"""Expand only the official FIFA artwork template; never guess an entity ID."""
from __future__ import annotations
import re
from urllib.parse import unquote, urlsplit, urlunsplit

_FIFA_TEMPLATE = re.compile(r'^/api/v3/picture/(flags|teams)-\{format\}-\{size\}/([A-Za-z0-9_-]{1,128})$')


def image_asset_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if parts.scheme != 'https' or parts.netloc.lower() != 'api.fifa.com':
        return value
    match = _FIFA_TEMPLATE.fullmatch(unquote(parts.path))
    if not match:
        return value
    path = f'/api/v3/picture/{match[1]}-sq-2/{match[2]}'
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
