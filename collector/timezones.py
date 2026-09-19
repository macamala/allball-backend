"""Resolve naive source datetimes without silently assuming UTC."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATE_ONLY = "DATE_ONLY"
EXACT_TIME = "EXACT_TIME"
UNKNOWN_PRECISION = "UNKNOWN"

TIMEZONE_UNKNOWN = "TIMEZONE_UNKNOWN"

PROVIDER_UTC_CONTRACT = {
    "openligadb",
    "fifa-json",
    "fifa-digital",
    "nhl-web",
    "mlb-statsapi",
    "khl-mobile",
    "espn-html",
}

IANA_BY_COMPETITION = {
    "germany-bundesliga": "Europe/Berlin",
    "germany-2-bundesliga": "Europe/Berlin",
    "germany-3-liga": "Europe/Berlin",
    "germany-dfb-pokal": "Europe/Berlin",
    "germany-frauen-bundesliga": "Europe/Berlin",
    "germany-del": "Europe/Berlin",
    "germany-del2": "Europe/Berlin",
    "england-premier-league": "Europe/London",
    "england-championship": "Europe/London",
    "england-league-one": "Europe/London",
    "england-league-two": "Europe/London",
    "fa-cup": "Europe/London",
    "premiership-rugby": "Europe/London",
    "super-league": "Europe/London",
    "bha-meetings": "Europe/London",
    "spain-la-liga": "Europe/Madrid",
    "spain-acb": "Europe/Madrid",
    "italy-serie-a": "Europe/Rome",
    "italy-superlega": "Europe/Rome",
    "france-ligue-1": "Europe/Paris",
    "france-top-14": "Europe/Paris",
    "france-pro-d2": "Europe/Paris",
    "france-letrot-meetings": "Europe/Paris",
    "netherlands-eredivisie": "Europe/Amsterdam",
    "portugal-primeira-liga": "Europe/Lisbon",
    "belgium-pro-league": "Europe/Brussels",
    "austria-bundesliga": "Europe/Vienna",
    "switzerland-super-league": "Europe/Zurich",
    "turkey-super-lig": "Europe/Istanbul",
    "greece-super-league": "Europe/Athens",
    "poland-ekstraklasa": "Europe/Warsaw",
    "plusliga": "Europe/Warsaw",
    "czech-first-league": "Europe/Prague",
    "hungary-nb-i": "Europe/Budapest",
    "croatia-hnl": "Europe/Zagreb",
    "serbia-superliga": "Europe/Belgrade",
    "romania-superliga": "Europe/Bucharest",
    "bulgaria-first-league": "Europe/Sofia",
    "ukraine-premier-league": "Europe/Kyiv",
    "russia-premier-league": "Europe/Moscow",
    "denmark-superliga": "Europe/Copenhagen",
    "sweden-allsvenskan": "Europe/Stockholm",
    "sweden-shl": "Europe/Stockholm",
    "norway-eliteserien": "Europe/Oslo",
    "finland-liiga": "Europe/Helsinki",
    "scotland-premiership": "Europe/London",
    "ireland-premier-division": "Europe/Dublin",
    "irish-greyhound-derby": "Europe/Dublin",
    "albania-superliga": "Europe/Tirane",
    "bosnia-premier-liga": "Europe/Sarajevo",
    "argentina-primera": "America/Argentina/Buenos_Aires",
    "brazil-serie-a": "America/Sao_Paulo",
    "chile-primera": "America/Santiago",
    "mexico-liga-mx": "America/Mexico_City",
    "mls": "America/New_York",
    "nba": "America/New_York",
    "wnba": "America/New_York",
    "nhl": "America/New_York",
    "nfl": "America/New_York",
    "mlb": "America/New_York",
    "cfl": "America/Toronto",
    "nll": "America/New_York",
    "pll": "America/New_York",
    "australia-a-league": "Australia/Sydney",
    "australia-a-league-women": "Australia/Sydney",
    "australia-afl": "Australia/Melbourne",
    "nrl": "Australia/Sydney",
    "a-league": "Australia/Sydney",
    "japan-j1": "Asia/Tokyo",
    "npb": "Asia/Tokyo",
    "kbo": "Asia/Seoul",
    "china-super-league": "Asia/Shanghai",
    "korea-k-league": "Asia/Seoul",
    "saudi-pro-league": "Asia/Riyadh",
    "egypt-premier-league": "Africa/Cairo",
    "south-africa-psl": "Africa/Johannesburg",
    "africa-cup-of-nations": "Africa/Cairo",
    "cev-eurovolley-men": "Europe/Vienna",
    "uefa-champions-league": "Europe/Paris",
    "uefa-europa-league": "Europe/Paris",
    "uefa-conference-league": "Europe/Paris",
}

IANA_BY_COUNTRY = {
    "de": "Europe/Berlin",
    "england": "Europe/London",
    "uk": "Europe/London",
    "gb": "Europe/London",
    "es": "Europe/Madrid",
    "it": "Europe/Rome",
    "fr": "Europe/Paris",
    "nl": "Europe/Amsterdam",
    "pt": "Europe/Lisbon",
    "be": "Europe/Brussels",
    "at": "Europe/Vienna",
    "ch": "Europe/Zurich",
    "tr": "Europe/Istanbul",
    "gr": "Europe/Athens",
    "pl": "Europe/Warsaw",
    "cz": "Europe/Prague",
    "hu": "Europe/Budapest",
    "hr": "Europe/Zagreb",
    "rs": "Europe/Belgrade",
    "ro": "Europe/Bucharest",
    "bg": "Europe/Sofia",
    "ua": "Europe/Kyiv",
    "ru": "Europe/Moscow",
    "dk": "Europe/Copenhagen",
    "se": "Europe/Stockholm",
    "no": "Europe/Oslo",
    "fi": "Europe/Helsinki",
    "ie": "Europe/Dublin",
    "ar": "America/Argentina/Buenos_Aires",
    "br": "America/Sao_Paulo",
    "cl": "America/Santiago",
    "mx": "America/Mexico_City",
    "us": "America/New_York",
    "ca": "America/Toronto",
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
    "kr": "Asia/Seoul",
    "cn": "Asia/Shanghai",
    "sa": "Asia/Riyadh",
    "eg": "Africa/Cairo",
    "za": "Africa/Johannesburg",
}


@dataclass
class ResolvedTime:
    utc: Optional[datetime]
    source_local_datetime: Optional[str]
    source_timezone: Optional[str]
    method: str
    precision: str
    start_date: Optional[str]


def _zone(name: Optional[str]) -> Optional[ZoneInfo]:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None


def competition_timezone(competition_id: str = "", country_id: str = "") -> Optional[str]:
    if competition_id in IANA_BY_COMPETITION:
        return IANA_BY_COMPETITION[competition_id]
    return IANA_BY_COUNTRY.get((country_id or "").lower())


def _parse_raw(text: str) -> Optional[datetime]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def resolve_event_time(
    value: Any,
    *,
    competition_id: str = "",
    country_id: str = "",
    provider: str = "",
    source_timezone: Optional[str] = None,
    venue_timezone: Optional[str] = None,
) -> ResolvedTime:
    if isinstance(value, dict):
        value = value.get("iso") or value.get("utc") or value.get("isoDate") or value.get("date") or ""
    text = str(value or "").strip()
    if text.startswith("{") and "'iso':" in text:
        import ast

        try:
            blob = ast.literal_eval(text)
            if isinstance(blob, dict):
                text = str(blob.get("iso") or blob.get("isoDate") or text)
        except (ValueError, SyntaxError):
            found = re.search(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?", text)
            if found:
                text = found.group(0)
    if not text:
        return ResolvedTime(None, None, None, TIMEZONE_UNKNOWN, UNKNOWN_PRECISION, None)
    parsed = _parse_raw(text)
    date_part = text[:10] if len(text) >= 10 and text[4] == "-" else None
    date_only_shape = bool(date_part and "T" not in text)
    precision = DATE_ONLY if date_only_shape else (EXACT_TIME if parsed and "T" in text else UNKNOWN_PRECISION)

    if parsed and parsed.tzinfo is not None:
        utc = parsed.astimezone(timezone.utc)
        return ResolvedTime(
            utc,
            parsed.replace(tzinfo=None).isoformat(timespec="seconds"),
            str(parsed.tzinfo),
            "explicit_source_offset",
            precision,
            date_part,
        )

    tz_name = source_timezone or competition_timezone(competition_id, country_id) or venue_timezone
    method = "source_timezone" if source_timezone else (
        "competition_timezone" if competition_timezone(competition_id, country_id) else (
            "venue_timezone" if venue_timezone else None
        )
    )
    if tz_name is None and provider in PROVIDER_UTC_CONTRACT:
        tz_name = "UTC"
        method = "provider_documented_utc"
    if parsed is None:
        return ResolvedTime(None, text, None, TIMEZONE_UNKNOWN, precision, date_part)
    if tz_name:
        zone = _zone(tz_name)
        if zone is not None:
            local = parsed.replace(tzinfo=zone)
            return ResolvedTime(
                local.astimezone(timezone.utc),
                parsed.isoformat(timespec="seconds"),
                tz_name,
                method or "competition_timezone",
                precision,
                date_part,
            )
    return ResolvedTime(
        None,
        parsed.isoformat(timespec="seconds"),
        None,
        TIMEZONE_UNKNOWN,
        precision,
        date_part,
    )


def utc_naive_for_storage(resolved: ResolvedTime) -> Optional[datetime]:
    if resolved.utc is None:
        return None
    return resolved.utc.replace(tzinfo=None)


def iso_utc(resolved: ResolvedTime) -> Optional[str]:
    if resolved.precision == DATE_ONLY and resolved.start_date:
        return f"{resolved.start_date}T00:00:00Z"
    if resolved.utc is None:
        return None
    return resolved.utc.strftime("%Y-%m-%dT%H:%M:%SZ")
