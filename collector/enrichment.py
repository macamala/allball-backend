"""Safe enrichment helpers. Map fields already present on fetched payloads.

Does not call upstream. Does not invent scores, incidents, or participants.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

DETAIL_ONLY_KEYS = {
    "classification",
    "athletes",
    "runners",
    "leaderboard",
    "maps",
    "bracket",
    "incidents",
    "lineups",
    "statistics",
    "player_statistics",
    "form",
    "disciplines",
    "officials",
    "innings",
    "h2h",
}

# Copied onto a canonical keeper from collapsed observations. Never includes
# competition, participant identity, start_precision, or score.
OBSERVATION_ENRICH_KEYS = (
    "periods",
    "incidents",
    "maps",
    "runners",
    "classification",
    "leaderboard",
    "form",
    "best_of",
    "winner",
    "round",
    "bracket",
    "attendance",
    "referee",
    "innings",
    "officials",
    "player_statistics",
    "lineups",
    "statistics",
    "trap",
    "race_number",
    "serving",
    "current_set",
)

EXTRA_PERSIST_KEYS = (
    "race_number",
    "tournament",
    "round",
    "parent_sport_id",
    "country_based",
    "athletes",
    "periods",
    "maps",
    "best_of",
    "classification",
    "runners",
    "leaderboard",
    "bracket",
    "form",
    "race_name",
    "trap",
    "referee",
    "attendance",
    "officials",
    "player_statistics",
    "incidents",
    "lineups",
    "statistics",
    "h2h",
    "serving",
    "current_set",
    "innings",
    "source_family",
    "timezone",
    "source_timezone",
    "source_local_datetime",
    "timezone_resolution_method",
    "start_precision",
    "start_date",
    "result_type",
    "winner",
    "walkover",
    "forfeit",
    "tournament_id",
    "tournament_name",
    "surface",
    "category",
    "location",
    "source_status",
    "source_event_updated_at",
    "source_fetch_time",
    "last_contact_at",
    "canonical_last_observed_at",
    "status_reconciliation",
    "observed_at",
    "quality_flags",
    "display_eligible",
    "identity_confidence",
    "source_competition_name",
    "source_competition_id",
    "canonical_competition_id",
    "resolution_method",
    "resolution_confidence",
    "orientation_conflict",
    "status_inferred",
    "live_class",
    "provider_conflicts",
    "fetch_started_at",
    "fetch_completed_at",
    "parsed_at",
    "persisted_at",
    "canonical_updated_at",
    "field_freshness",
    "source_event_id",
    "source_event_ids",
)

_DATE = re.compile(
    r"^(\d{1,2}[./]\s*\d{1,2}[./]\s*\d{2,4}(\s+\d{1,2}:\d{2})?|"
    r"\d{4}-\d{2}-\d{2}([ T]\d{1,2}:\d{2}(:\d{2})?)?|"
    r"\d{1,2}\s+\w+\s+\d{4})$"
)
_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?(\s*(am|pm))?$", re.I)
_SCORE = re.compile(r"^\d{1,3}\s*[-–:/]\s*\d{1,3}$")
_HTML = re.compile(r"<[^>]+>")
_URL = re.compile(r"https?://|www\.", re.I)
_HEADING = re.compile(
    r"^(home|away|team|date|time|versus|vs|score|played|pts|table|standings|fixtures)$",
    re.I,
)


def quality_flags_for_name(name: Optional[str]) -> List[str]:
    raw = str(name or "").strip()
    if not raw:
        return ["empty_name"]
    flags: List[str] = []
    if _HTML.search(raw):
        flags.append("html_in_name")
    if _URL.search(raw):
        flags.append("url_in_name")
    compact = re.sub(r"\s+", " ", raw)
    if _DATE.match(compact):
        flags.append("name_is_date")
    if _TIME.match(compact):
        flags.append("name_is_time")
    if _SCORE.match(compact):
        flags.append("name_is_score")
    if _HEADING.match(compact):
        flags.append("generic_heading")
    return flags


def quality_flags_for_event(event: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    for key in ("home", "away", "participant_a", "participant_b"):
        side = event.get(key) or {}
        name = side.get("name") if isinstance(side, dict) else side
        for flag in quality_flags_for_name(name if isinstance(name, str) else ""):
            labeled = f"{key}:{flag}"
            if labeled not in flags:
                flags.append(labeled)
    sport = str(event.get("sport") or "")
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    if sport in {"football", "soccer"}:
        try:
            home_s = int(score.get("home"))
            away_s = int(score.get("away"))
        except (TypeError, ValueError):
            home_s = away_s = None
        if home_s is not None and away_s is not None and home_s > 15 and away_s > 15:
            flags.append("implausible_football_score")
    return flags


def is_display_eligible(event: Dict[str, Any]) -> bool:
    if event.get("display_eligible") is False:
        return False
    blocking = {"name_is_date", "name_is_time", "name_is_score", "html_in_name", "generic_heading", "url_in_name", "implausible_football_score"}
    for flag in quality_flags_for_event(event):
        kind = flag.split(":", 1)[-1]
        if kind in blocking:
            return False
    return True


def _section_filled(value: Any) -> bool:
    if value is None or value == "" or value == {} or value == []:
        return False
    return True


def stamp_provenance(section: Any, *, source_family: str, source_event_id: Optional[str] = None) -> Any:
    if not isinstance(section, dict):
        return section
    if section.get("provenance"):
        return section
    section["provenance"] = {
        "source_family": source_family,
        "source_event_id": source_event_id,
        "fetched_at": None,
        "freshness": None,
        "confidence": None,
    }
    return section


def copy_missing_enrichment(destination: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """Fill empty enrichment sections only. Never overwrite real zeros or existing lists."""
    out = dict(destination)
    for key in OBSERVATION_ENRICH_KEYS:
        if not _section_filled(out.get(key)) and _section_filled(source.get(key)):
            out[key] = source.get(key)
    return out


_OPENLIGA_PERIOD = {
    "HalfTime": ("HT", "HT"),
    "After90Minutes": ("FT", "FT"),
    "AfterExtraTime": ("ET", "ET"),
    "AfterPenaltyShootout": ("PEN", "PEN"),
    "AfterPenalty": ("PEN", "PEN"),
}


def _period_code(sport: str, label: Any, index: int) -> tuple[Any, str]:
    raw = str(label if label is not None else index + 1).strip()
    sport = (sport or "").lower()
    upper = raw.upper()
    if sport in {"basketball"}:
        if upper in {"OT", "OT1", "OT2", "OT3"} or upper.startswith("OT"):
            return raw, upper if upper.startswith("OT") else f"OT{raw}"
        try:
            number = int(raw)
        except ValueError:
            return raw, raw
        if number >= 5:
            return number, f"OT{number - 4}"
        return number, f"Q{number}"
    if sport in {"ice-hockey", "hockey"}:
        if upper in {"SO", "SHOOTOUT"}:
            return "SO", "SO"
        if upper in {"OT", "OT1"}:
            return "OT", "OT"
        try:
            number = int(raw)
        except ValueError:
            return raw, raw
        if number >= 4:
            return number, "OT"
        return number, f"P{number}"
    if sport in {"baseball"}:
        try:
            number = int(raw)
        except ValueError:
            return raw, str(raw)
        return number, str(number)
    if sport in {"tennis"}:
        try:
            number = int(raw)
        except ValueError:
            number = index + 1
        return number, f"Set {number}"
    return raw, str(raw)


def periods_from_espn_lnescrs(lnescrs: Any, *, sport: str = "") -> Optional[List[Dict[str, Any]]]:
    """ESPN HTML __espnfitt__ uses event.lnescrs {hme, awy, lbls}, not competitor.linescores."""
    if not isinstance(lnescrs, dict):
        return None
    labels = lnescrs.get("lbls") or lnescrs.get("labels") or []
    if isinstance(labels, list) and labels:
        tokens = [str(item).upper() for item in labels]
        if tokens == ["R", "H", "E"] or set(tokens) <= {"R", "H", "E"}:
            return None
    home_rows = lnescrs.get("hme") or lnescrs.get("home") or []
    away_rows = lnescrs.get("awy") or lnescrs.get("away") or []
    if not isinstance(home_rows, list) or not isinstance(away_rows, list):
        return None
    if not home_rows and not away_rows:
        return None
    length = max(len(home_rows), len(away_rows), len(labels) if isinstance(labels, list) else 0)
    out: List[Dict[str, Any]] = []
    for index in range(length):
        label = labels[index] if isinstance(labels, list) and index < len(labels) else index + 1
        number, code = _period_code(sport, label, index)
        home_val = home_rows[index] if index < len(home_rows) else None
        away_val = away_rows[index] if index < len(away_rows) else None
        if home_val is None and away_val is None:
            continue
        try:
            if home_val is not None:
                home_val = int(home_val)
        except (TypeError, ValueError):
            pass
        try:
            if away_val is not None:
                away_val = int(away_val)
        except (TypeError, ValueError):
            pass
        out.append(
            {
                "number": number,
                "period": number,
                "code": code,
                "label": code,
                "home": home_val,
                "away": away_val,
            }
        )
    return out or None


def rhe_from_espn_lnescrs(lnescrs: Any) -> Dict[str, Any]:
    if not isinstance(lnescrs, dict):
        return {}
    labels = [str(item).upper() for item in (lnescrs.get("lbls") or [])]
    if labels != ["R", "H", "E"]:
        return {}
    home = lnescrs.get("hme") or []
    away = lnescrs.get("awy") or []
    out: Dict[str, Any] = {}
    if len(home) >= 3 or len(away) >= 3:
        out["hits"] = {"home": home[1] if len(home) > 1 else None, "away": away[1] if len(away) > 1 else None}
        out["errors"] = {"home": home[2] if len(home) > 2 else None, "away": away[2] if len(away) > 2 else None}
    return out


def periods_from_linescores(home: Dict[str, Any], away: Dict[str, Any], *, sport: str = "") -> Optional[List[Dict[str, Any]]]:
    home_rows = home.get("linescores") if isinstance(home, dict) else None
    away_rows = away.get("linescores") if isinstance(away, dict) else None
    if not isinstance(home_rows, list) or not isinstance(away_rows, list):
        return None
    if not home_rows and not away_rows:
        return None
    length = max(len(home_rows), len(away_rows))
    out: List[Dict[str, Any]] = []
    for index in range(length):
        left = home_rows[index] if index < len(home_rows) else {}
        right = away_rows[index] if index < len(away_rows) else {}
        if not isinstance(left, dict):
            left = {"value": left}
        if not isinstance(right, dict):
            right = {"value": right}
        number = left.get("period") or right.get("period") or index + 1
        home_val = left.get("value") if left.get("value") is not None else left.get("displayValue")
        away_val = right.get("value") if right.get("value") is not None else right.get("displayValue")
        _number, code = _period_code(sport, number, index)
        out.append(
            {
                "number": number,
                "period": number,
                "code": code,
                "label": code,
                "home": home_val,
                "away": away_val,
                "tiebreak_home": None,
                "tiebreak_away": None,
            }
        )
    return out or None


def incidents_from_openliga_goals(match: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    rows = match.get("goals") or []
    if not isinstance(rows, list) or not rows:
        return None
    incidents: List[Dict[str, Any]] = []
    for goal in rows:
        if not isinstance(goal, dict):
            continue
        kind = "goal"
        if goal.get("isPenalty"):
            kind = "penalty_goal"
        elif goal.get("isOwnGoal"):
            kind = "own_goal"
        minute = goal.get("matchMinute")
        period = None
        if isinstance(minute, int):
            period = "2" if minute > 45 else "1"
        incidents.append(
            {
                "type": kind,
                "period": period,
                "minute": minute,
                "stoppage": None,
                "participant": None,
                "player": goal.get("goalGetterName"),
                "secondary_player": None,
                "assist": None,
                "score_after": {"home": goal.get("scoreTeam1"), "away": goal.get("scoreTeam2")},
                "detail": None,
                "provenance": {"source_family": "openligadb", "source_event_id": str(match.get("matchID") or "")},
            }
        )
    return incidents or None


def periods_from_openliga_results(match: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    rows = match.get("matchResults") or []
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("resultTypeKind") or "")
        code, label = _OPENLIGA_PERIOD.get(kind, (kind or row.get("resultName"), row.get("resultName") or kind))
        out.append(
            {
                "code": code,
                "label": label,
                "number": row.get("resultOrderID") or row.get("resultTypeID"),
                "home": row.get("pointsTeam1"),
                "away": row.get("pointsTeam2"),
            }
        )
    return out or None


def periods_from_wta_sets(row: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    from collector.wta_orientation import periods_from_score_sets

    return periods_from_score_sets(row) or None


def competitor_name(node: Any) -> str:
    if not isinstance(node, dict):
        return str(node or "")
    athlete = node.get("athlete") if isinstance(node.get("athlete"), dict) else {}
    team = node.get("team") if isinstance(node.get("team"), dict) else {}
    return (
        athlete.get("displayName")
        or athlete.get("fullName")
        or team.get("displayName")
        or team.get("name")
        or node.get("displayName")
        or node.get("name")
        or ""
    )
