"""Canonical competition standings. One table per competition/season/stage/group."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _num(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace("+", "")
    try:
        return int(text) if "." not in text else float(text)
    except ValueError:
        return value


def canonicalize_standing_rows(raw: Any, sport: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = raw
    if isinstance(raw, dict):
        rows = raw.get("rows") or raw.get("table") or raw.get("standings") or []
        sport = sport or raw.get("sport")
    if not isinstance(rows, list):
        return []
    sport_key = str(sport or "").lower()
    football = sport_key in {"", "football", "soccer"}
    out: List[Dict[str, Any]] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        team = item.get("team") or item.get("name") or item.get("club") or item.get("teamName")
        if isinstance(team, dict):
            team = team.get("name") or team.get("default") or team.get("fullName")
        if not team:
            continue
        wins = _num(item.get("wins") if item.get("wins") is not None else item.get("won"))
        has_draws = any(item.get(key) is not None for key in ("draws", "drawn"))
        draws = _num(item.get("draws") if item.get("draws") is not None else item.get("drawn")) if has_draws else None
        losses = _num(item.get("losses") if item.get("losses") is not None else item.get("lost"))
        row = {
            "position": _num(item.get("position") or item.get("rank") or item.get("idx") or index),
            "team": str(team),
            "played": _num(item.get("played") or item.get("gamesPlayed") or item.get("gp")),
            "won": wins,
            "lost": losses,
            "wins": wins,
            "losses": losses,
            "points": _num(item.get("points") or item.get("pts")),
            "form": item.get("form") or item.get("streak"),
            "stage": item.get("stage"),
            "group": item.get("group") or item.get("conference") or item.get("division"),
        }
        if has_draws:
            row["drawn"] = draws
            row["draws"] = draws
        if football or sport_key in {"ice-hockey", "rugby"}:
            row["goals_for"] = _num(item.get("goals_for") or item.get("goalsFor") or item.get("gf") or item.get("goalFor"))
            row["goals_against"] = _num(
                item.get("goals_against") or item.get("goalsAgainst") or item.get("ga") or item.get("goalAgainst")
            )
            row["goal_difference"] = _num(
                item.get("goal_difference") or item.get("goalDiff") or item.get("gd") or item.get("goalConDiff")
            )
        if item.get("ot_losses") is not None or item.get("otLosses") is not None:
            row["ot_losses"] = _num(item.get("ot_losses") or item.get("otLosses"))
        if item.get("pct") is not None:
            row["pct"] = item.get("pct")
        if item.get("win_pct") is not None:
            row["win_pct"] = item.get("win_pct")
        if item.get("percentage") is not None:
            row["percentage"] = _num(item.get("percentage"))
        if item.get("points_for") is not None:
            row["points_for"] = _num(item.get("points_for"))
        if item.get("points_against") is not None:
            row["points_against"] = _num(item.get("points_against"))
        if item.get("sets_for") is not None:
            row["sets_for"] = _num(item.get("sets_for"))
        if item.get("sets_against") is not None:
            row["sets_against"] = _num(item.get("sets_against"))
        out.append({key: value for key, value in row.items() if value not in (None, "", [])})
    return out


def wrap_standings(
    rows: List[Dict[str, Any]],
    *,
    competition: str,
    season: Optional[str] = None,
    stage: Optional[str] = None,
    group: Optional[str] = None,
    sport: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "competition": competition,
        "season": season,
        "stage": stage,
        "group": group,
        "sport": sport,
        "rows": canonicalize_standing_rows(rows, sport=sport),
    }


def unwrap_standings(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return canonicalize_standing_rows(payload["rows"], sport=payload.get("sport"))
    return canonicalize_standing_rows(payload)
