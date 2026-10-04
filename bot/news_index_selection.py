"""News discovery selection only; no publication, database or network actions.

Already-ingested links and recently verified stale pages must not fill an
index's eight-link quota before newer/unseen articles are considered. The
transport limits, article timestamps, image/factual gates and AI budget remain
unchanged. Losing this cache on restart only repeats a read; it loses no news.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock
import time

from .news_policy import news_source_identity

_STALE_SECONDS = 30 * 60
_MAX_STALE = 2048
_STALE: OrderedDict[tuple[str, str], float] = OrderedDict()
_LOCK = Lock()


def discovery_config(cfg: dict, known_urls=()) -> dict:
    """Exclude identities before selecting eight links, only for football."""
    if cfg.get('sport') != 'football':
        return cfg
    known = {identity for url in known_urls if (identity := news_source_identity(url))}
    now = time.monotonic()
    source = str(cfg.get('id') or '')
    with _LOCK:
        for key, expires in list(_STALE.items()):
            if expires <= now:
                _STALE.pop(key, None)
        known.update(identity for (desk, identity), expires in _STALE.items()
                     if desk == source and expires > now)
    return {**cfg, '_news_exclude_ids': frozenset(known)}


def excluded_index_link(cfg: dict, url: str) -> bool:
    identity = news_source_identity(url)
    return bool(identity and identity in cfg.get('_news_exclude_ids', ()))


def record_stale_index_page(cfg: dict, url: str, reasons: dict) -> None:
    """Only a confirmed old publication date qualifies; errors never do.

    Missing bodies, denied transport, future dates, unverified timestamps and
    valid articles waiting for a writer are deliberately not cached here.
    """
    if cfg.get('sport') != 'football' or set(reasons) != {'stale_publication'}:
        return
    identity = news_source_identity(url)
    source = str(cfg.get('id') or '')
    if not source or not identity or not reasons.get('stale_publication'):
        return
    key = (source, identity)
    with _LOCK:
        _STALE[key] = time.monotonic() + _STALE_SECONDS
        _STALE.move_to_end(key)
        while len(_STALE) > _MAX_STALE:
            _STALE.popitem(last=False)
