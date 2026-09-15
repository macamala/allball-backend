"""Same-image URL size selection. String rewrites only — never fetches."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Display roles → target CSS-pixel width of the SAME image.
DISPLAY_WIDTHS = {
    "thumb": 320,
    "card": 800,
    "featured": 1280,
    "hero": 1600,
}
HERO_TARGET_WIDTH = DISPLAY_WIDTHS["hero"]
QUERY_WIDTH_KEYS = {
    "w",
    "width",
    "maxwidth",
    "max_width",
    "max-width",
    "resize",
    "rwidth",
    "fitw",
}

PATH_WIDTH_RE = re.compile(
    r"(?P<pre>/(?:ace/(?:standard|ws)|news|iplayer)/)(?P<w>\d{2,4})(?=/)",
    re.IGNORECASE,
)
WP_CROP_RE = re.compile(
    r"-(?P<w>\d{2,4})x(?P<h>\d{2,4})(?=\.(?:jpe?g|png|webp|gif)(?:$|\?))",
    re.IGNORECASE,
)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(
    r"""\b(?P<key>src|srcset|width)=(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
ATTR_BARE_WIDTH_RE = re.compile(r"""\bwidth=['"]?(\d+)""", re.IGNORECASE)


def width_from_url(url: Optional[str]) -> int:
    raw = (url or "").strip()
    if not raw:
        return 0
    match = PATH_WIDTH_RE.search(raw)
    if match:
        return int(match.group("w"))
    parsed = urlsplit(raw)
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in QUERY_WIDTH_KEYS and str(value).isdigit():
            return int(value)
    crop = WP_CROP_RE.search(parsed.path)
    if crop:
        return int(crop.group("w"))
    return 0


def image_stem(url: Optional[str]) -> str:
    """Identity of one photo across size variants of the same file."""
    raw = (url or "").strip()
    if not raw:
        return ""
    rewritten = PATH_WIDTH_RE.sub(lambda m: f"{m.group('pre')}{{w}}", raw)
    parsed = urlsplit(rewritten)
    path = WP_CROP_RE.sub("", parsed.path)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in QUERY_WIDTH_KEYS
    ]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def image_url_for_display(url: Optional[str], role: str = "card") -> Optional[str]:
    """Same photo, sized for the UI surface. Never invents a different image."""
    raw = (url or "").strip()
    if not raw:
        return raw
    target = DISPLAY_WIDTHS.get(role, DISPLAY_WIDTHS["card"])
    current = width_from_url(raw)
    if current <= 0:
        return raw
    if current == target:
        return raw
    upgraded = _replace_width(raw, target)
    return upgraded or raw


def upgrade_hero_image_url(url: Optional[str]) -> Optional[str]:
    return image_url_for_display(url, "hero")


def _replace_width(url: str, width: int) -> str:
    if PATH_WIDTH_RE.search(url):
        return PATH_WIDTH_RE.sub(lambda m: f"{m.group('pre')}{width}", url, count=1)
    parsed = urlsplit(url)
    pairs = []
    changed = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in QUERY_WIDTH_KEYS and str(value).isdigit():
            pairs.append((key, str(width)))
            changed = True
        else:
            pairs.append((key, value))
    if changed:
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), parsed.fragment)
        )
    crop = WP_CROP_RE.search(parsed.path)
    if crop and int(crop.group("w")) < width and width >= 800:
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                WP_CROP_RE.sub("", parsed.path),
                parsed.query,
                parsed.fragment,
            )
        )
    return url


def pick_source_image(candidates: Sequence[Tuple[str, int]]) -> Optional[str]:
    """Keep the first photo's family; choose the largest same-image URL."""
    usable: List[Tuple[str, int]] = []
    for url, width in candidates:
        value = (url or "").strip()
        if not value:
            continue
        usable.append((value, int(width or 0) or width_from_url(value)))
    if not usable:
        return None
    stem = image_stem(usable[0][0])
    group = [item for item in usable if image_stem(item[0]) == stem] or usable
    return max(group, key=lambda item: item[1])[0]


def images_from_html(html: Optional[str]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for tag in IMG_TAG_RE.findall(html or ""):
        src = ""
        srcset = ""
        width = 0
        for match in ATTR_RE.finditer(tag):
            key = match.group("key").lower()
            val = match.group("val").strip()
            if key == "src":
                src = val
            elif key == "srcset":
                srcset = val
            elif key == "width" and val.isdigit():
                width = int(val)
        if not width:
            bare = ATTR_BARE_WIDTH_RE.search(tag)
            if bare:
                width = int(bare.group(1))
        if src:
            out.append((src, width or width_from_url(src)))
        out.extend(_parse_srcset(srcset))
    return out


def _parse_srcset(srcset: str) -> List[Tuple[str, int]]:
    items: List[Tuple[str, int]] = []
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        descriptor = bits[1] if len(bits) > 1 else ""
        width = 0
        if descriptor.endswith("w"):
            try:
                width = int(descriptor[:-1])
            except ValueError:
                width = 0
        items.append((url, width or width_from_url(url)))
    return items


def collect_feed_image_candidates(entry) -> List[Tuple[str, int]]:
    candidates: List[Tuple[str, int]] = []
    for key in ("media_content", "media_thumbnail"):
        rows = entry.get(key) if hasattr(entry, "get") else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = row.get("url") or row.get("href")
            if not url:
                continue
            width = _int_field(row.get("width"))
            height = _int_field(row.get("height"))
            candidates.append((url, width or height or width_from_url(url)))
    links = entry.get("links") if hasattr(entry, "get") else None
    for link in links or []:
        if not isinstance(link, dict):
            continue
        if link.get("rel") == "enclosure" and str(link.get("type") or "").startswith("image"):
            url = link.get("href")
            if url:
                candidates.append((url, _int_field(link.get("width")) or width_from_url(url)))
    summary = ""
    if hasattr(entry, "get"):
        summary = entry.get("summary") or entry.get("description") or ""
    candidates.extend(images_from_html(summary))
    return candidates


def _int_field(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
