"""Canonical competitor name keys so providers with different spellings match."""

from __future__ import annotations

from collector.util import slugify

ALIASES = {
    "man-utd": "manchester-united",
    "man-united": "manchester-united",
    "manchester-utd": "manchester-united",
    "spurs": "tottenham-hotspur",
    "tottenham": "tottenham-hotspur",
    "inter": "inter-milan",
    "internazionale": "inter-milan",
    "psg": "paris-saint-germain",
    "paris-sg": "paris-saint-germain",
    "fc-bayern": "fc-bayern-munchen",
    "bayern-munich": "fc-bayern-munchen",
    "fc-bayern-munchen": "fc-bayern-munchen",
    "athletic-bilbao": "athletic-club",
}


def canonical_name_key(value: object) -> str:
    if isinstance(value, dict):
        raw = value.get("slug") or value.get("name") or ""
    else:
        raw = value or ""
    slug = slugify(str(raw))
    return ALIASES.get(slug, slug)
