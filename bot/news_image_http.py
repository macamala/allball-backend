"""Bounded reachability checks for public News hero images.

This verifies that a selected remote URL actually serves image bytes before the
story is allowed to rely on it. It is intentionally independent from AI and DB.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Iterable
from urllib.parse import urljoin

import httpx

from .media_url import upgrade_hero_image_url

from .news_feed_http import validate_public_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
    "(compatible; NinkoSportsImageCheck/1.0; +https://ninkosports.com)"
)
MAX_SNIFF_BYTES = 64 * 1024
_CACHE_TTL_OK = 6 * 60 * 60
_CACHE_TTL_BAD = 30 * 60
_CACHE: dict[str, tuple[float, bool, str]] = {}


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
    # PNG: signature + IHDR width/height.
    if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n") and raw[12:16] == b"IHDR":
        return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    # GIF logical screen dimensions.
    if len(raw) >= 10 and raw.startswith((b"GIF87a", b"GIF89a")):
        return int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little")
    # JPEG SOF markers normally occur well inside the bounded 64 KiB sniff.
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
        return None
    width, height = dims
    if width <= 0 or height <= 0:
        return None
    if width < 320 or height < 140:
        # Some publishers (notably BBC ichef) encode the requested display
        # width in the URL. The public UI rewrites that same-photo URL to the
        # hero role, so a 240px transport variant is not inherently a bad hero.
        upgraded = upgrade_hero_image_url(url)
        if not upgraded or upgraded == url:
            return "image_too_small"
    ratio = width / max(height, 1)
    if ratio > 3.5 or ratio < 0.35:
        return "bad_aspect_ratio"
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


def clear_image_probe_cache():
    """Tests/admin diagnostics only; production normally relies on TTL expiry."""
    _CACHE.clear()


def probe_news_image(url: str, *, client=None) -> tuple[bool, str]:
    value = str(url or "").strip()
    if not value:
        return False, "missing"
    cached = _cache_get(value)
    if cached is not None:
        return cached

    own_client = client is None
    try:
        validate_public_url(value)
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
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.5",
                "Range": f"bytes=0-{MAX_SNIFF_BYTES - 1}",
            },
        )

    current = value
    try:
        for _ in range(4):
            try:
                validate_public_url(current)
                with client.stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
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
                        if len(data) >= MAX_SNIFF_BYTES:
                            break
                    magic_ok = _looks_like_image_bytes(bytes(data))
                    type_ok = content_type.startswith("image/")
                    if not data:
                        result = (False, "empty_image_response")
                        _cache_put(value, *result)
                        return result
                    if not type_ok and not magic_ok:
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
            except Exception:
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
