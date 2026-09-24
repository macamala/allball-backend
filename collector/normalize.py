"""Normalize adapter event dicts onto the SportsDataProvider event families."""

from __future__ import annotations

from typing import Any, Dict, Optional

from collector.live_state import canonical_status, guard_future_status, is_live, reconcile_live_status
from collector.tennis_score import apply_tennis_match_score
from collector.participant_text import clean_participant_name, fold_for_identity, participant_payload
from collector.timezones import DATE_ONLY, iso_utc, resolve_event_time
from collector.util import slugify
from sports_registry.event_models import event_family_for_sport
from sports_registry.sports import get_sport


def _participant(raw: Any, side: str, sport_id: str = "") -> Dict[str, Any]:
    payload = participant_payload(raw, side, sport=sport_id)
    name = payload.get("name") or ""
    payload["slug"] = payload.get("slug") or slugify(fold_for_identity(name) or name)
    if isinstance(raw, dict):
        payload["logo"] = (
            payload.get("logo")
            or raw.get("logo")
            or raw.get("image")
            or raw.get("crest")
            or raw.get("badge")
            or raw.get("team_logo")
            or raw.get("teamLogo")
            or raw.get("logo_url")
            or raw.get("logoUrl")
            or raw.get("image_url")
            or raw.get("imageUrl")
            or raw.get("emblem")
            or raw.get("icon")
        )
    return payload


def normalize_event(raw: Dict[str, Any], *, sport_id: str, competition_id: str) -> Dict[str, Any]:
    sport = get_sport(sport_id) or {}
    family = raw.get("event_family") or event_family_for_sport(sport_id) or "team_match"
    inferred = bool(raw.get("status_inferred"))
    resolved = resolve_event_time(
        raw.get("start_time") or raw.get("kickoff") or raw.get("date"),
        competition_id=competition_id,
        country_id=str(raw.get("country_id") or ""),
        provider=str(raw.get("source_family") or raw.get("provider") or ""),
        source_timezone=raw.get("timezone") or raw.get("source_timezone"),
        venue_timezone=raw.get("venue_timezone"),
    )
    canonical_start = iso_utc(resolved)
    status = guard_future_status(
        canonical_status(raw.get("status") or "scheduled"),
        canonical_start or resolved.source_local_datetime,
        inferred=inferred,
        sport_id=sport_id,
    )
    home = _participant(raw.get("home") or raw.get("participant_a") or raw.get("fighter_a"), "home", sport_id)
    away = _participant(raw.get("away") or raw.get("participant_b") or raw.get("fighter_b"), "away", sport_id)
    score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
    event: Dict[str, Any] = {
        "source_event_id": str(raw.get("source_event_id") or raw.get("id") or ""),
        "sport": sport_id,
        "competition": raw.get("competition") or raw.get("competition_name") or competition_id,
        "competition_key": competition_id,
        "source_competition_name": raw.get("source_competition_name") or raw.get("competition") or raw.get("competition_name"),
        "source_competition_id": raw.get("source_competition_id"),
        "season": raw.get("season"),
        "event_family": family,
        "home": home,
        "away": away,
        "participant_a": _participant(raw.get("participant_a") or home, "a", sport_id),
        "participant_b": _participant(raw.get("participant_b") or away, "b", sport_id),
        "start_time": canonical_start,
        "start_date": resolved.start_date,
        "start_precision": resolved.precision,
        "source_local_datetime": resolved.source_local_datetime,
        "source_timezone": resolved.source_timezone,
        "timezone_resolution_method": resolved.method,
        "_resolved_time": resolved,
        "status": status,
        "score": {
            "home": score.get("home", raw.get("home_score")),
            "away": score.get("away", raw.get("away_score")),
            "period": score.get("period") or raw.get("period"),
            "minute": score.get("minute") or raw.get("minute"),
            "clock": score.get("clock") or raw.get("clock"),
            "set": score.get("set"),
            "quarter": score.get("quarter"),
            "hits": score.get("hits"),
            "errors": score.get("errors"),
            "runs": score.get("runs"),
            "wickets": score.get("wickets"),
            "overs": score.get("overs"),
            "inning": score.get("inning") or raw.get("inning"),
            "inning_half": score.get("inning_half") or score.get("inning_state") or raw.get("inning_half"),
            "outs": score.get("outs"),
            "ft_home": score.get("ft_home"),
            "ft_away": score.get("ft_away"),
            "aet_home": score.get("aet_home"),
            "aet_away": score.get("aet_away"),
            "home_penalties": score.get("home_penalties"),
            "away_penalties": score.get("away_penalties"),
        },
        "venue": raw.get("venue"),
        "attendance": raw.get("attendance") or raw.get("numberOfViewers"),
        "referee": raw.get("referee"),
        "series_id": raw.get("series_id"),
        "session_type": raw.get("session_type"),
        "game_id": raw.get("game_id") or (sport_id if sport.get("parent_id") == "esports" else None),
        "country_id": raw.get("country_id"),
        "competition_logo": (
            raw.get("competition_logo")
            or raw.get("competitionLogo")
            or raw.get("competition_image")
            or raw.get("competitionImage")
            or raw.get("league_logo")
            or raw.get("leagueLogo")
            or raw.get("league_image")
            or raw.get("leagueImage")
            or raw.get("tournament_logo")
            or raw.get("tournamentLogo")
        ),
        "meeting_id": raw.get("meeting_id"),
        "race_number": raw.get("race_number"),
        "group": raw.get("group"),
        "group_name": raw.get("group_name"),
        "source_group_id": raw.get("source_group_id"),
        "source_parent_competition_id": raw.get("source_parent_competition_id"),
        "tournament": raw.get("tournament"),
        "round": raw.get("round"),
        "lineups": raw.get("lineups"),
        "statistics": raw.get("statistics"),
        "incidents": raw.get("incidents") or raw.get("events"),
        "availability": raw.get("availability") or [],
        "live": is_live(status),
        "stage": raw.get("stage") or raw.get("round"),
        "gender": raw.get("gender"),
        "timezone": raw.get("timezone"),
        "source_url": raw.get("source_url") or raw.get("url"),
        "coverage": raw.get("coverage") or raw.get("coverage_kind"),
        "coverage_kind": raw.get("coverage_kind") or raw.get("coverage"),
        "source_competition_name": raw.get("source_competition_name") or raw.get("competition"),
        "source_season_id": raw.get("source_season_id") or ((raw.get("extra") or {}).get("source_season_id") if isinstance(raw.get("extra"), dict) else None),
        "source_season_name": raw.get("source_season_name") or ((raw.get("extra") or {}).get("source_season_name") if isinstance(raw.get("extra"), dict) else None),
        "sofascore_tournament_id": raw.get("sofascore_tournament_id") or ((raw.get("extra") or {}).get("sofascore_tournament_id") if isinstance(raw.get("extra"), dict) else None),
        "sofascore_season_id": raw.get("sofascore_season_id") or ((raw.get("extra") or {}).get("sofascore_season_id") if isinstance(raw.get("extra"), dict) else None),
        "source_family": raw.get("source_family"),
        "source_event_ids": (raw.get("source_event_ids") if isinstance(raw.get("source_event_ids"), dict) else None)
        or ((raw.get("extra") or {}).get("source_event_ids") if isinstance(raw.get("extra"), dict) else None),
        "athletes": raw.get("athletes") or raw.get("drivers") or raw.get("runners"),
        "periods": raw.get("periods") or raw.get("sets") or raw.get("quarters"),
        "maps": raw.get("maps"),
        "best_of": raw.get("best_of"),
        "classification": raw.get("classification"),
        "runners": raw.get("runners"),
        "leaderboard": raw.get("leaderboard"),
        "bracket": raw.get("bracket"),
        "form": raw.get("form"),
        "race_name": raw.get("race_name"),
        "trap": raw.get("trap"),
        "result_type": raw.get("result_type"),
        "winner": raw.get("winner"),
        "walkover": raw.get("walkover"),
        "forfeit": raw.get("forfeit"),
        "retrieved_at": raw.get("retrieved_at") or raw.get("source_fetch_time"),
        "source_fetch_time": raw.get("source_fetch_time") or raw.get("retrieved_at") or raw.get("fetch_completed_at"),
        "source_event_updated_at": raw.get("source_event_updated_at") or raw.get("event_updated_at"),
        "observed_at": raw.get("observed_at")
        or raw.get("source_event_updated_at")
        or raw.get("event_updated_at"),
        "canonical_last_observed_at": raw.get("canonical_last_observed_at")
        or raw.get("observed_at")
        or raw.get("source_event_updated_at"),
        "source_status": raw.get("source_status") or raw.get("status"),
        "tournament_id": raw.get("tournament_id"),
        "tournament_name": raw.get("tournament_name"),
        "surface": raw.get("surface"),
        "category": raw.get("category"),
        "location": raw.get("location"),
        "orientation_conflict": raw.get("orientation_conflict"),
        "status_inferred": inferred,
    }
    if sport.get("event_model") == "motorsport_race" and not event.get("series_id"):
        event["series_id"] = raw.get("series_id") or competition_id
    if sport.get("event_model") == "esports_match":
        event["game_id"] = event.get("game_id") or sport_id
        event["parent_sport_id"] = sport.get("parent_id") or "esports"
    if sport.get("event_model") == "racing":
        event["country_id"] = event.get("country_id")
        event["country_based"] = True
        runners = event.get("runners") or (event.get("score") or {}).get("winner")
        winner = event.get("winner") or (event.get("score") or {}).get("winner")
        if event.get("status") == "finished" and not winner and not runners:
            event["status"] = "scheduled"
            event["live"] = False
    score_row = event.get("score") or {}
    if event.get("status") == "scheduled":
        try:
            if int(score_row.get("home")) == 0 and int(score_row.get("away")) == 0:
                score_row["home"] = None
                score_row["away"] = None
                event["score"] = score_row
        except (TypeError, ValueError):
            pass
    from collector.source_ids import merge_family_ids

    extra_raw = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    event["source_event_ids"] = merge_family_ids(
        event.get("source_event_ids"),
        raw.get("source_event_ids"),
        extra_raw.get("source_event_ids"),
        family=str(raw.get("source_family") or extra_raw.get("source_family") or ""),
        source_event_id=raw.get("source_event_id") or extra_raw.get("source_event_id") or event.get("source_event_id"),
    )
    if sport_id == "tennis":
        event = apply_tennis_match_score(event)
    return reconcile_live_status(event)


def fingerprint(event: Dict[str, Any]) -> str:
    family = event.get("event_family") or ""
    sport = event.get("sport") or ""
    comp = event.get("competition_key") or ""
    start = str(event.get("start_time") or "")[:16]
    if family == "motorsport_race":
        parts = [sport, event.get("series_id") or comp, start, event.get("session_type") or "race"]
    elif family == "racing":
        parts = [
            sport,
            event.get("country_id") or "",
            event.get("meeting_id") or event.get("venue") or comp,
            str(event.get("race_number") or event.get("race_name") or start),
        ]
    elif family == "tournament":
        parts = [sport, event.get("tournament") or comp, start, event.get("round") or ""]
    elif family in {"individual_match", "combat", "esports_match"}:
        a = (event.get("participant_a") or event.get("home") or {}).get("slug") or ""
        b = (event.get("participant_b") or event.get("away") or {}).get("slug") or ""
        extra = event.get("game_id") or ""
        parts = [sport, extra or comp, start, a, b]
    else:
        home = (event.get("home") or {}).get("slug") or ""
        away = (event.get("away") or {}).get("slug") or ""
        parts = [sport, comp, start, home, away]
    from collector.util import sha_id

    return sha_id("", *parts, length=32)
