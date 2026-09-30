"""Bounded reachability checks for public News hero images.

This verifies that a selected remote URL actually serves image bytes before the
story is allowed to rely on it. It is intentionally independent from AI and DB.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import logging
import socket
from typing import Iterable
from urllib.parse import urljoin, urlsplit, parse_qs, parse_qsl, urlencode, urlunsplit

import httpx

from .media_url import upgrade_hero_image_url

from .news_feed_http import validate_public_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
    "(compatible; NinkoSportsImageCheck/1.0; +https://ninkosports.com)"
)
# Verified FSS camera JPEGs have more than 64 KiB of EXIF/ICC metadata before
# their dimensions. Keep a bounded probe, stopping early once dimensions exist.
MAX_SNIFF_BYTES = 128 * 1024
_CACHE_TTL_OK = 6 * 60 * 60
_CACHE_TTL_BAD = 30 * 60
_CACHE: dict[str, tuple[float, bool, str]] = {}
logger = logging.getLogger(__name__)


def score_news_image_candidate(candidate: dict) -> float:
    """Prefer this article's explicit hero over images in recommendation cards."""
    from editorial import score_image_candidate
    score = score_image_candidate(candidate)
    if score < 0:
        return score
    # <main> and even <article> often also wrap unrelated story cards. Publisher
    # OG/NewsArticle metadata is stronger subject evidence than DOM position.
    return score + {"og": 24, "jsonld": 20, "twitter": 14}.get(candidate.get("source"), 0)


def pick_news_article_image(candidates):
    ranked = [row for row in candidates or [] if isinstance(row, dict)]
    best = max(ranked, key=score_news_image_candidate, default=None)
    return best.get("url") if best and score_news_image_candidate(best) >= 0 else None


def news_hero_url(url: str) -> str:
    """Select a same-photo size; callers MUST probe and persist this exact URL."""
    value = str(url or "").strip()
    try:
        parts = urlsplit(value)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        # Never alter signed URLs or publisher overlays.
        if {k.lower() for k, _ in pairs} & {
            "signature", "sig", "token", "policy", "expires", "st", "hmac",
            "x-amz-signature", "x-goog-signature",
            "overlay-base64", "overlay", "mark", "mark64", "txt",
        }:
            return value
        if any(k.lower() == 's' and v.lower() not in {'', 'none'} for k, v in pairs):
            return value
        # Verified UEFA image endpoint: 158x89 thumbnail -> 988x556 original.
        # Preserve the image identity, crop and every unrelated query value.
        if parts.hostname == "editorial.uefa.com":
            pairs = [(k, "1600" if k.lower() == "imwidth" and v.isdigit() else v)
                     for k, v in pairs]
            value = urlunsplit((parts.scheme, parts.netloc, parts.path,
                               urlencode(pairs), parts.fragment))
        return upgrade_hero_image_url(value) or value
    except ValueError:
        return value


def _looks_like_image_bytes(data: bytes) -> bool:
    head = bytes(data[:64])
    if head.startswith(b"\xff\xd8\xff"):
        return True  # JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if head.startswith((b"GIF87a", b"GIF89a")):
        return True
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    if b"ftypavif" in head or b"ftypavis" in head:
        return True
    return False


def _image_dimensions(data: bytes):
    """Return (width, height) from common image headers when available."""
    raw = bytes(data or b"")
    # All three WebP headers, per the RIFF container specification. CDN content
    # negotiation can return WebP even when the URL ends in .jpeg.
    if len(raw) >= 30 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        kind, payload = raw[12:16], raw[20:]
        if kind == b"VP8X":
            return (1 + int.from_bytes(payload[4:7], "little"),
                    1 + int.from_bytes(payload[7:10], "little"))
        if kind == b"VP8 " and payload[3:6] == b"\x9d\x01\x2a":
            return (int.from_bytes(payload[6:8], "little") & 0x3fff,
                    int.from_bytes(payload[8:10], "little") & 0x3fff)
        if kind == b"VP8L" and payload[0] == 0x2f:
            packed = int.from_bytes(payload[1:5], "little")
            return (1 + (packed & 0x3fff), 1 + ((packed >> 14) & 0x3fff))
    # PNG: signature + IHDR width/height.
    if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n") and raw[12:16] == b"IHDR":
        return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    # GIF logical screen dimensions.
    if len(raw) >= 10 and raw.startswith((b"GIF87a", b"GIF89a")):
        return int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little")
    # JPEG SOF markers can follow several EXIF/ICC application segments.
    if len(raw) >= 4 and raw[:2] == b"\xff\xd8":
        pos = 2
        sof = {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}
        while pos + 4 <= len(raw):
            if raw[pos] != 0xFF:
                pos += 1
                continue
            while pos < len(raw) and raw[pos] == 0xFF:
                pos += 1
            if pos >= len(raw):
                break
            marker = raw[pos]
            pos += 1
            if marker in {0xD8, 0xD9}:
                continue
            if marker == 0xDA:
                break
            if pos + 2 > len(raw):
                break
            seglen = int.from_bytes(raw[pos:pos+2], "big")
            if seglen < 2 or pos + seglen > len(raw):
                break
            if marker in sof and seglen >= 7:
                height = int.from_bytes(raw[pos+3:pos+5], "big")
                width = int.from_bytes(raw[pos+5:pos+7], "big")
                return width, height
            pos += seglen
    return None


def _image_geometry_reason(data: bytes, url: str = ""):
    dims = _image_dimensions(data)
    if not dims:
        return "image_dimensions_unverified"
    width, height = dims
    if width <= 0 or height <= 0:
        return "image_dimensions_unverified"
    ratio = width / max(height, 1)
    if ratio > 3.5 or ratio < 0.35:
        return "bad_aspect_ratio"
    if width < 640 or height < 320:
        # A possible larger URL is not proof. Probe the selected hero itself;
        # never approve a thumbnail on the assumption that the UI upgrades it.
        return "image_too_small"
    return None


def _cache_get(url: str):
    cached = _CACHE.get(url)
    if not cached:
        return None
    expires, ok, reason = cached
    if expires <= time.monotonic():
        _CACHE.pop(url, None)
        return None
    return ok, reason


def _cache_put(url: str, ok: bool, reason: str):
    ttl = _CACHE_TTL_OK if ok else _CACHE_TTL_BAD
    _CACHE[url] = (time.monotonic() + ttl, bool(ok), str(reason))
    if not ok:
        logger.info('[news-image] held host=%s reason=%s', urlsplit(url).hostname, reason)


def clear_image_probe_cache():
    """Tests/admin diagnostics only; production normally relies on TTL expiry."""
    _CACHE.clear()


def probe_news_image(url: str, *, client=None) -> tuple[bool, str]:
    value = str(url or "").strip()
    if not value:
        return False, "missing"
    try:
        keys = {key.lower() for key in parse_qs(urlsplit(value).query)}
    except ValueError:
        return False, "invalid_or_nonpublic_url"
    # The independently deployed reader still resizes Guardian card/hero URLs.
    # A valid signed source URL then becomes HTTP 401 on the public page.
    # Never strip/regenerate its signature: select an explicitly published
    # unsigned same-article photo candidate instead. This is News-only repair.
    parts = urlsplit(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if (parts.hostname == 'i.guim.co.uk' and 'width' in query
            and query.get('s', '').lower() not in {'', 'none'}):
        return False, 'signed_image_display_incompatible'
    # Confirmed NBL incident: a repeated navigation/product logo outranked the
    # article's player photograph. Large dimensions do not make a logo a hero.
    if (urlsplit(value).hostname == "cdn.prod.website-files.com"
            and re.search(r"[_/](?:nblplus(?:%20|[ ._(%-])|NBL%2B_|670f29f16cffa3066d5d5ca1_Exclusive\.)", urlsplit(value).path, re.I)):
        return False, "publisher_default_image"
    if (urlsplit(value).hostname == 'images.ctfassets.net'
            and re.search(r'/DPG_Media_Building_[^/]+\.(?:png|jpe?g)$', urlsplit(value).path, re.I)):
        return False, 'publisher_default_image'
    if re.search(r"(?:^|[/_-])(?:banner|title[-_]card)(?:[._-]|$)", urlsplit(value).path, re.I):
        return False, "promotional_banner"
    # Choose another real photograph from the same article. Do not strip an
    # overlay or modify a signed publisher image URL to manufacture a new one.
    if keys & {"overlay-base64", "overlay", "mark", "mark64", "txt"}:
        return False, "composited_overlay"
    if re.search(r"(?:[,/])overlay[-_,]", urlsplit(value).path, re.I):
        return False, "composited_overlay"
    cached = _cache_get(value)
    if cached is not None:
        return cached

    own_client = client is None
    try:
        validate_public_url(value)
    except socket.gaierror:
        result = (False, "dns_resolution_failed")
        _cache_put(value, *result)
        return result
    except Exception:
        result = (False, "invalid_or_nonpublic_url")
        _cache_put(value, *result)
        return result

    if own_client:
        client = httpx.Client(
            timeout=httpx.Timeout(6.0, connect=3.0),
            follow_redirects=False,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://ninkosports.com/",
                "Accept": "image/jpeg,image/png,image/webp,image/gif;q=0.8",
            },
        )

    current = value
    range_header = f"bytes=0-{MAX_SNIFF_BYTES - 1}"
    redirects = 0
    try:
        for _ in range(5):
            try:
                validate_public_url(current)
                with client.stream("GET", current, headers={"Range": range_header} if range_header else {}) as response:
                    # Some image CDNs reject a range extending beyond EOF.
                    # Retry the SAME URL once without Range, still reading at
                    # most MAX_SNIFF_BYTES and enforcing all image/geometry gates.
                    if response.status_code == 416 and range_header:
                        range_header = None
                        logger.info('[news-image] range unsupported; bounded full GET host=%s', urlsplit(current).hostname)
                        continue
                    if response.status_code in (301, 302, 303, 307, 308):
                        redirects += 1
                        if redirects >= 4:
                            result = (False, 'redirect_limit')
                            _cache_put(value, *result)
                            return result
                        location = response.headers.get("location", "")
                        if not location:
                            result = (False, "redirect_without_location")
                            _cache_put(value, *result)
                            return result
                        current = urljoin(current, location)
                        continue
                    if response.status_code not in (200, 206):
                        result = (False, f"http_{response.status_code}")
                        _cache_put(value, *result)
                        return result

                    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if chunk:
                            data.extend(chunk[: max(0, MAX_SNIFF_BYTES - len(data))])
                        if len(data) >= MAX_SNIFF_BYTES or _image_dimensions(bytes(data)) is not None:
                            break
                    magic_ok = _looks_like_image_bytes(bytes(data))
                    if not data:
                        result = (False, "empty_image_response")
                        _cache_put(value, *result)
                        return result
                    if not magic_ok:
                        result = (False, "not_image_content")
                        _cache_put(value, *result)
                        return result
                    geometry_reason = _image_geometry_reason(bytes(data), current)
                    if geometry_reason:
                        result = (False, geometry_reason)
                        _cache_put(value, *result)
                        return result
                    result = (True, "ok")
                    _cache_put(value, *result)
                    return result
            except Exception as exc:
                logger.info('[news-image] transport exception host=%s type=%s',
                            urlsplit(value).hostname, type(exc).__name__)
                result = (False, "request_failed")
                _cache_put(value, *result)
                return result
        result = (False, "redirect_limit")
        _cache_put(value, *result)
        return result
    finally:
        if own_client:
            client.close()


def news_image_is_reachable(url: str) -> bool:
    return probe_news_image(url)[0]


def probe_news_images(urls: Iterable[str], *, max_workers: int = 6) -> dict[str, tuple[bool, str]]:
    unique = []
    seen = set()
    for raw in urls:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    if not unique:
        return {}

    workers = max(1, min(int(max_workers or 1), 8, len(unique)))
    if workers == 1:
        return {url: probe_news_image(url) for url in unique}

    results: dict[str, tuple[bool, str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(probe_news_image, url): url for url in unique}
        for future in as_completed(pending):
            url = pending[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = (False, "probe_failed")
    return results
