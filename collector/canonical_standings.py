"""Canonical competition standings. One table per competition/season/stage/group."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _first(*values):
    return next((value for value in values if value is not None and value != ""), None)


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
        team_raw = item.get("team") or item.get("club") or item.get("teamName")
        team = team_raw or item.get("name")
        if isinstance(team, dict):
            team = team.get("name") or team.get("default") or team.get("fullName")
        if not team:
            continue
        team_meta = team_raw if isinstance(team_raw, dict) else {}
        team_id = (
            item.get("team_id")
            or item.get("teamId")
            or item.get("club_id")
            or item.get("clubId")
            or team_meta.get("id")
        )
        team_slug = item.get("team_slug") or item.get("teamSlug") or team_meta.get("slug")
        logo = (
            item.get("logo")
            or item.get("crest")
            or item.get("badge")
            or item.get("team_logo")
            or item.get("teamLogo")
            or item.get("image")
            or item.get("imageUrl")
            or item.get("logoUrl")
            or team_meta.get("logo")
            or team_meta.get("crest")
            or team_meta.get("badge")
            or team_meta.get("image")
            or team_meta.get("imageUrl")
            or team_meta.get("logoUrl")
        )
        country = (
            item.get("country_id")
            or item.get("country")
            or item.get("nationality")
            or team_meta.get("country_id")
            or team_meta.get("country")
            or team_meta.get("nationality")
        )
        if isinstance(country, dict):
            country = country.get("alpha2") or country.get("alpha3") or country.get("code") or country.get("name")
        wins = _num(item.get("wins") if item.get("wins") is not None else item.get("won"))
        has_draws = any(item.get(key) is not None for key in ("draws", "drawn"))
        draws = _num(item.get("draws") if item.get("draws") is not None else item.get("drawn")) if has_draws else None
        losses = _num(item.get("losses") if item.get("losses") is not None else item.get("lost"))
        row = {
            "position": _num(item.get("position") or item.get("rank") or item.get("idx") or index),
            "team": str(team),
            "team_id": str(team_id) if team_id not in (None, "") else None,
            "team_slug": str(team_slug) if team_slug not in (None, "") else None,
            "logo": str(logo) if logo not in (None, "") else None,
            "country_id": str(country) if country not in (None, "") else None,
            "played": _num(_first(item.get("played"), item.get("gamesPlayed"), item.get("gp"))),
            "won": wins,
            "lost": losses,
            "wins": wins,
            "losses": losses,
            "points": _num(_first(item.get("points"), item.get("pts"))),
            "form": item.get("form") or item.get("streak"),
            "stage": item.get("stage"),
            "group": item.get("group") or item.get("conference") or item.get("division"),
        }
        if has_draws:
            row["drawn"] = draws
            row["draws"] = draws
        if football or sport_key in {"ice-hockey", "rugby"}:
            row["goals_for"] = _num(_first(item.get("goals_for"), item.get("goalsFor"), item.get("gf"), item.get("goalFor")))
            row["goals_against"] = _num(
                _first(item.get("goals_against"), item.get("goalsAgainst"), item.get("ga"), item.get("goalAgainst"))
            )
            row["goal_difference"] = _num(
                _first(item.get("goal_difference"), item.get("goalDiff"), item.get("gd"), item.get("goalConDiff"))
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
