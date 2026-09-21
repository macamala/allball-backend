"""Participant display/identity helpers. Diacritics stay on display names."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional

# ISO-2 codes used as BBC/ESPN flag abbreviations next to football clubs.
# Football name particles that collide with ISO codes are excluded (AS, US, AC, SK…).
_FLAG_CODES = {
    "GB",
    "IE",
    "CZ",
    "BR",
    "BE",
    "FR",
    "DE",
    "IT",
    "ES",
    "PT",
    "NL",
    "NO",
    "SE",
    "DK",
    "FI",
    "PL",
    "AT",
    "CH",
    "GR",
    "TR",
    "AR",
    "MX",
    "AU",
    "NZ",
    "JP",
    "KR",
    "CN",
    "QA",
    "AE",
    "EG",
    "MA",
    "UY",
    "PY",
    "CO",
    "CL",
    "PE",
    "EC",
    "VE",
    "BO",
    "CR",
    "PA",
    "CA",
    "ZA",
    "NG",
    "GH",
    "SN",
    "CM",
    "CI",
    "UA",
    "RU",
    "RS",
    "HR",
    "RO",
    "BG",
    "HU",
    "SI",
    "SK",
    "BA",
    "AL",
    "MK",
    "ME",
    "XK",
    "BY",
    "LT",
    "LV",
    "EE",
    "IS",
    "LU",
    "MT",
    "CY",
    "GE",
    "AM",
    "AZ",
    "IL",
    "SA",
    "TN",
    "DZ",
    "AO",
    "MZ",
    "ZW",
    "KE",
    "UG",
    "TZ",
    "IN",
    "ID",
    "TH",
    "VN",
    "MY",
    "SG",
    "PH",
    "HK",
    "TW",
    "CR",
}

_ABBR_TAG = re.compile(r"<abbr\b[^>]*>[^<]{1,3}</abbr>", re.I)
_FLAG_CLASS = re.compile(r"<[^>]+(?:gs-o-flag|sp-c-flag|flag--small|iso-country)[^>]*>[^<]*</[^>]+>", re.I)
_MOJI = re.compile(r"Ã.|Â.")
_PAREN_COUNTRY_RE = re.compile(r"\s*\(([A-Za-z]{3})\)\s*$")
# Football feed country tags only — not a global parenthesis stripper.
PAREN_COUNTRY = {
    "uru": "UY",
    "per": "PE",
    "arg": "AR",
    "bra": "BR",
    "chi": "CL",
    "col": "CO",
    "ecu": "EC",
    "par": "PY",
    "bol": "BO",
    "ven": "VE",
    "mex": "MX",
    "usa": "US",
    "esp": "ES",
    "ita": "IT",
    "fra": "FR",
    "ger": "DE",
    "ned": "NL",
    "por": "PT",
    "bel": "BE",
    "eng": "GB",
    "sco": "GB",
    "wal": "GB",
    "irl": "IE",
}


def fold_for_identity(name: str) -> str:
    raw = unicodedata.normalize("NFKD", str(name or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower()
    raw = re.sub(r"\([a-z]{2,3}\)", " ", raw)
    raw = re.sub(r"^[a-z]{2}\s+", "", raw)
    raw = re.sub(r"\binternazionale(?:\s+milano)?\b", "inter", raw)
    raw = re.sub(
        r"\b(fc|cf|sc|afc|cfc|fk|nk|bk|if|il|sk|ac|as|us|ssc|acf|ud|cd|rcd|sv|rc|vfl|calcio|club|clube|football|soccer)\b",
        " ",
        raw,
    )
    raw = re.sub(r"\b(de|da|do|del|della|di|of|the|and|la|le|el|los|las)\b", " ", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


# Sport-scoped club suffixes. Never stripped globally — only when the event
# sport/competition is basketball, volleyball, or table tennis.
BASKETBALL_CLUB_SUFFIXES = {"bc", "basketball", "baloncesto", "basket"}
VOLLEYBALL_CLUB_SUFFIXES = {"volley", "volleyball", "pallavolo", "vk"}
TABLE_TENNIS_CLUB_SUFFIXES = {"ttc", "ttv", "tt", "tischtennis"}
_BASKETBALL_CONTEXT = {"basketball", "nba", "wnba", "euroleague", "ncaa-basketball"}
_VOLLEYBALL_CONTEXT = {"volleyball", "plusliga", "italy-superlega", "cev-eurovolley-men"}
_TABLE_TENNIS_CONTEXT = {"table-tennis", "germany-click-tt"}

LEGAL_IDENTITY_TOKENS = {
    "fc",
    "cf",
    "sc",
    "afc",
    "cfc",
    "fk",
    "nk",
    "bk",
    "if",
    "il",
    "sk",
    "ac",
    "as",
    "us",
    "ssc",
    "acf",
    "ud",
    "cd",
    "rcd",
    "sv",
    "rc",
    "vfl",
    "calcio",
    "club",
    "clube",
    "football",
    "soccer",
    "de",
    "da",
    "do",
    "del",
    "della",
    "di",
    "of",
    "the",
    "and",
    "la",
    "le",
    "el",
    "los",
    "las",
    "1",
    "i",
}

# Prefix/suffix tokens that change a club's legal name without creating a new club.
CLUB_STYLE_EXTRAS = {
    "racing",
    "olympique",
    "olympic",
    "deportivo",
}


def club_suffixes_for(sport: str = "", competition: str = "") -> set:
    ctx = {str(sport or "").lower().strip(), str(competition or "").lower().strip()}
    suffixes: set = set()
    if ctx & _BASKETBALL_CONTEXT:
        suffixes |= BASKETBALL_CLUB_SUFFIXES
    if ctx & _VOLLEYBALL_CONTEXT:
        suffixes |= VOLLEYBALL_CLUB_SUFFIXES
    if ctx & _TABLE_TENNIS_CONTEXT:
        suffixes |= TABLE_TENNIS_CLUB_SUFFIXES
    return suffixes


def identity_core(name: str, *, sport: str = "", competition: str = "") -> str:
    tokens = [tok for tok in fold_for_identity(name).split() if tok not in LEGAL_IDENTITY_TOKENS]
    suffixes = club_suffixes_for(sport, competition)
    while len(tokens) > 1 and tokens[-1] in suffixes:
        tokens = tokens[:-1]
    while len(tokens) > 1 and tokens[0] in suffixes:
        tokens = tokens[1:]
    # "B.C." folds to two tokens ("b", "c") — only strip that pair together.
    if suffixes and len(tokens) >= 2 and tokens[-2:] == ["b", "c"] and "bc" in suffixes:
        tokens = tokens[:-2]
    if suffixes and len(tokens) >= 2 and tokens[:2] == ["b", "c"] and "bc" in suffixes:
        tokens = tokens[2:]
    return " ".join(tokens).strip()


def repair_mojibake(value: str) -> str:
    text = str(value or "")
    if not _MOJI.search(text):
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if _MOJI.search(fixed) and fixed.count("Ã") >= text.count("Ã"):
        return text
    return fixed


def strip_flag_abbr_html(html: str) -> str:
    clean = _ABBR_TAG.sub(" ", html or "")
    return _FLAG_CLASS.sub(" ", clean)


_CLUB_PARTICLES = {"AS", "AC", "FC", "CF", "SC", "SK", "SS", "RC", "CD", "UD"}
_TRANSPORT_SPORTS = {
    "baseball",
    "basketball",
    "american-football",
    "ice-hockey",
    "nfl",
    "nba",
    "mlb",
    "nhl",
}
_ISO_ALIASES = {
    "italy": "IT",
    "ita": "IT",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "belgium": "BE",
    "bel": "BE",
    "england": "GB",
    "spain": "ES",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "portugal": "PT",
    "brazil": "BR",
    "argentina": "AR",
}


def iso_country_code(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[A-Za-z]{2}", raw):
        return raw.upper()
    folded = re.sub(r"[\s_-]+", " ", raw.lower()).strip()
    return _ISO_ALIASES.get(folded)


def strip_transport_country_prefix(
    name: str,
    sport: Optional[str] = None,
    competition_country: Optional[str] = None,
    participant_country: Optional[str] = None,
) -> str:
    """Drop ISO transport prefixes without touching club particles (AS Monaco, US Sassuolo)."""
    raw = str(name or "").strip()
    match = re.match(r"^([A-Z]{2})\s+(.+)$", raw)
    if not match:
        return raw
    code, rest = match.group(1), match.group(2).strip()
    if code in _CLUB_PARTICLES:
        return raw
    sport_id = str(sport or "").lower()
    comp_iso = iso_country_code(competition_country)
    part_iso = iso_country_code(participant_country)
    tokens = rest.split()
    if code == "US":
        italian_us_club = len(tokens) == 1 or (
            len(tokens) == 2 and tokens[-1].lower() in {"calcio", "fc"}
        )
        metadata = (
            sport_id in _TRANSPORT_SPORTS
            or comp_iso == "US"
            or part_iso == "US"
            or (comp_iso is None and part_iso is None and len(tokens) >= 3)
        )
        if italian_us_club and comp_iso not in {None, "US"} and part_iso != "US":
            return raw
        if italian_us_club and not metadata:
            return raw
        if metadata or (len(tokens) >= 2 and comp_iso == "US"):
            return rest
        if len(tokens) >= 3:
            return rest
        return raw
    if code in _FLAG_CODES and code not in {"SK", "IN"}:
        return rest
    if comp_iso and code == comp_iso:
        return rest
    return raw


def strip_glued_country_code(name: str) -> str:
    """Repair stored names where a flag code was concatenated, not club initials."""
    raw = str(name or "").strip()
    if len(raw) < 5:
        return raw
    prefix = re.match(r"^([A-Z]{2})(?:\s+|(?=[A-Z][a-z]))(.+)$", raw)
    if prefix and prefix.group(1) in _FLAG_CODES and prefix.group(1) not in {"SK", "IN", "US"}:
        rest = prefix.group(2).strip()
        if len(rest) >= 3:
            return rest
    suffix = re.match(r"^(.+?)([A-Z]{2})$", raw)
    if suffix and suffix.group(2) in _FLAG_CODES and " " in suffix.group(1):
        stem = suffix.group(1).strip()
        if len(stem) >= 4 and not stem.endswith(" "):
            return stem
    glued = re.match(r"^(.+[a-z])([A-Z]{2})$", raw)
    if glued and glued.group(2) in _FLAG_CODES:
        return glued.group(1)
    return raw


def extract_parenthetical_country(name: str) -> tuple[str, Optional[str]]:
    raw = str(name or "").strip()
    match = _PAREN_COUNTRY_RE.search(raw)
    if not match:
        return raw, None
    code = PAREN_COUNTRY.get(match.group(1).lower())
    if not code:
        return raw, None
    cleaned = raw[: match.start()].strip()
    return cleaned or raw, code


def clean_participant_name(
    name: str,
    sport: Optional[str] = None,
    competition_country: Optional[str] = None,
    participant_country: Optional[str] = None,
) -> str:
    text = repair_mojibake(str(name or "").strip())
    text = re.sub(r"\s+", " ", text)
    text = strip_transport_country_prefix(
        text,
        sport=sport,
        competition_country=competition_country,
        participant_country=participant_country,
    )
    text = strip_glued_country_code(text)
    text, _country = extract_parenthetical_country(text)
    return text


def participant_payload(
    raw: Any,
    side: str,
    sport: Optional[str] = None,
    competition_country: Optional[str] = None,
) -> Dict[str, Any]:
    sport_id = sport
    if isinstance(raw, dict):
        sport_id = sport or raw.get("sport")
        country = raw.get("country") or raw.get("countryCode") or raw.get("nationality") or raw.get("country_id")
        source_name = raw.get("name") or raw.get("label") or raw.get("fullName") or raw.get("displayName") or ""
        name = clean_participant_name(
            str(source_name),
            sport=sport_id,
            competition_country=competition_country,
            participant_country=country if isinstance(country, str) else None,
        )
        cleaned, extracted = extract_parenthetical_country(str(source_name or name))
        if extracted and not country:
            country = extracted
        if cleaned:
            name = clean_participant_name(
                cleaned,
                sport=sport_id,
                competition_country=competition_country,
                participant_country=country if isinstance(country, str) else None,
            )
        from collector.participant_alias import canonical_display_name

        shown = canonical_display_name(name, sport=sport_id)
        return {
            "id": raw.get("id") or "",
            "slug": raw.get("slug") or "",
            "name": shown,
            "display_name": shown,
            "side": side,
            "logo": raw.get("logo") or raw.get("image"),
            "source_name": source_name or shown,
            "country_id": country if isinstance(country, str) and len(country) <= 3 else None,
        }
    name = clean_participant_name(str(raw or ""), sport=sport_id, competition_country=competition_country)
    from collector.participant_alias import canonical_display_name

    shown = canonical_display_name(name, sport=sport_id)
    return {
        "id": "",
        "slug": "",
        "name": shown,
        "display_name": shown,
        "side": side,
        "source_name": str(raw or ""),
    }
