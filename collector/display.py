"""Public display sanitizers. Read-side only — collectors are unchanged."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

TBD = "TBD"
_ROUND = {
    "sf": "SF",
    "qf": "QF",
    "r16": "R16",
    "r32": "R32",
    "r64": "R64",
    "of": "F",
    "f": "F",
}


def _compact(value: str) -> str:
    return re.sub(r"[\s._-]+", "", value or "")


def _winner_loser(kind: str, round_token: str, index: str) -> str:
    role = "Loser" if str(kind).lower().startswith("l") else "Winner"
    base = _ROUND.get(str(round_token).lower(), str(round_token).upper())
    slot = f"{base}{index}" if index else base
    return f"{role} of {slot}" if slot else TBD


def sanitize_participant_name(
    name: Optional[str],
    sport: Optional[str] = None,
    competition_country: Optional[str] = None,
    participant_country: Optional[str] = None,
) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    folded = _compact(raw)
    if re.fullmatch(r"(tbd|tba|tbc|n/a|na|unk|unknown)", folded, re.I):
        return TBD
    if re.fullmatch(r"(team|player|fighter|horse|runner|club)?(tbd|tba|tbc)", folded, re.I):
        return TBD
    coded = re.fullmatch(r"(w|l)(sf|qf|r16|r32|r64|of|f)(\d{1,2})", folded, re.I)
    if coded:
        return _winner_loser(coded.group(1), coded.group(2), coded.group(3))
    if re.fullmatch(r"m[efs]-\d+", folded, re.I):
        return TBD
    if re.fullmatch(r"[wl][a-z]{1,3}\d{1,2}", folded, re.I):
        return TBD
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", raw):
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return ""
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", raw):
        return ""
    if re.fullmatch(r"\d{1,3}\s*[-–:/]\s*\d{1,3}", raw):
        return ""
    if re.search(r"<[^>]+>", raw):
        return ""
    from collector.participant_alias import canonical_display_name
    from collector.participant_text import clean_participant_name

    cleaned = clean_participant_name(
        raw,
        sport=sport,
        competition_country=competition_country,
        participant_country=participant_country,
    )
    return canonical_display_name(cleaned, sport=sport)


def sanitize_side(
    side: Any,
    sport: Optional[str] = None,
    competition_country: Optional[str] = None,
) -> Any:
    if not isinstance(side, dict):
        if isinstance(side, str):
            return sanitize_participant_name(side, sport=sport, competition_country=competition_country)
        return side
    out = dict(side)
    shown = sanitize_participant_name(
        str(out.get("display_name") or out.get("name") or ""),
        sport=sport,
        competition_country=competition_country,
        participant_country=out.get("country_id") or out.get("country") or out.get("nationality"),
    )
    if shown:
        if not out.get("source_name"):
            out["source_name"] = out.get("name") or shown
        out["display_name"] = shown
        out["name"] = shown
    return out
