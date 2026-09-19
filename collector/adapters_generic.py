"""Reusable family adapter for verified public HTTP sources without a dedicated parser."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.html_parse import fixture_urls, parse_html, walk_json_events
from collector.adapters_sites import events_for_host
from collector.http import budget_remaining, fetch_text, fetch_url

SCORE_RE = re.compile(
    r"([A-Z][A-Za-z0-9 .'\-]{1,40})\s+(\d{1,3})\s*[-–]\s*(\d{1,3})\s+([A-Z][A-Za-z0-9 .'\-]{1,40})"
)

WINDOW_CAPABILITIES = {"fixtures", "results", "live_scores", "snapshot"}


def classify_http(result: FetchResult) -> str:
    if result.config_missing:
        return "CONFIG_MISSING"
    if result.http_status == 429:
        return "RATE_LIMITED"
    err = (result.error or "").lower()
    if result.http_status == 0 or "timed out" in err or "timeout" in err:
        return "NETWORK_FAILURE"
    if result.restricted or result.http_status in {401, 403}:
        return "SOURCE_CHANGED" if result.http_status in {401, 403, 200} or result.restricted else "NETWORK_FAILURE"
    if result.http_status in {404, 410}:
        return "SOURCE_CHANGED"
    if result.parse_status == "failed":
        return "PARSE_FAILURE"
    if result.ok and not result.events and not result.standings:
        return "NO_CURRENT_EVENTS"
    if result.ok:
        return "WORKING"
    return "OTHER_ERROR"


def apply_window(events: List[Dict[str, Any]], capability: str) -> List[Dict[str, Any]]:
    if capability in {"snapshot", "event"} or capability not in WINDOW_CAPABILITIES:
        return events
    if capability == "live_scores":
        return [row for row in events if row.get("status") == "live"]
    if capability == "results":
        return [row for row in events if row.get("status") == "finished"]
    if capability == "fixtures":
        return [row for row in events if row.get("status") != "finished"]
    return events


def _events_from_json(payload: Any, competition_id: str) -> List[Dict[str, Any]]:
    events = walk_json_events(payload)
    if events:
        for event in events:
            event.setdefault("competition", competition_id)
        return events
    rows: List[Any] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("events", "matches", "Results", "games", "data", "items", "meetings"):
            if isinstance(payload.get(key), list):
                rows = payload.get(key) or []
                break
    events = []
    for index, row in enumerate(rows[:80]):
        if not isinstance(row, dict):
            continue
        home = row.get("home") or row.get("homeTeam") or row.get("team1") or row.get("radiant_name")
        away = row.get("away") or row.get("awayTeam") or row.get("team2") or row.get("dire_name")
        if isinstance(home, dict):
            home_name = home.get("name") or home.get("Name") or ""
        else:
            home_name = str(home or "")
        if isinstance(away, dict):
            away_name = away.get("name") or away.get("Name") or ""
        else:
            away_name = str(away or "")
        if not home_name and not away_name:
            continue
        events.append(
            {
                "id": str(row.get("id") or row.get("matchId") or f"{competition_id}:{index}"),
                "home": {"name": home_name},
                "away": {"name": away_name},
                "status": row.get("status") or "scheduled",
                "score": row.get("score") if isinstance(row.get("score"), dict) else {},
                "start_time": row.get("start_time") or row.get("date") or row.get("startTime"),
                "venue": row.get("venue"),
                "competition": competition_id,
            }
        )
    return events


class GenericHttpAdapter:
    adapter_key = "generic-http"

    def __init__(self, source_id: str = "generic-http", getter=None, text_getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        config = request.source_config or {}
        url = (config.get("url") or "").strip()
        if not url:
            return FetchResult(
                ok=False,
                http_status=0,
                error="no verified URL configured",
                classification="CONFIG_MISSING",
                config_missing=True,
                parse_status="skipped",
            )
        json_urls = [item for item in (config.get("json_urls") or []) if item]
        method = str(config.get("source_type") or "")
        host = urlparse(url).netloc.lower()
        if json_urls:
            events: List[Dict[str, Any]] = []
            last_json = None
            for extra_url in json_urls[:4]:
                last_json = self._get(extra_url)
                if last_json.ok and isinstance(last_json.payload, (dict, list)):
                    events = self._json_family(extra_url, last_json.payload, request)
                    if events:
                        latency = int((time.perf_counter() - started) * 1000)
                        out = FetchResult(
                            ok=True,
                            http_status=last_json.http_status or 200,
                            payload=last_json.payload,
                            events=apply_window(events, request.capability),
                            latency_ms=latency,
                            parse_status="ok",
                        )
                        out.classification = classify_http(out)
                        return out
            if last_json is not None and not last_json.ok and last_json.restricted:
                last_json.latency_ms = int((time.perf_counter() - started) * 1000)
                last_json.classification = classify_http(last_json)
                return last_json
        if "JSON" in method or url.lower().endswith(".json") or "/api/" in url.lower() or host.startswith("api."):
            result = self._get(url)
        else:
            result = self._get_text(url)
        latency = int((time.perf_counter() - started) * 1000)
        if not result.ok:
            result.latency_ms = latency
            result.classification = classify_http(result)
            return result
        events: List[Dict[str, Any]] = []
        parse_status = "ok"
        payload = result.payload
        try:
            if isinstance(payload, (dict, list)):
                events = self._json_family(url, payload, request)
            elif isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    events = self._json_family(url, parsed, request)
                    payload = parsed
                except (TypeError, ValueError):
                    if "<html" in payload.lower() or "<!doctype" in payload.lower() or "<table" in payload.lower():
                        events = self._html_family(payload, url, request)
                    elif payload.strip()[:1] in {"{", "["}:
                        parse_status = "failed"
                        result = FetchResult(
                            ok=False,
                            http_status=result.http_status,
                            error="malformed json",
                            payload=payload[:300],
                            parse_status=parse_status,
                            latency_ms=latency,
                            classification="PARSE_FAILURE",
                        )
                        return result
        except Exception as exc:  # noqa: BLE001 — keep diagnostics, do not swallow as empty
            return FetchResult(
                ok=False,
                http_status=result.http_status or 200,
                error=f"{type(exc).__name__}: {exc}",
                payload=str(payload)[:300] if payload is not None else None,
                parse_status="failed",
                latency_ms=latency,
                classification="OTHER_ERROR",
            )
        events = apply_window(events, request.capability)
        empty_reason = None
        if not events:
            sample = payload if isinstance(payload, str) else ""
            if isinstance(payload, (dict, list)):
                empty_reason = "SOURCE_HEALTHY_NO_EVENTS"
            elif "table" in sample.lower() or "fixture" in sample.lower() or "score" in sample.lower():
                empty_reason = "PARSER_COULD_NOT_EXTRACT"
            else:
                empty_reason = "SOURCE_HEALTHY_NO_EVENTS"
        out = FetchResult(
            ok=True,
            http_status=result.http_status or 200,
            payload=payload if not isinstance(payload, str) else payload[:2000],
            events=events,
            latency_ms=latency,
            parse_status=parse_status,
            empty_reason=empty_reason,
        )
        out.classification = classify_http(out)
        return out

    def _json_family(self, url: str, payload: Any, request: FetchRequest) -> List[Dict[str, Any]]:
        competition_id = request.competition_id or ""
        host = urlparse(url).netloc.lower()
        if "motogp.pulselive.com" in host:
            return self._motogp_events(url, payload, competition_id)
        if "espn.com" in host:
            from collector.adapters_espn import parse_espn_scoreboard

            espn_events = parse_espn_scoreboard(payload)
            if espn_events:
                return espn_events
        return _events_from_json(payload, competition_id)

    def _motogp_events(self, url: str, payload: Any, competition_id: str) -> List[Dict[str, Any]]:
        events = walk_json_events(payload)
        if events:
            for event in events:
                event.setdefault("competition", competition_id)
                event.setdefault("event_family", "motorsport_race")
            return events
        if not isinstance(payload, list) or not payload:
            return []
        current = None
        for row in payload:
            if isinstance(row, dict) and row.get("current"):
                current = row
                break
        if current is None:
            years = [row for row in payload if isinstance(row, dict) and row.get("year")]
            current = max(years, key=lambda row: int(row.get("year") or 0), default=None)
        season_id = (current or {}).get("id") if isinstance(current, dict) else None
        if not season_id:
            return []
        events_url = f"https://api.motogp.pulselive.com/motogp/v1/events?seasonUuid={season_id}"
        extra = self._get(events_url)
        if not extra.ok:
            # already-public results calendar used by the same family
            extra = self._get(f"https://api.motogp.pulselive.com/motogp/v1/results/events?seasonUuid={season_id}")
        if not extra.ok:
            return []
        mapped = walk_json_events(extra.payload)
        for event in mapped:
            event.setdefault("competition", competition_id)
            event.setdefault("event_family", "motorsport_race")
        return mapped

    def _html_family(self, html: str, url: str, request: FetchRequest) -> List[Dict[str, Any]]:
        hosted = events_for_host(html, url)
        events = list(hosted or [])
        config = request.source_config or {}
        for extra_url in list(config.get("html_urls") or [])[:3]:
            if extra_url == url or not extra_url:
                continue
            try:
                extra = self._get_text(extra_url, timeout=12)
            except TypeError:
                extra = self._get_text(extra_url)
            if not extra.ok or not isinstance(extra.payload, str):
                continue
            events.extend(events_for_host(extra.payload, extra_url) or parse_html(extra.payload, extra_url))
        if events:
            return events
        events = parse_html(html, url)
        if events:
            return events
        from collector.http import budget_remaining

        seen = set()
        family = request.upstream_family or ""
        max_links = 3 if family in {
            "bbc-sport",
            "espn-html",
            "nba-web",
            "wnba-web",
            "nrl-web",
            "abc-sport",
            "cyclingnews",
            "uci-web",
            "aso-letour",
            "lnr-web",
            "afc-web",
            "caf-web",
            "conmebol-web",
            "a-league-web",
            "nwsl-web",
            "usl-web",
            "acb-web",
            "hbl-web",
            "allsvenskan-web",
            "denmark-superliga-web",
            "superliga-web",
            "futbalnet",
            "tophaandbold-web",
            "netball-australia-web",
            "ibu-web",
            "sporting-life",
            "tournamentsoftware",
            "rankedin",
            "click-tt",
            "world-lacrosse-web",
            "hra-natsite",
            "standardbred-canada-web",
            "gri-web",
        } else 2
        for extra_url in list(fixture_urls(html, url))[:max_links]:
            if extra_url in seen or not budget_remaining():
                continue
            seen.add(extra_url)
            try:
                extra = self._get_text(extra_url, timeout=8)
            except TypeError:
                extra = self._get_text(extra_url)
            if not extra.ok or not isinstance(extra.payload, str):
                continue
            events.extend(events_for_host(extra.payload, extra_url) or parse_html(extra.payload, extra_url))
            if events:
                break
        if events:
            return events
        if family in {"tournamentsoftware", "rankedin", "click-tt"}:
            events.extend(self._follow_tournament_ids(html, url, request, seen))
            if events:
                return events
        for extra_url in list(_next_json_urls(html, url)) + list(_same_host_json_urls(html, url)[:4]):
            if extra_url in seen or not budget_remaining():
                continue
            seen.add(extra_url)
            extra = self._get(extra_url)
            if extra.ok and isinstance(extra.payload, (dict, list)):
                events.extend(_events_from_json(extra.payload, request.competition_id or ""))
                if events:
                    return events
        return self._html_events(html, request.competition_id or "")

    def _follow_tournament_ids(
        self, html: str, url: str, request: FetchRequest, seen: set
    ) -> List[Dict[str, Any]]:
        from collector.http import budget_remaining

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        family = request.upstream_family or ""
        follow: List[str] = []
        if family == "tournamentsoftware":
            ids = re.findall(r"[?&]id=([0-9A-Fa-f-]{8,})", html or "")[:4]
            for tid in ids:
                follow.append(f"{origin}/sport/matches?id={tid}")
                follow.append(f"{origin}/sport/draw?id={tid}")
        elif family == "rankedin":
            ids = re.findall(r"/[Tt]ournament(?:s)?/(\d+)", html or "")[:4]
            ids += re.findall(r"[?&](?:tournamentId|drawId)=(\d+)", html or "")[:4]
            for tid in dict.fromkeys(ids):
                follow.append(f"{origin}/Public/Tournament/{tid}")
                follow.append(f"{origin}/public/draws/{tid}")
        else:
            ids = re.findall(r"(?:championship|competition|meeting|turnier)=(\d+)", html or "", re.I)[:4]
            for tid in ids:
                follow.append(f"{origin}/clicktt/spielbericht?championship={tid}")
                follow.append(f"{origin}/spielbericht?competition={tid}")
        events: List[Dict[str, Any]] = []
        for extra_url in follow[:6]:
            if extra_url in seen or not budget_remaining():
                continue
            seen.add(extra_url)
            extra = self._get_text(extra_url)
            if not extra.ok or not isinstance(extra.payload, str):
                continue
            events.extend(events_for_host(extra.payload, extra_url) or parse_html(extra.payload, extra_url))
            if not events:
                events.extend(self._html_events(extra.payload, request.competition_id or ""))
            if events:
                break
        return events

    def _html_events(self, html: str, competition_id: str) -> List[Dict[str, Any]]:
        events = []
        sample = re.sub(r"<[^>]+>", " ", html)
        sample = re.sub(r"\s+", " ", sample)
        for index, match in enumerate(SCORE_RE.finditer(sample[:20000])):
            groups = match.groups()
            if len(groups) < 4:
                continue
            try:
                home_score = int(groups[1])
                away_score = int(groups[2])
            except (TypeError, ValueError):
                continue
            events.append(
                {
                    "id": f"{self.source_id}:{competition_id}:{index}",
                    "home": {"name": str(groups[0]).strip()},
                    "away": {"name": str(groups[3]).strip()},
                    "status": "finished",
                    "score": {"home": home_score, "away": away_score},
                    "competition": competition_id,
                }
            )
            if len(events) >= 25:
                break
        return events


def _registrable(host: str) -> str:
    host = (host or "").lower().replace("www.", "")
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "gov", "ac", "or"}:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _next_json_urls(html: str, base_url: str) -> List[str]:
    from collector.html_parse import NEXT_RE

    match = NEXT_RE.search(html or "")
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return []
    build = payload.get("buildId") if isinstance(payload, dict) else None
    if not build:
        return []
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/") or ""
    urls = []
    if path:
        urls.append(f"{origin}/_next/data/{build}{path}.json")
    page = str((payload.get("page") if isinstance(payload, dict) else "") or "").rstrip("/")
    if page:
        urls.append(f"{origin}/_next/data/{build}{page}.json")
    return list(dict.fromkeys(urls))


def _same_host_json_urls(html: str, base_url: str) -> List[str]:
    host = urlparse(base_url).netloc.lower()
    base_reg = _registrable(host)
    found = []
    for match in re.finditer(r"https?://[^\s\"'<>]+", html or "", re.I):
        link = match.group(0).rstrip(").,]")
        parsed = urlparse(link)
        if _registrable(parsed.netloc) != base_reg:
            continue
        path = (parsed.path or "").lower()
        if "/api/" in path or path.endswith(".json") or "scoreboard" in path or "fixtures" in path or "schedule" in path:
            found.append(link)
        if len(found) >= 6:
            break
    for match in re.finditer(r"[\"'](/api/[^\"']+)[\"']", html or "", re.I):
        found.append(urlparse(base_url).scheme + "://" + urlparse(base_url).netloc + match.group(1))
        if len(found) >= 8:
            break
    return list(dict.fromkeys(found))


class PulseLiveFamilyAdapter:
    """World Rugby RIMS JSON. MotoGP uses the same family with generic-http + config URL."""

    adapter_key = "pulselive-family"

    def __init__(self, source_id: str = "pulselive", getter=None):
        from collector.adapters_feeds import WorldRugbyAdapter

        self.source_id = source_id
        self._inner = WorldRugbyAdapter(source_id=source_id, getter=getter or fetch_url)

    def fetch(self, request: FetchRequest) -> FetchResult:
        return self._inner.fetch(request)

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)
