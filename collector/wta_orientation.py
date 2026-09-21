"""Deterministic WTA family side orientation.

Source semantics (api.wtatennis.com match rows):

- Player/Team A fields (PlayerName*A, PlayerName*A2) are participant A.
- Player/Team B fields are participant B.
- ScoreSetNA / ScoreSetNB are games won by A / B in set N. They are not
  winner/loser columns.
- Canonical home is A, away is B. participant_a/b follow the same sides.
- Match score is sets won by A vs B from those set games.
- Winner / Loser, if present, only corroborate. They never rotate A/B.

A canonical event must not show match score 2–0 for A while the displayed
sets were won by B.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from collector.tennis_score import apply_tennis_match_score, completed_set_wins, set_is_complete

A_SIDE = "home"
B_SIDE = "away"

_RETIRED = {"R", "RET", "RETIRED", "ABD", "ABANDONED"}
_WALKOVER = {"W", "WO", "WALKOVER"}
_FINISHED = {"F", "FINISHED"}
_LIVE = {"P", "L", "I", "LIVE"}


def wta_player_name(row: Dict[str, Any], prefix: str) -> str:
    first = str(row.get(f"PlayerNameFirst{prefix}") or "").strip()
    last = str(row.get(f"PlayerNameLast{prefix}") or "").strip()
    name = f"{first} {last}".strip()
    first2 = str(row.get(f"PlayerNameFirst{prefix}2") or "").strip()
    last2 = str(row.get(f"PlayerNameLast{prefix}2") or "").strip()
    partner = f"{first2} {last2}".strip()
    if partner:
        return f"{name} / {partner}"
    return name


def _int_score(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def periods_from_score_sets(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for index in range(1, 6):
        home = _int_score(row.get(f"ScoreSet{index}A"))
        away = _int_score(row.get(f"ScoreSet{index}B"))
        if home is None and away is None:
            continue
        if home is None or away is None:
            continue
        winner = None
        complete = set_is_complete(home, away)
        if complete and home > away:
            winner = A_SIDE
        elif complete and away > home:
            winner = B_SIDE
        out.append(
            {
                "number": index,
                "period": index,
                "code": f"Set {index}",
                "label": f"Set {index}",
                "home": home,
                "away": away,
                "winner": winner,
                "complete": complete,
                "tiebreak_home": None,
                "tiebreak_away": None,
            }
        )
    return out


def sets_won_from_periods(periods: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
    return completed_set_wins(periods)


def winner_side_from_source(row: Dict[str, Any], home_name: str, away_name: str) -> Optional[str]:
    raw = row.get("Winner")
    if raw in (None, ""):
        raw = row.get("MatchWinner")
    token = str(raw or "").strip()
    if not token:
        return None
    upper = token.upper()
    if upper in {"A", "1", "HOME", "TEAMA"}:
        return A_SIDE
    if upper in {"B", "2", "AWAY", "TEAMB"}:
        return B_SIDE
    folded = token.casefold()
    if home_name and folded == home_name.casefold():
        return A_SIDE
    if away_name and folded == away_name.casefold():
        return B_SIDE
    return None


def match_status(row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    score_string = str(row.get("ScoreString") or "").upper()
    if "W/O" in score_string or score_string.strip() in {"WO", "WALKOVER"}:
        return "finished", "walkover"
    state = str(row.get("MatchState") or "").strip().upper()
    if state in _FINISHED:
        return "finished", None
    if state in _LIVE:
        return "live", None
    if state in _WALKOVER:
        return "finished", "walkover"
    if state in _RETIRED:
        return "finished", "retirement"
    return "scheduled", None


def unique_source_event_id(row: Dict[str, Any], tournament: Optional[Dict[str, Any]] = None) -> str:
    group = (tournament or {}).get("tournamentGroup") or {}
    parts = [
        group.get("id") or (tournament or {}).get("id") or row.get("EventID") or row.get("TournamentID"),
        (tournament or {}).get("year"),
        row.get("MatchID"),
    ]
    tokens = [str(item).strip() for item in parts if item not in (None, "")]
    return ":".join(tokens) if tokens else str(row.get("id") or "")


def orient_wta_match(row: Dict[str, Any], tournament: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    home = wta_player_name(row, "A")
    away = wta_player_name(row, "B")
    periods = periods_from_score_sets(row)
    status, result_type = match_status(row)
    payload = apply_tennis_match_score(
        {
            "periods": periods,
            "status": status,
            "result_type": result_type,
            "score": {"home": None, "away": None},
        }
    )
    home_sets = (payload.get("score") or {}).get("home")
    away_sets = (payload.get("score") or {}).get("away")
    winner_side = winner_side_from_source(row, home, away)
    conflict = False
    if winner_side == A_SIDE and home_sets is not None and away_sets is not None and home_sets < away_sets:
        conflict = True
    if winner_side == B_SIDE and home_sets is not None and away_sets is not None and away_sets < home_sets:
        conflict = True
    return {
        "home_name": home,
        "away_name": away,
        "periods": periods or None,
        "score": {"home": home_sets, "away": away_sets},
        "status": status,
        "result_type": result_type,
        "winner_side": winner_side,
        "orientation_conflict": conflict,
        "source_event_id": unique_source_event_id(row, tournament),
    }


def tennis_sets_agree_with_match_score(score: Dict[str, Any], periods: Any) -> bool:
    if not isinstance(periods, list) or not periods:
        return True
    won_home, won_away = sets_won_from_periods(periods)
    if won_home is None or won_away is None:
        return True
    try:
        match_home = int(score.get("home"))
        match_away = int(score.get("away"))
    except (TypeError, ValueError):
        return True
    return (match_home, match_away) == (won_home, won_away)
