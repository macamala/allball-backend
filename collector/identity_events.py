"""Cross-provider event identity. Name similarity alone is never enough."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from collector.participant_alias import expand_abbreviations, participants_equivalent
from collector.participant_text import club_suffixes_for, fold_for_identity, identity_core

IDENTITY_MERGE_THRESHOLD = 90
_WEAK = {"united", "city", "racing", "sporting", "athletic", "rovers", "town", "county", "stars"}


def _ids(event: Dict[str, Any]) -> set:
    raw = event.get("source_event_ids") or {}
    if isinstance(raw, dict):
        return {str(value) for value in raw.values() if value}
    if isinstance(raw, list):
        return {str(value) for value in raw if value}
    sid = event.get("source_event_id")
    return {str(sid)} if sid else set()


def _fold_side(side: Any) -> str:
    if isinstance(side, dict):
        return expand_abbreviations(fold_for_identity(str(side.get("name") or "")))
    return expand_abbreviations(fold_for_identity(str(side or "")))


def _side_name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "")
    return str(side or "")


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt in ("%b %d, %Y %H:%M", "%b %d, %Y", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if fmt.startswith("%Y-%m-%d %H") else text, fmt)
        except ValueError:
            continue
    return None


def _weak_pair(a: str, b: str) -> bool:
    parts_a = set(a.split())
    parts_b = set(b.split())
    if not parts_a or not parts_b:
        return True
    if parts_a <= _WEAK or parts_b <= _WEAK:
        return True
    return False


def _core_contains(left: str, right: str, *, sport: str = "", competition: str = "") -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < 5:
        return False
    if not longer.startswith(shorter + " "):
        return False
    extra = longer[len(shorter) :].strip()
    extra_tokens = extra.split()
    suffixes = club_suffixes_for(sport, competition)
    if suffixes:
        return bool(extra_tokens) and all(tok in suffixes or (tok == "c" and extra_tokens == ["b", "c"]) for tok in extra_tokens)
    return extra not in _WEAK and extra not in {"fc", "cf"}


def _core_pair(h0: str, a0: str, h1: str, a1: str, *, sport: str = "", competition: str = "") -> bool:
    return (
        _core_contains(h0, h1, sport=sport, competition=competition)
        and _core_contains(a0, a1, sport=sport, competition=competition)
    ) or (
        _core_contains(h0, a1, sport=sport, competition=competition)
        and _core_contains(a0, h1, sport=sport, competition=competition)
    )


def _club_stems(core: str, *, sport: str = "") -> set:
    tokens = [tok for tok in str(core or "").split() if tok]
    if not tokens:
        return set()
    stems = {" ".join(tokens)}
    if sport in {"basketball", "volleyball", "table-tennis"} and len(tokens[0]) >= 8:
        stems.add(tokens[0])
    return stems


def _stems_pair(h0: str, a0: str, h1: str, a1: str, *, sport: str = "") -> bool:
    sh0, sa0, sh1, sa1 = _club_stems(h0, sport=sport), _club_stems(a0, sport=sport), _club_stems(h1, sport=sport), _club_stems(a1, sport=sport)
    return bool(sh0 and sa0 and sh1 and sa1) and (
        (sh0 & sh1 and sa0 & sa1) or (sh0 & sa1 and sa0 & sh1)
    )


def _side_id(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("id") or side.get("source_id") or "").strip()
    return ""


def identity_confidence(canonical: Dict[str, Any], candidate: Dict[str, Any]) -> int:
    if not canonical or not candidate:
        return 0
    if _ids(canonical) & _ids(candidate):
        return 100
    sport = str(canonical.get("sport") or candidate.get("sport") or "")
    if (canonical.get("sport") or "") != (candidate.get("sport") or ""):
        if canonical.get("sport") and candidate.get("sport"):
            return 0
    competition = str(
        canonical.get("competition_key")
        or canonical.get("competition")
        or candidate.get("competition_key")
        or candidate.get("competition")
        or ""
    )
    home = _fold_side(canonical.get("home") or canonical.get("participant_a"))
    away = _fold_side(canonical.get("away") or canonical.get("participant_b"))
    ch = _fold_side(candidate.get("home") or candidate.get("participant_a"))
    ca = _fold_side(candidate.get("away") or candidate.get("participant_b"))
    home_name = _side_name(canonical.get("home") or canonical.get("participant_a"))
    away_name = _side_name(canonical.get("away") or canonical.get("participant_b"))
    ch_name = _side_name(candidate.get("home") or candidate.get("participant_a"))
    ca_name = _side_name(candidate.get("away") or candidate.get("participant_b"))
    if not home or not away:
        return 0
    hid = _side_id(canonical.get("home") or canonical.get("participant_a"))
    aid = _side_id(canonical.get("away") or canonical.get("participant_b"))
    cid_h = _side_id(candidate.get("home") or candidate.get("participant_a"))
    cid_a = _side_id(candidate.get("away") or candidate.get("participant_b"))
    ids_match = bool(hid and aid and cid_h and cid_a) and {hid, aid} == {cid_h, cid_a}
    core_home = identity_core(home_name, sport=sport, competition=competition) or home
    core_away = identity_core(away_name, sport=sport, competition=competition) or away
    core_ch = identity_core(ch_name, sport=sport, competition=competition) or ch
    core_ca = identity_core(ca_name, sport=sport, competition=competition) or ca
    cores_match = bool(core_home and core_away) and {core_home, core_away} == {core_ch, core_ca}
    cores_contain = _core_pair(core_home, core_away, core_ch, core_ca, sport=sport, competition=competition)
    stems_match = _stems_pair(core_home, core_away, core_ch, core_ca, sport=sport)
    if (
        not ids_match
        and {home, away} != {ch, ca}
        and not participants_equivalent(home_name, away_name, ch_name, ca_name)
        and not cores_match
        and not cores_contain
        and not stems_match
    ):
        return 0
    if _weak_pair(home, away):
        return 0
    t0 = _ts(canonical.get("start_time"))
    t1 = _ts(candidate.get("start_time"))
    same_comp = (canonical.get("competition_key") or canonical.get("competition")) == (
        candidate.get("competition_key") or candidate.get("competition")
    )
    max_delta = 4 * 3600 if sport in {"baseball", "basketball"} else 12 * 3600
    if t0 and t1:
        delta = abs((t0 - t1).total_seconds())
        same_cal = t0.date() == t1.date()
        if delta > max_delta and not (same_comp and same_cal):
            return 0
        if same_comp and delta <= 15 * 60:
            return 95
        if same_comp:
            return 90
        if delta <= 3 * 3600:
            return 88
        return 0
    d0 = t0.date().isoformat() if t0 else str(canonical.get("start_time") or "")[:10]
    d1 = t1.date().isoformat() if t1 else str(candidate.get("start_time") or "")[:10]
    same_date = len(d0) >= 10 and d0[:10] == d1[:10] and d0[0].isdigit() and d1[0].isdigit()
    if same_date and same_comp:
        return 90
    if same_date:
        return 65
    return 0


def should_merge_enrichment(canonical: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    score = identity_confidence(canonical, candidate)
    if score < IDENTITY_MERGE_THRESHOLD:
        return False
    same_comp = (canonical.get("competition_key") or canonical.get("competition")) == (
        candidate.get("competition_key") or candidate.get("competition")
    )
    return same_comp or score == 100
