"""Reject parsed objects that are not plausible canonical events."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_BAD_TOKENS = (
    "cookie",
    "subscribe",
    "function ",
    "weather",
    "full calendar",
    "estimated purse",
    "arrow_drop",
    "like us",
    "searchtab",
    "todos",
    "gols vs",
    "rank vs",
    "event #",
    "tune in",
    "hungarian capital",
    "javascript",
    "document.getelementbyid",
    "start list",
    "dive list",
    "detailed results",
)

_NATIONAL_TEAM_SPORTS = {"football"}

INDIVIDUAL_SPORTS = {
    "winter-sports",
    "swimming",
    "cycling",
    "golf",
    "horse-racing",
    "greyhound-racing",
    "harness-racing",
    "motorsport",
    "athletics",
}

INDIVIDUAL_FAMILIES = {"racing", "motorsport_race", "individual", "tournament"}

TEAM_MATCH = "TEAM_MATCH"
HEAD_TO_HEAD = "HEAD_TO_HEAD"
RACE = "RACE"
MEET = "MEET"
TOURNAMENT = "TOURNAMENT"
BRACKET = "BRACKET"
MULTI_EVENT_MEET = "MULTI_EVENT_MEET"

EVENT_TYPE_BY_COMPETITION = {
    "nrl": TEAM_MATCH,
    "italy-superlega": TEAM_MATCH,
    "nordic-water-polo-league": TEAM_MATCH,
    "world-lacrosse": TEAM_MATCH,
    "fih-eurohockey": TEAM_MATCH,
    "brazil-lnf": TEAM_MATCH,
    "fifa-futsal-when-listed": TEAM_MATCH,
    "futsalplanet-leagues-cups": TEAM_MATCH,
    "uefa-futsal-champions-league": TEAM_MATCH,
    "mexico-lnbp": TEAM_MATCH,
    "germany-handball-bundesliga": TEAM_MATCH,
    "ettu-events": HEAD_TO_HEAD,
    "bwf-and-national-events": HEAD_TO_HEAD,
    "indonesia-open": HEAD_TO_HEAD,
    "national-and-club": HEAD_TO_HEAD,
    "all-england-open": HEAD_TO_HEAD,
    "germany-click-tt": TEAM_MATCH,
    "uci-calendar": RACE,
    "tour-de-france": RACE,
    "biathlon": RACE,
    "formula-2": RACE,
    "formula-3": RACE,
    "bha-meetings": MEET,
    "gbgb-meetings": MEET,
    "ireland-gri-meetings": MEET,
    "irish-greyhound-derby": RACE,
    "nsw-hrnsw-meetings": MEET,
    "canada-standardbred-meetings": MEET,
    "france-letrot-meetings": MEET,
    "usa-usta-meetings": MEET,
    "korean-golf-tour": TOURNAMENT,
    "rlcs": BRACKET,
    "vct": BRACKET,
    "tier1": BRACKET,
    "worlds-msi-regional": BRACKET,
    "lol-world-championship": BRACKET,
    "owcs-historical": BRACKET,
    "owcs-world-finals": BRACKET,
    "cross-game-brackets": BRACKET,
    "cross-game-wiki": BRACKET,
    "wa-calendar": MULTI_EVENT_MEET,
    "world-aquatics-events": MULTI_EVENT_MEET,
    "world-aquatics-meets": MULTI_EVENT_MEET,
}

EVENT_TYPE_BY_SPORT = {
    "football": TEAM_MATCH,
    "futsal": TEAM_MATCH,
    "handball": TEAM_MATCH,
    "volleyball": TEAM_MATCH,
    "water-polo": TEAM_MATCH,
    "lacrosse": TEAM_MATCH,
    "hockey": TEAM_MATCH,
    "field-hockey": TEAM_MATCH,
    "basketball": TEAM_MATCH,
    "rugby-league": TEAM_MATCH,
    "rugby": TEAM_MATCH,
    "netball": TEAM_MATCH,
    "tennis": HEAD_TO_HEAD,
    "badminton": HEAD_TO_HEAD,
    "table-tennis": HEAD_TO_HEAD,
    "cycling": RACE,
    "winter-sports": RACE,
    "motorsport": RACE,
    "horse-racing": MEET,
    "greyhound-racing": MEET,
    "harness-racing": MEET,
    "golf": TOURNAMENT,
    "athletics": MULTI_EVENT_MEET,
    "swimming": MULTI_EVENT_MEET,
}


def event_type_for(competition_id: str = "", sport_id: str = "") -> str:
    return EVENT_TYPE_BY_COMPETITION.get(competition_id) or EVENT_TYPE_BY_SPORT.get(sport_id) or TEAM_MATCH


def _name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "").strip()
    return str(side or "").strip()


def split_fixture(text: str) -> Optional[tuple[str, str]]:
    blob = (text or "").strip()
    if " vs " not in blob.lower() and " v " not in blob.lower():
        return None
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", blob, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    home, away = parts[0].strip(" :-"), parts[1].strip(" :-")
    if not home or not away:
        return None
    return home, away


def _has_word_letters(name: str) -> bool:
    text = name or ""
    if re.search(r"[A-Za-z]{3}", text):
        return True
    return bool(re.search(r"(?u)[^\W\d_]{3}", text))


def reject_reason(
    event: Dict[str, Any],
    *,
    sport_id: str = "",
    competition_id: str = "",
) -> Optional[str]:
    home = _name(event.get("home"))
    away = _name(event.get("away"))
    family = str(event.get("event_family") or "")
    kind = str(event.get("event_type") or event_type_for(competition_id, sport_id))
    individual = sport_id in INDIVIDUAL_SPORTS or family in INDIVIDUAL_FAMILIES or kind in {RACE, MEET, TOURNAMENT, MULTI_EVENT_MEET}
    if (not home or not away) and event.get("competition"):
        parsed = split_fixture(str(event.get("competition") or event.get("name") or ""))
        if parsed:
            home, away = parsed
    if individual and home and not away:
        away = _name(event.get("venue") or event.get("event") or event.get("competition") or event.get("discipline") or "field")
    if not home:
        return "missing_participants"
    if kind in {TEAM_MATCH, HEAD_TO_HEAD, BRACKET} and not away:
        return "missing_participants"
    if kind in {RACE, MEET, TOURNAMENT, MULTI_EVENT_MEET} and not away:
        away = _name(event.get("venue") or event.get("classification") or event.get("discipline") or "result")
    lowered = f"{home} {away} {competition_id} {sport_id}".lower()
    if any(token in lowered for token in _BAD_TOKENS):
        return "placeholder_navigation_row"
    if kind == TEAM_MATCH and any(
        token in lowered
        for token in ("filly", "colt", "full calendar", "gols vs", "weather vs", "off time")
    ):
        return "placeholder_navigation_row"
    word_limit = 20 if kind in {RACE, MEET, MULTI_EVENT_MEET, TOURNAMENT} else (16 if individual else 8)
    if len(home.split()) > word_limit or len((away or "").split()) > word_limit:
        return "unsupported_event_shape"
    if away and home.lower() == away.lower() and kind in {TEAM_MATCH, HEAD_TO_HEAD, BRACKET}:
        return "unsupported_event_shape"
    if not _has_word_letters(home):
        return "parser_extraction_error"
    if away and kind in {TEAM_MATCH, HEAD_TO_HEAD, BRACKET} and not _has_word_letters(away):
        return "parser_extraction_error"
    if sport_id == "futsal" and competition_id.startswith("fifa-futsal"):
        if any(token in lowered for token in ("levadia", "tammeka", "premier league", "serie a")):
            return "invalid_competition"
    if competition_id in {"serbia-superliga", "slovakia-super-liga"} and sport_id in _NATIONAL_TEAM_SPORTS:
        if home.lower() in {"serbia", "slovakia"} or away.lower() in {"serbia", "slovakia", "greece", "netherlands", "germany", "moldova", "kazakhstan"}:
            return "invalid_competition"
    if competition_id == "france-top-14" and any(token in lowered for token in ("benetton", "dragons", "stormers", "hurricanes")):
        return "invalid_competition"
    start = str(event.get("start_time") or event.get("date") or "")
    if start and not re.search(r"\d{4}", start):
        return "invalid_date"
    if kind in {RACE, MEET, TOURNAMENT, MULTI_EVENT_MEET} and away.lower() in {"race", "local", "news", "filly", "colt", "sex", "vs", "rider", "rank", "f. c.", "field"}:
        if kind != MEET:
            return "unsupported_event_shape"
        if away.lower() in {"filly", "colt", "news", "f. c."}:
            return "placeholder_navigation_row"
    return None


def event_is_valid(
    event: Dict[str, Any],
    *,
    sport_id: str = "",
    competition_id: str = "",
) -> bool:
    return reject_reason(event, sport_id=sport_id, competition_id=competition_id) is None
