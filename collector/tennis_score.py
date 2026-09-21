"""Generic tennis match-score derivation from completed sets.

Game totals are never used as the match score. Retirement, walkover,
abandoned, and incomplete matches do not invent a finished set tally.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

_PROTECTED = {"walkover", "wo", "retired", "retirement", "abandoned", "incomplete", "cancelled", "canceled"}


def _int_score(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def set_is_complete(home: Any, away: Any) -> bool:
    a = _int_score(home)
    b = _int_score(away)
    if a is None or b is None:
        return False
    hi, lo = (a, b) if a >= b else (b, a)
    if hi == lo:
        return False
    if hi >= 10 and hi - lo >= 2:
        return True
    if hi == 7 and lo in {5, 6}:
        return True
    if hi >= 6 and hi - lo >= 2:
        return True
    return False


def completed_set_wins(periods: Any) -> Tuple[Optional[int], Optional[int]]:
    if not isinstance(periods, list) or not periods:
        return None, None
    home = away = 0
    complete = 0
    for row in periods:
        if not isinstance(row, dict):
            continue
        a = row.get("home") if "home" in row else row.get("a")
        b = row.get("away") if "away" in row else row.get("b")
        if not set_is_complete(a, b):
            continue
        complete += 1
        ai = int(a)
        bi = int(b)
        if ai > bi:
            home += 1
        else:
            away += 1
    if not complete:
        return None, None
    return home, away


def _target_sets(best_of: Any) -> int:
    try:
        value = int(best_of)
    except (TypeError, ValueError):
        value = 3
    if value >= 5:
        return 3
    return 2


def result_type_is_protected(result_type: Any, walkover: Any = None) -> bool:
    if walkover:
        return True
    token = str(result_type or "").strip().lower()
    return token in _PROTECTED


def derive_tennis_match_score(
    periods: Any,
    *,
    status: str = "",
    result_type: Any = None,
    walkover: Any = None,
    best_of: Any = None,
) -> Tuple[Optional[int], Optional[int]]:
    """Return sets won, or (None, None) when a match result cannot be derived."""
    if result_type_is_protected(result_type, walkover) and str(result_type or "").lower() in {"walkover", "wo"}:
        return None, None
    home, away = completed_set_wins(periods)
    if home is None or away is None:
        return None, None
    target = _target_sets(best_of)
    status_l = str(status or "").lower()
    protected = result_type_is_protected(result_type, walkover)
    if status_l in {"live", "inprogress", "in_progress"}:
        return home, away
    if home >= target or away >= target:
        return home, away
    if protected or status_l in {"finished", "complete"}:
        return None, None
    return home, away


def looks_like_game_score(home: Any, away: Any) -> bool:
    a = _int_score(home)
    b = _int_score(away)
    if a is None or b is None:
        return False
    if a > 3 or b > 3:
        return True
    if a + b >= 6:
        return True
    return False


def apply_tennis_match_score(event: Dict[str, Any]) -> Dict[str, Any]:
    periods = event.get("periods") or event.get("sets")
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    derived = derive_tennis_match_score(
        periods,
        status=str(event.get("status") or ""),
        result_type=event.get("result_type"),
        walkover=event.get("walkover"),
        best_of=event.get("best_of"),
    )
    home, away = derived
    if home is None or away is None:
        if looks_like_game_score(score.get("home"), score.get("away")):
            score = dict(score)
            score["home"] = None
            score["away"] = None
            event["score"] = score
        return event
    score = dict(score)
    if looks_like_game_score(score.get("home"), score.get("away")) or score.get("home") in (None, "") or score.get("away") in (None, ""):
        score["home"] = home
        score["away"] = away
        event["score"] = score
    elif (score.get("home"), score.get("away")) != (home, away) and looks_like_game_score(score.get("home"), score.get("away")):
        score["home"] = home
        score["away"] = away
        event["score"] = score
    else:
        score["home"] = home
        score["away"] = away
        event["score"] = score
    return event
