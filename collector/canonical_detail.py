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

    def pack_player(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, str):
            name = _text(value)
            return {"name": name} if name else None
        if not isinstance(value, dict):
            return None
        name = _text(
            value.get("name")
            or value.get("display_name")
            or value.get("displayName")
            or value.get("fullName")
        )
        if not name:
            return None
        country = (
            value.get("country_id")
            or value.get("countryCode")
            or value.get("country")
            or value.get("nationality")
            or value.get("nation")
        )
        if isinstance(country, dict):
            country = (
                country.get("alpha2")
                or country.get("alpha3")
                or country.get("code")
                or country.get("abbreviation")
                or country.get("name")
            )
        player = {
            "id": value.get("id") or value.get("player_id") or value.get("playerId") or value.get("personId"),
            "name": name,
            "number": value.get("number") or value.get("shirtNumber") or value.get("jerseyNumber"),
            "position": value.get("position") or value.get("role"),
            "captain": bool(value.get("captain") or value.get("isCaptain")),
            "rating": value.get("rating"),
            "image": (
                value.get("image")
                or value.get("photo")
                or value.get("avatar")
                or value.get("image_url")
                or value.get("imageUrl")
                or value.get("headshot")
            ),
            "country_id": _text(country),
        }
        return {key: val for key, val in player.items() if val not in (None, "", False)}

    if isinstance(raw, dict) and (raw.get("home") or raw.get("away")):
        def pack(side: Any) -> Dict[str, Any]:
            blob = side if isinstance(side, dict) else {}
            players = blob.get("start") or blob.get("xi") or blob.get("players") or blob.get("starting") or []
            bench = blob.get("bench") or blob.get("substitutes") or []
            if isinstance(side, list):
                players = side
            packed_start = [pack_player(p) for p in (players or [])]
            packed_bench = [pack_player(p) for p in (bench or [])]
            return {
                "formation": _text(blob.get("formation")),
                "coach": _text(blob.get("coach") or blob.get("manager")),
                "start": [p for p in packed_start if p],
                "bench": [p for p in packed_bench if p],
            }

        home = pack(raw.get("home"))
        away = pack(raw.get("away"))
        if not home["start"] and not away["start"] and not home["bench"] and not away["bench"]:
            return None
        result = {"home": home, "away": away}
        if raw.get("confirmed") is not None:
            result["confirmed"] = bool(raw.get("confirmed"))
        return result
    if isinstance(raw, list) and raw:
        names = []
        for item in raw:
            packed = pack_player(item)
            if not packed:
                continue
            packed["side"] = _side_name(item) if isinstance(item, dict) else ""
            names.append(packed)
        if not names:
            return None
        return {
            "home": {"formation": None, "coach": None, "start": [r for r in names if r.get("side") in {"home", "a", ""}], "bench": []},
            "away": {"formation": None, "coach": None, "start": [r for r in names if r.get("side") in {"away", "b"}], "bench": []},
        }
    return None


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def volleyball_sets_from_scalars(values: List[Any]) -> List[Dict[str, Any]]:
    """Rebuild set pairs from a flattened point list.

    PlusLiga/DataProject stored [25,25,25,19,21,14] for 25-19, 25-21, 25-14.
    Interleaved pairing would invent a 25-25 set, which is not a volleyball result.
    """
    nums = [_as_int(item) for item in values]
    if any(item is None for item in nums) or len(nums) < 2 or len(nums) % 2:
        return []
    n = len(nums) // 2
    interleaved = [{"label": f"Set {i + 1}", "home": nums[2 * i], "away": nums[2 * i + 1]} for i in range(n)]
    split = [{"label": f"Set {i + 1}", "home": nums[i], "away": nums[n + i]} for i in range(n)]

    def winners(rows: List[Dict[str, Any]]) -> int:
        return sum(1 for row in rows if row["home"] != row["away"])

    if winners(interleaved) == n:
        return interleaved
    if winners(split) == n:
        return split
    return split if winners(split) >= winners(interleaved) else interleaved


def volleyball_match_score(periods: List[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    home = away = 0
    complete = 0
    for row in periods:
        hv = _as_int(row.get("home"))
        av = _as_int(row.get("away"))
        if hv is None or av is None or hv == av:
            continue
        complete += 1
        if hv > av:
            home += 1
        else:
            away += 1
    if complete == 0:
        return None
    return {"home": home, "away": away}


def canonicalize_periods(raw: Any, *, sport: str = "") -> List[Dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    if rows and all(not isinstance(item, dict) for item in rows):
        folded = str(sport or "").lower()
        if folded in {"volleyball", "table-tennis"} or (
            len(rows) >= 4
            and len(rows) % 2 == 0
            and all((_as_int(item) or -1) <= 33 for item in rows)
            and any((_as_int(item) or 0) >= 15 for item in rows)
        ):
            return volleyball_sets_from_scalars(rows)
        return []
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


def periods_from_hockey_goals(incidents: Any) -> List[Dict[str, Any]]:
    """Period score is the last goal's score_after in that period. Earlier goalless periods stay 0-0."""
    rows = incidents if isinstance(incidents, list) else []
    by_period: Dict[int, Dict[str, Any]] = {}
    max_period = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("family") or "").lower()
        if kind != "goal" or not isinstance(item.get("score_after"), dict):
            continue
        try:
            number = int(item.get("period"))
        except (TypeError, ValueError):
            continue
        if number < 1:
            continue
        max_period = max(max_period, number)
        by_period[number] = item["score_after"]
    if not max_period:
        return []
    home = 0
    away = 0
    out = []
    for number in range(1, max_period + 1):
        score = by_period.get(number) or {}
        if score.get("home") is not None:
            home = score.get("home")
        if score.get("away") is not None:
            away = score.get("away")
        out.append({"label": str(number), "home": home, "away": away})
    return out


def attach_canonical_detail(event: Dict[str, Any]) -> Dict[str, Any]:
    if not event:
        return event
    timeline = canonicalize_timeline(event.get("incidents") or event.get("timeline"))
    statistics = canonicalize_statistics(event.get("statistics"))
    lineups = canonicalize_lineups(event.get("lineups"))
    raw_periods = event.get("periods") or event.get("innings") or (event.get("score") or {}).get("periods")
    sport = str(event.get("sport") or "").lower()
    if sport == "ice-hockey" and not raw_periods:
        raw_periods = periods_from_hockey_goals(event.get("incidents") or event.get("timeline"))
    periods = canonicalize_periods(
        raw_periods,
        sport=str(event.get("sport") or ""),
    )
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
        if str(event.get("sport") or "").lower() == "volleyball":
            derived = volleyball_match_score(periods)
            if derived:
                score = dict(event.get("score") or {})
                score["home"] = derived["home"]
                score["away"] = derived["away"]
                event["score"] = score
    elif isinstance(event.get("periods"), list) and event.get("periods") and not isinstance(event["periods"][0], dict):
        event.pop("periods", None)
    existing = event.get("sport_detail") if isinstance(event.get("sport_detail"), dict) else {}
    sport_detail = {**existing, **sport_detail_from_event(event)}
    if sport_detail:
        event["sport_detail"] = sport_detail
    if event.get("player_statistics") in ([], {}, None):
        event.pop("player_statistics", None)
    if event.get("classification") in ([], {}, None):
        event.pop("classification", None)
    if event.get("maps") in ([], {}, None):
        event.pop("maps", None)
    return align_australian_rules_detail(event)


def _afl_total(goals: Any, behinds: Any) -> Optional[int]:
    try:
        if goals is None or behinds is None:
            return None
        return int(goals) * 6 + int(behinds)
    except (TypeError, ValueError):
        return None


def align_australian_rules_detail(event: Dict[str, Any]) -> Dict[str, Any]:
    """Keep goals, behinds, and score together. Do not treat AFL as football quarters."""
    if str(event.get("sport") or "").lower() not in {"australian-rules", "afl"}:
        return event
    detail = dict(event.get("sport_detail") or {})
    goals = detail.get("goals") if isinstance(detail.get("goals"), dict) else None
    behinds = detail.get("behinds") if isinstance(detail.get("behinds"), dict) else None
    if not goals:
        return event
    home_total = _afl_total(goals.get("home"), (behinds or {}).get("home"))
    away_total = _afl_total(goals.get("away"), (behinds or {}).get("away"))
    if home_total is not None and away_total is not None:
        detail["score"] = {"home": home_total, "away": away_total}
    if event.get("venue") and not detail.get("venue"):
        detail["venue"] = event.get("venue")
    round_name = detail.get("round") or event.get("round")
    if round_name and not str(round_name).isdigit():
        detail["round"] = round_name
        event["round"] = round_name
    stage = detail.get("stage") or event.get("stage")
    if str(stage or "").isdigit() and int(str(stage)) > 30:
        detail.pop("stage", None)
        if str(event.get("stage") or "") == str(stage):
            event.pop("stage", None)
    if str(event.get("round") or "").isdigit() and int(str(event.get("round"))) > 30:
        event.pop("round", None)
        detail.pop("round", None)
    event["sport_detail"] = {key: value for key, value in detail.items() if value not in (None, "", {})}
    event["statistics"] = [
        {"label": "Goals", "home": goals.get("home"), "away": goals.get("away")},
        {"label": "Behinds", "home": (behinds or {}).get("home"), "away": (behinds or {}).get("away")},
        {"label": "Score", "home": (detail.get("score") or {}).get("home"), "away": (detail.get("score") or {}).get("away")},
    ]
    event["periods"] = [
        {"label": "G", "home": goals.get("home"), "away": goals.get("away")},
        {"label": "B", "home": (behinds or {}).get("home"), "away": (behinds or {}).get("away")},
    ]
    return event
