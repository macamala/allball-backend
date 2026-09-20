"""Canonical public match-detail shapes. Provider schemas stay internal."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace("%", "")
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _side_name(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("team") or row.get("participant") or "").lower()


def canonicalize_timeline(raw: Any) -> List[Dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("event_type") or item.get("code") or "").lower()
        if not kind and not item.get("player") and not item.get("minute"):
            continue
        if kind in {"goal", "penalty_goal", "own_goal", "pen"}:
            family = "goal"
        elif kind in {"yellow", "yellow_card", "card"}:
            family = "card"
            kind = kind if kind != "card" else "yellow"
        elif kind in {"red", "red_card", "second_yellow"}:
            family = "card"
        elif kind in {"sub", "substitution", "subst"}:
            family = "substitution"
        elif "var" in kind:
            family = "var"
        else:
            family = kind or "event"
        score_after = item.get("score_after") if isinstance(item.get("score_after"), dict) else None
        out.append(
            {
                "type": kind or family,
                "family": family,
                "period": _text(item.get("period")),
                "minute": item.get("minute"),
                "stoppage": item.get("stoppage"),
                "player": _text(item.get("player") or item.get("name") or item.get("scorer")),
                "assist": _text(item.get("assist") or item.get("secondary_player")),
                "player_in": _text(item.get("player_in") or (item.get("in") if family == "substitution" else None)),
                "player_out": _text(item.get("player_out") or (item.get("out") if family == "substitution" else None)),
                "side": _text(item.get("side") or item.get("participant")),
                "score_after": (
                    {"home": score_after.get("home"), "away": score_after.get("away")} if score_after else None
                ),
            }
        )
    return out


def canonicalize_statistics(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    rows: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = _text(item.get("label") or item.get("name") or item.get("key"))
            home = item.get("home") if "home" in item else item.get("home_value")
            away = item.get("away") if "away" in item else item.get("away_value")
            value = item.get("value")
            if home is None and away is None and isinstance(value, dict):
                home = value.get("home")
                away = value.get("away")
            if home is None and away is None and value is not None and label:
                rows.append({"label": label, "home": None, "away": None, "value": value})
                continue
            if home is None and away is None:
                continue
            if _num(home) == 0 and _num(away) == 0 and home is not None and away is not None:
                # Real zeros are allowed; unknown 0/0 without provenance is still a supplied value.
                pass
            rows.append({"label": label or "Stat", "home": home, "away": away})
        return rows
    if isinstance(raw, dict):
        home_blob = raw.get("home") if isinstance(raw.get("home"), dict) else {}
        away_blob = raw.get("away") if isinstance(raw.get("away"), dict) else {}
        keys = sorted(set(home_blob) | set(away_blob) | {k for k in raw if k not in {"home", "away", "provider", "source"}})
        for key in keys:
            if str(key).startswith("source"):
                continue
            if key in home_blob or key in away_blob:
                home = home_blob.get(key)
                away = away_blob.get(key)
                if home is None and away is None:
                    continue
                rows.append({"label": str(key).replace("_", " ").title(), "home": home, "away": away})
            elif not isinstance(raw.get(key), dict):
                continue
        return rows
    return []


def canonicalize_lineups(raw: Any) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    if isinstance(raw, dict) and (raw.get("home") or raw.get("away")):
        def pack(side: Any) -> Dict[str, Any]:
            blob = side if isinstance(side, dict) else {}
            players = blob.get("start") or blob.get("xi") or blob.get("players") or blob.get("starting") or []
            bench = blob.get("bench") or blob.get("substitutes") or []
            if isinstance(side, list):
                players = side
            return {
                "formation": _text(blob.get("formation")),
                "coach": _text(blob.get("coach") or blob.get("manager")),
                "start": [
                    {"name": _text(p.get("name") if isinstance(p, dict) else p), "number": (p.get("number") if isinstance(p, dict) else None), "position": (p.get("position") if isinstance(p, dict) else None)}
                    for p in (players or [])
                    if (p.get("name") if isinstance(p, dict) else p)
                ],
                "bench": [
                    {"name": _text(p.get("name") if isinstance(p, dict) else p), "number": (p.get("number") if isinstance(p, dict) else None)}
                    for p in (bench or [])
                    if (p.get("name") if isinstance(p, dict) else p)
                ],
            }

        home = pack(raw.get("home"))
        away = pack(raw.get("away"))
        if not home["start"] and not away["start"] and not home["bench"] and not away["bench"]:
            return None
        return {"home": home, "away": away}
    if isinstance(raw, list) and raw:
        names = [{"name": _text(item.get("name") if isinstance(item, dict) else item), "side": _side_name(item) if isinstance(item, dict) else ""} for item in raw]
        names = [row for row in names if row.get("name")]
        if not names:
            return None
        return {
            "home": {"formation": None, "coach": None, "start": [r for r in names if r.get("side") in {"home", "a", ""}], "bench": []},
            "away": {"formation": None, "coach": None, "start": [r for r in names if r.get("side") in {"away", "b"}], "bench": []},
        }
    return None


def canonicalize_periods(raw: Any) -> List[Dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        home = item.get("home") if "home" in item else item.get("a")
        away = item.get("away") if "away" in item else item.get("b")
        if home is None and away is None:
            continue
        out.append(
            {
                "label": _text(item.get("label") or item.get("code")) or str(item.get("number") or index + 1),
                "code": _text(item.get("code")),
                "home": home,
                "away": away,
            }
        )
    return out


def sport_detail_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    extra = {
        "clock": score.get("clock") or event.get("clock"),
        "minute": score.get("minute"),
        "period": score.get("period") or score.get("quarter") or event.get("period"),
        "serving": event.get("serving"),
        "current_set": event.get("current_set") or score.get("set"),
        "surface": event.get("surface"),
        "inning": score.get("inning") or event.get("inning"),
        "inning_half": score.get("inning_half"),
        "outs": score.get("outs"),
        "hits": score.get("hits"),
        "errors": score.get("errors"),
        "best_of": event.get("best_of"),
        "maps": event.get("maps"),
        "session_type": event.get("session_type"),
        "stage": event.get("stage"),
        "winner": event.get("winner"),
        "result_type": event.get("result_type"),
    }
    return {key: value for key, value in extra.items() if value not in (None, "", [], {})}


def attach_canonical_detail(event: Dict[str, Any]) -> Dict[str, Any]:
    if not event:
        return event
    timeline = canonicalize_timeline(event.get("incidents") or event.get("timeline"))
    statistics = canonicalize_statistics(event.get("statistics"))
    lineups = canonicalize_lineups(event.get("lineups"))
    periods = canonicalize_periods(event.get("periods") or event.get("innings") or (event.get("score") or {}).get("periods"))
    if timeline:
        event["timeline"] = timeline
        event["incidents"] = timeline
    else:
        event.pop("incidents", None)
    if statistics:
        event["statistics"] = statistics
    else:
        event.pop("statistics", None)
    if lineups:
        event["lineups"] = lineups
    else:
        event.pop("lineups", None)
    if periods:
        event["periods"] = periods
    sport_detail = sport_detail_from_event(event)
    if sport_detail:
        event["sport_detail"] = sport_detail
    return event
