"""Source adapter contract.

Adapters must not bypass authentication, CAPTCHAs, Cloudflare, paywalls,
anti-bot controls, or other access restrictions. A 401/403/429 with a
challenge is recorded as restricted and the collector falls back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


class AccessRestricted(Exception):
    """The source refused access. Do not retry as a bypass."""


class AdapterNotRegistered(Exception):
    """No adapter class is registered for this source."""


class LicensedSourceInactive(Exception):
    """Licensed/commercial source is optional and not configured."""


ADAPTERS: Dict[str, type] = {}


def register_adapter(adapter_key: str, cls: type) -> None:
    ADAPTERS[adapter_key] = cls


def unregister_adapter(adapter_key: str) -> None:
    ADAPTERS.pop(adapter_key, None)


@dataclass
class FetchRequest:
    capability: str
    sport_id: Optional[str] = None
    competition_id: Optional[str] = None
    source_competition_id: Optional[str] = None
    event_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    series_id: Optional[str] = None
    game_id: Optional[str] = None
    country_id: Optional[str] = None
    parent_sport_id: Optional[str] = None
    source_config: Dict[str, Any] = field(default_factory=dict)
    coverage_scope: str = "full"
    coverage_context: Optional[str] = None
    upstream_family: Optional[str] = None


@dataclass
class FetchResult:
    ok: bool
    http_status: int = 0
    payload: Any = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    standings: List[Dict[str, Any]] = field(default_factory=list)
    rankings: List[Dict[str, Any]] = field(default_factory=list)
    competitions: List[Dict[str, Any]] = field(default_factory=list)
    restricted: bool = False
    error: Optional[str] = None
    classification: Optional[str] = None
    latency_ms: Optional[int] = None
    parse_status: Optional[str] = None
    config_missing: bool = False
    empty_reason: Optional[str] = None
    request_count: int = 0
    parse_reason: Optional[str] = None


class SourceAdapter(Protocol):
    source_id: str
    adapter_key: str

    def fetch(self, request: FetchRequest) -> FetchResult:
        ...

    def health_check(self, request: FetchRequest) -> FetchResult:
        ...


def get_adapter_class(adapter_key: str) -> type:
    cls = ADAPTERS.get(adapter_key)
    if cls is None:
        raise AdapterNotRegistered(adapter_key)
    return cls


def make_adapter(adapter_key: str, source_id: str) -> SourceAdapter:
    factory = get_adapter_class(adapter_key)
    try:
        return factory(source_id=source_id)
    except TypeError:
        return factory()
