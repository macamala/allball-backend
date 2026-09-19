"""Shared HTTP fetch for production adapters.

Does not solve CAPTCHAs, Cloudflare challenges, logins, or paywalls.
Restricted responses are returned to the collector for fallback.
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

from collector.adapters import FetchResult
from collector.family_health import family_from_host, note_family_failure, reset_family_health

USER_AGENT = "NinkoSportsCollector/2.5 (+https://ninkosports.com; sports-data collection)"
DEFAULT_TIMEOUT = 20

_CACHE: Dict[str, FetchResult] = {}
STATS: Dict[str, int] = {
    "requests": 0,
    "cache_hits": 0,
    "timeouts": 0,
    "retries": 0,
    "budget_skips": 0,
    "paced": 0,
    "http_429": 0,
    "http_403": 0,
    "network_failures": 0,
}
_LOCAL = threading.local()
_HOST_BLOCKED_UNTIL: Dict[str, float] = {}
_HOST_BLOCK_KIND: Dict[str, str] = {}
_HOST_LAST_REQUEST: Dict[str, float] = {}
_HOST_MIN_INTERVAL = {
    "www.thesportsdb.com": 1.25,
    "thesportsdb.com": 1.25,
    "www.bbc.com": 0.35,
    "bbc.com": 0.35,
    "www.bbc.co.uk": 0.35,
    "bbc.co.uk": 0.35,
    "www.espn.com": 1.0,
    "www.soccerway.com": 0.4,
    "soccerway.com": 0.4,
    "www.the-aiff.com": 0.35,
    "the-aiff.com": 0.35,
    "www.rte.ie": 0.35,
    "rte.ie": 0.35,
    "super.rugby": 0.4,
    "www.eliteprospects.com": 0.45,
    "eliteprospects.com": 0.45,
    "en.volleyballworld.com": 0.35,
    "www-old.cev.eu": 0.4,
    "espn.com": 1.0,
    "site.api.espn.com": 1.0,
    "api.wtatennis.com": 0.5,
    "liquipedia.net": 0.4,
    "raw.githubusercontent.com": 0.3,
    "api.github.com": 0.4,
}

_HOST_LOCKS: Dict[str, threading.Lock] = {}
_ROLLING: deque = deque()
_PHYSICAL_ROLLING: deque = deque()

CHALLENGE_MARKERS = (
    b"just a moment",
    b"cf-browser-verification",
    b"cdn-cgi/challenge",
    b"cdn-cgi/challenges",
    b"attention required! | cloudflare",
    b"cf-challenge-running",
    b"_cf_chl",
)

HttpGetter = Callable[[str, Optional[Dict[str, str]]], FetchResult]


def reset_http_stats() -> None:
    _CACHE.clear()
    _HOST_BLOCKED_UNTIL.clear()
    _HOST_BLOCK_KIND.clear()
    _HOST_LAST_REQUEST.clear()
    STATS.update(
        requests=0,
        cache_hits=0,
        timeouts=0,
        retries=0,
        budget_skips=0,
        paced=0,
        http_429=0,
        http_403=0,
        network_failures=0,
    )
    STATS["espn"] = []
    STATS["by_family"] = {}
    STATS["rolling_hour"] = {}
    _ROLLING.clear()
    _PHYSICAL_ROLLING.clear()
    reset_family_health()


def begin_budget(*, max_requests: int = 6, max_seconds: float = 18.0) -> None:
    _LOCAL.budget = {
        "max_requests": max_requests,
        "max_seconds": max_seconds,
        "used": 0,
        "started": time.monotonic(),
        "timeouts": 0,
    }


def end_budget() -> Dict[str, int]:
    budget = getattr(_LOCAL, "budget", None) or {}
    _LOCAL.budget = None
    return {
        "requests": int(budget.get("used") or 0),
        "timeouts": int(budget.get("timeouts") or 0),
    }


def budget_remaining() -> bool:
    budget = getattr(_LOCAL, "budget", None)
    if not budget:
        return True
    if budget["used"] >= budget["max_requests"]:
        return False
    if time.monotonic() - budget["started"] >= budget["max_seconds"]:
        return False
    return True


def note_physical_requests(count: int) -> None:
    now = time.time()
    _PHYSICAL_ROLLING.append((now, int(count or 0)))
    cutoff = now - 3600
    while _PHYSICAL_ROLLING and _PHYSICAL_ROLLING[0][0] < cutoff:
        _PHYSICAL_ROLLING.popleft()


def rolling_http_hour() -> Dict[str, Any]:
    cutoff = time.time() - 3600
    while _ROLLING and _ROLLING[0][0] < cutoff:
        _ROLLING.popleft()
    by_family: Dict[str, Dict[str, int]] = {}
    for _ts, fam, status, timeout in _ROLLING:
        row = by_family.setdefault(fam, {"requests": 0, "http_403": 0, "http_429": 0, "timeouts": 0})
        row["requests"] += 1
        if status == 403:
            row["http_403"] += 1
        if status == 429:
            row["http_429"] += 1
        if timeout:
            row["timeouts"] += 1
    physical = sum(n for ts, n in _PHYSICAL_ROLLING if ts >= cutoff)
    espn_403 = int((by_family.get("espn-html") or {}).get("http_403") or 0)
    return {
        "window_s": 3600,
        "physical_requests": physical,
        "http_requests": len(_ROLLING),
        "espn_403": espn_403,
        "http_429": sum(int(row.get("http_429") or 0) for row in by_family.values()),
        "timeouts": sum(int(row.get("timeouts") or 0) for row in by_family.values()),
        "by_family": by_family,
    }


def _note_request(url: str, result: FetchResult) -> None:
    STATS["requests"] += 1
    timeout = False
    budget = getattr(_LOCAL, "budget", None)
    if budget is not None:
        budget["used"] += 1
        if result.http_status == 0 or "timeout" in (result.error or "").lower() or "timed out" in (result.error or "").lower():
            budget["timeouts"] += 1
            STATS["timeouts"] += 1
            timeout = True
    fam = family_from_host(_host(url)) or _host(url) or "unknown"
    _ROLLING.append((time.time(), fam, int(result.http_status or 0), timeout))
    if len(_ROLLING) > 8000:
        _ROLLING.popleft()
    STATS["rolling_hour"] = rolling_http_hour()


def _cached(url: str) -> Optional[FetchResult]:
    hit = _CACHE.get(url)
    if hit is not None:
        STATS["cache_hits"] += 1
    return hit


def _store(url: str, result: FetchResult) -> FetchResult:
    if result.http_status != 0:
        _CACHE[url] = result
    return result


def _decode_body(raw: bytes, encoding: str = "") -> bytes:
    if encoding.lower() == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    return raw


def _is_challenge(status: int, body: bytes) -> bool:
    if status in {202, 401, 403}:
        return True
    sample = body[:4000].lower()
    return any(marker in sample for marker in CHALLENGE_MARKERS)


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _host_blocked(url: str) -> bool:
    until = _HOST_BLOCKED_UNTIL.get(_host(url), 0)
    return time.monotonic() < until


def _block_host(url: str, seconds: float = 120.0, kind: str = "rate") -> None:
    host = _host(url)
    _HOST_BLOCKED_UNTIL[host] = max(_HOST_BLOCKED_UNTIL.get(host, 0), time.monotonic() + seconds)
    _HOST_BLOCK_KIND[host] = kind


def host_is_blocked(url: str) -> bool:
    return _host_blocked(url)


FAMILY_BLOCK_URLS = {
    "thesportsdb": "https://www.thesportsdb.com/",
    "bbc-sport": "https://www.bbc.com/",
    "espn-html": "https://www.espn.com/",
    "soccerway": "https://www.soccerway.com/",
    "liquipedia": "https://liquipedia.net/",
    "sackmann-tennis": "https://raw.githubusercontent.com/",
}


def family_host_blocked(family: str) -> bool:
    url = FAMILY_BLOCK_URLS.get(family or "")
    return bool(url) and host_is_blocked(url)


def _pace_host(url: str) -> None:
    host = _host(url)
    interval = _HOST_MIN_INTERVAL.get(host, 0)
    lock = _HOST_LOCKS.setdefault(host, threading.Lock())
    with lock:
        if interval > 0:
            last = _HOST_LAST_REQUEST.get(host, 0)
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                STATS["paced"] = STATS.get("paced", 0) + 1
                time.sleep(wait)
        _HOST_LAST_REQUEST[host] = time.monotonic()


def _transport_error(url: str, exc: BaseException) -> FetchResult:
    err = str(exc)
    lowered = err.lower()
    if "getaddrinfo" in err or "name or service not known" in lowered or "nodename nor servname" in lowered:
        _block_host(url, 30.0, kind="dns")
    result = FetchResult(ok=False, http_status=0, error=err, classification="NETWORK_FAILURE")
    STATS["network_failures"] = STATS.get("network_failures", 0) + 1
    _note_request(url, result)
    return result


def fetch_url(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> FetchResult:
    cached = _cached(url)
    if cached is not None:
        return cached
    if _host_blocked(url):
        STATS["budget_skips"] += 1
        kind = _HOST_BLOCK_KIND.get(_host(url), "rate")
        if kind == "dns":
            return FetchResult(ok=False, http_status=0, error="host dns recently failed", classification="NETWORK_FAILURE")
        return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")
    if not budget_remaining():
        STATS["budget_skips"] += 1
        return FetchResult(ok=False, http_status=0, error="request budget exceeded")
    _pace_host(url)
    timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = _decode_body(resp.read(), resp.headers.get("Content-Encoding") or "")
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        raw = _decode_body(exc.read() or b"", (exc.headers.get("Content-Encoding") if exc.headers else "") or "")
        status = int(exc.code or 0)
        if status == 403:
            STATS["http_403"] = STATS.get("http_403", 0) + 1
            fam = family_from_host(_host(url))
            wait = 21600.0 if fam == "espn-html" else 900.0
            _block_host(url, wait, kind="forbidden")
            if fam:
                note_family_failure(fam, http_status=403, error_type="ACCESS_BLOCKED", retry_after_s=wait)
        if status == 429 or _is_challenge(status, raw):
            result = FetchResult(
                ok=False,
                http_status=status,
                restricted=status != 429,
                error=f"http {status}",
                payload=None,
            )
            if status == 429:
                STATS["http_429"] = STATS.get("http_429", 0) + 1
                retry_after = 120.0
                try:
                    retry_after = float((exc.headers or {}).get("Retry-After") or 120)
                except (TypeError, ValueError):
                    retry_after = 120.0
                _block_host(url, max(30.0, min(retry_after, 300.0)))
                fam = family_from_host(_host(url))
                if fam:
                    note_family_failure(fam, http_status=429, error_type="RATE_LIMITED", retry_after_s=retry_after)
            _note_request(url, result)
            return _store(url, result)
        result = FetchResult(ok=False, http_status=status, error=f"http {status}")
        if status == 503:
            _block_host(url, 180.0, kind="unavailable")
            _note_request(url, result)
            return result
        _note_request(url, result)
        return _store(url, result)
    except Exception as exc:  # noqa: BLE001
        return _transport_error(url, exc)

    if _is_challenge(status, raw):
        result = FetchResult(ok=False, http_status=status, restricted=True, error="access restricted")
        _note_request(url, result)
        return _store(url, result)
    payload: Any
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = raw.decode("utf-8", "replace")
        result = FetchResult(ok=False, http_status=status, error="non-json response", payload=text[:300])
        _note_request(url, result)
        return _store(url, result)
    result = FetchResult(ok=True, http_status=status, payload=payload)
    _note_request(url, result)
    return _store(url, result)


def fetch_bytes(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> FetchResult:
    """GET raw bytes. Used for zip datasets and non-JSON bodies."""
    cached = _cached(url)
    if cached is not None:
        return cached
    if _host_blocked(url):
        STATS["budget_skips"] += 1
        kind = _HOST_BLOCK_KIND.get(_host(url), "rate")
        if kind == "dns":
            return FetchResult(ok=False, http_status=0, error="host dns recently failed", classification="NETWORK_FAILURE")
        return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")
    if not budget_remaining():
        STATS["budget_skips"] += 1
        return FetchResult(ok=False, http_status=0, error="request budget exceeded")
    _pace_host(url)
    timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = _decode_body(resp.read(), resp.headers.get("Content-Encoding") or "")
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        raw = _decode_body(exc.read() or b"", (exc.headers.get("Content-Encoding") if exc.headers else "") or "")
        status = int(exc.code or 0)
        if status == 403:
            STATS["http_403"] = STATS.get("http_403", 0) + 1
            fam = family_from_host(_host(url))
            wait = 21600.0 if fam == "espn-html" else 900.0
            _block_host(url, wait, kind="forbidden")
            if fam:
                note_family_failure(fam, http_status=403, error_type="ACCESS_BLOCKED", retry_after_s=wait)
        if status == 429 or _is_challenge(status, raw):
            result = FetchResult(
                ok=False,
                http_status=status,
                restricted=status != 429,
                error=f"http {status}",
            )
            if status == 429:
                STATS["http_429"] = STATS.get("http_429", 0) + 1
                _block_host(url, 120.0)
                fam = family_from_host(_host(url))
                if fam:
                    note_family_failure(fam, http_status=429, error_type="RATE_LIMITED", retry_after_s=120)
            _note_request(url, result)
            return _store(url, result)
        result = FetchResult(ok=False, http_status=status, error=f"http {status}")
        _note_request(url, result)
        return _store(url, result)
    except Exception as exc:  # noqa: BLE001
        return _transport_error(url, exc)
    if _is_challenge(status, raw):
        result = FetchResult(ok=False, http_status=status, restricted=True, error="access restricted")
        _note_request(url, result)
        return _store(url, result)
    result = FetchResult(ok=True, http_status=status, payload=raw)
    _note_request(url, result)
    return _store(url, result)


def fetch_text(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> FetchResult:
    timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    accept = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.1",
    }
    if headers:
        accept.update(headers)
    result = fetch_bytes(url, headers=accept, timeout=timeout)
    if not result.ok:
        return result
    raw = result.payload if isinstance(result.payload, (bytes, bytearray)) else b""
    text = raw.decode("utf-8", "replace")
    lowered = text[:4000].lower()
    if any(marker.decode("utf-8", "ignore") in lowered if isinstance(marker, bytes) else marker in lowered for marker in CHALLENGE_MARKERS):
        return FetchResult(ok=False, http_status=result.http_status, restricted=True, error="access restricted")
    return FetchResult(ok=True, http_status=result.http_status, payload=text)


def urljoin_query(base: str, params: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{query}" if query else base
