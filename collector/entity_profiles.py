"""Public team and player profiles assembled from canonical sports data.

Profiles are derived from already-public canonical events/details. No provider
branding or private source metadata is exposed. This lets score participants
become navigable entities before a separate entity table is introduced.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.models import SportsEvent, SportsEventDetail, SportsStandingSnapshot
from collector.participant_text import fold_for_identity
from collector.util import load_json


def _names_equivalent(left: str, right: str) -> bool:
    a = fold_for_identity(left)
    b = fold_for_identity(right)
    return bool(a and b and a == b)


def _side_name(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    return str(side.get("display_name") or side.get("name") or "").strip()


def _side_logo(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    for key in ("logo", "image", "crest", "badge", "team_logo", "teamLogo", "logo_url", "logoUrl"):
        value = side.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _event_card(row: SportsEvent) -> Dict[str, Any]:
    participants = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}
    return {
        "id": row.event_id,
        "sport": row.sport_id,
        "competition_key": row.competition_id,
        "competition": (
            extra.get("public_competition_name")
            or extra.get("source_competition_name")
            or row.competition_id
        ),
        "competition_logo": extra.get("competition_logo") or "",
        "event_family": row.event_family,
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "status": row.status,
        "home": participants.get("home") or participants.get("participant_a") or {},
        "away": participants.get("away") or participants.get("participant_b") or {},
        "score": load_json(row.score_json, {}) or {},
        "country_id": row.country_id,
        "venue": row.venue,
        "stage": row.stage,
    }


def _matches_side(side: Any, *, entity_key: str, name: str) -> bool:
    if not isinstance(side, dict):
        return False
    side_id = str(side.get("id") or "").strip()
    if entity_key and side_id and side_id == entity_key:
        return True
    side_name = _side_name(side)
    return bool(name and side_name and _names_equivalent(name, side_name))


def _merge_identity(current: Dict[str, Any], side: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(current)
    for key in (
        "id",
        "slug",
        "name",
        "display_name",
        "country_id",
        "country",
        "nationality",
        "logo",
        "image",
        "crest",
        "badge",
    ):
        value = side.get(key)
        if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
            out[key] = value
    logo = _side_logo(side)
    if logo and not _side_logo(out):
        out["logo"] = logo
    return out


def _result_for_team(event: Dict[str, Any], *, entity_key: str, name: str) -> Optional[str]:
    home = event.get("home") or {}
    away = event.get("away") or {}
    score = event.get("score") or {}
    if score.get("home") is None or score.get("away") is None:
        return None
    try:
        hs = float(score.get("home"))
        as_ = float(score.get("away"))
    except (TypeError, ValueError):
        return None
    is_home = _matches_side(home, entity_key=entity_key, name=name)
    ours, theirs = (hs, as_) if is_home else (as_, hs)
    if ours > theirs:
        return "W"
    if ours < theirs:
        return "L"
    return "D"


def _latest_standing(
    db: Session,
    *,
    competition_ids: Iterable[str],
    entity_key: str,
    name: str,
) -> Optional[Dict[str, Any]]:
    for competition_id in competition_ids:
        snapshot = (
            db.query(SportsStandingSnapshot)
            .filter(SportsStandingSnapshot.competition_id == competition_id)
            .order_by(SportsStandingSnapshot.captured_at.desc())
            .first()
        )
        if snapshot is None:
            continue
        rows = load_json(snapshot.rows_json, []) or []
        if isinstance(rows, dict):
            rows = rows.get("rows") or rows.get("standings") or rows.get("table") or []
        if not isinstance(rows, list):
            continue
        for standing in rows:
            if not isinstance(standing, dict):
                continue
            team = standing.get("team") if isinstance(standing.get("team"), dict) else standing
            if _matches_side(team, entity_key=entity_key, name=name):
                return {
                    key: value
                    for key, value in standing.items()
                    if key not in {"provider", "source", "source_id", "source_family"}
                }
    return None


def team_profile(
    db: Session,
    *,
    entity_key: str,
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    entity_key = str(entity_key or "").strip()
    name = str(name or "").strip()
    now = datetime.utcnow()
    query = db.query(SportsEvent).filter(
        SportsEvent.canonical_event_id.is_(None),
        or_(SportsEvent.display_eligible.is_(True), SportsEvent.display_eligible.is_(None)),
        SportsEvent.start_time >= now - timedelta(days=400),
        SportsEvent.start_time <= now + timedelta(days=180),
    )
    if sport:
        query = query.filter(SportsEvent.sport_id == sport)
    if competition:
        query = query.filter(SportsEvent.competition_id == competition)
    # Narrow before the limit so unrelated future fixtures cannot evict history.
    import json
    probes = [v for v in (entity_key, name) if v]
    if probes:
        query = query.filter(or_(*[SportsEvent.participants_json.contains(json.dumps(v, ensure_ascii=False)[1:-1], autoescape=True) for v in probes],
                                 *[SportsEvent.participants_json.contains(json.dumps(v, ensure_ascii=True)[1:-1], autoescape=True) for v in probes]))
    rows = query.order_by(SportsEvent.start_time.desc()).limit(1200).all()

    identity: Dict[str, Any] = {}
    cards: List[Dict[str, Any]] = []
    competition_ids: List[str] = []
    resolved_name = name

    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        matched_side = None
        for key in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(key)
            if _matches_side(side, entity_key=entity_key, name=resolved_name):
                matched_side = side
                break
        if matched_side is None:
            continue
        identity = _merge_identity(identity, matched_side)
        if not resolved_name:
            resolved_name = _side_name(matched_side)
        cards.append(_event_card(row))
        if row.competition_id and row.competition_id not in competition_ids:
            competition_ids.append(row.competition_id)

    if not cards:
        return {
            "available": False,
            "entity_key": entity_key,
            "name": name,
            "team": None,
            "fixtures": [],
            "results": [],
            "form": [],
            "standings_position": None,
        }

    cards.sort(key=lambda event: event.get("start_time") or "")
    fixtures = [
        event
        for event in cards
        if event.get("start_time") and event["start_time"] >= now.isoformat()
        and str(event.get("status") or "").lower() not in {"finished", "final", "ft", "ended"}
    ][:20]
    results = [
        event
        for event in reversed(cards)
        if str(event.get("status") or "").lower() in {"finished", "final", "ft", "ended", "aet", "pen"}
    ][:20]
    form = []
    for event in results[:8]:
        result = _result_for_team(event, entity_key=entity_key, name=resolved_name)
        if result:
            form.append(result)

    return {
        "available": True,
        "entity_key": entity_key,
        "sport": sport or (cards[-1].get("sport") if cards else None),
        "team": identity,
        "name": _side_name(identity) or resolved_name,
        "competition_keys": competition_ids,
        "fixtures": fixtures,
        "results": results,
        "form": form,
        "standings_position": _latest_standing(
            db,
            competition_ids=competition_ids,
            entity_key=entity_key,
            name=resolved_name,
        ),
    }


def _iter_player_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        player = value.get("player")
        if isinstance(player, dict):
            merged = dict(player)
            for key in (
                "number",
                "jerseyNumber",
                "position",
                "rating",
                "captain",
                "minutes",
                "goals",
                "assists",
                "points",
                "rebounds",
                "tackles",
                "shots",
                "image",
                "photo",
                "country_id",
                "country",
                "nationality",
            ):
                if value.get(key) not in (None, "") and merged.get(key) in (None, ""):
                    merged[key] = value.get(key)
            yield merged
        if any(key in value for key in ("name", "display_name")) and any(
            key in value for key in ("id", "position", "number", "jerseyNumber", "rating", "image", "photo")
        ):
            yield value
        for child in value.values():
            yield from _iter_player_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_player_dicts(child)


def _matches_player(player: Dict[str, Any], *, player_key: str, name: str) -> bool:
    pid = str(player.get("id") or player.get("player_id") or "").strip()
    if player_key and pid and pid == player_key:
        return True
    pname = str(player.get("display_name") or player.get("name") or "").strip()
    return bool(name and pname and _names_equivalent(name, pname))


def _merge_player(current: Dict[str, Any], player: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(current)
    for key, value in player.items():
        if key in {"provider", "source", "source_id", "source_family"}:
            continue
        if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
            out[key] = value
    return out


def player_profile(
    db: Session,
    *,
    player_key: str,
    name: Optional[str] = None,
    event_id: Optional[str] = None,
    competition_key: Optional[str] = None,
    season: str = '',
    group: str = '',
) -> Dict[str, Any]:
    player_key = str(player_key or "").strip()
    name = str(name or "").strip()
    identity: Dict[str, Any] = {}
    appearances: List[Dict[str, Any]] = []
    profile_ref = None

    query = db.query(SportsEvent, SportsEventDetail).join(
        SportsEventDetail,
        SportsEventDetail.event_id == SportsEvent.event_id,
    ).filter(
        SportsEvent.canonical_event_id.is_(None),
        or_(SportsEvent.display_eligible.is_(True), SportsEvent.display_eligible.is_(None)),
    )
    if event_id:
        primary = query.filter(SportsEvent.event_id == event_id).all()
    else:
        primary = []
    recent = (
        query.order_by(SportsEvent.start_time.desc())
        .limit(400)
        .all()
    )
    seen = set()
    for row, detail in list(primary) + list(recent):
        if row.event_id in seen:
            continue
        seen.add(row.event_id)
        payloads = (
            load_json(detail.lineups_json),
            load_json(detail.statistics_json),
            load_json(detail.incidents_json),
        )
        matched = False
        for payload in payloads:
            for player in _iter_player_dicts(payload):
                if _matches_player(player, player_key=player_key, name=name):
                    # An established numeric identity must not absorb namesakes.
                    pid = str(player.get("id") or player.get("player_id") or "")
                    if player_key.isdigit() and pid and pid != player_key:
                        continue
                    if identity.get("id") and pid and str(identity["id"]) != pid:
                        continue
                    identity = _merge_player(identity, player)
                    ref = player.get('profile_ref')
                    if not ref and row.sport_id == 'football':
                        from collector.source_ids import id_for_family
                        pid = str(player.get('id') or '')
                        if (pid.isdigit() and id_for_family(load_json(row.extra_json, {}) or {}, 'fotmob')
                                and player.get('image') == f'https://images.fotmob.com/image_resources/playerimages/{pid}.png'):
                            ref = {'family':'fotmob','id':pid}
                    if (row.sport_id == 'football' and isinstance(ref, dict) and ref.get('family') == 'fotmob'
                            and str(ref.get('id')) == str(player.get('id')) == str(identity.get('id'))):
                        profile_ref = ref
                    if not name:
                        name = str(player.get("display_name") or player.get("name") or "").strip()
                    matched = True
        if matched:
            appearances.append(_event_card(row))
            if len(appearances) >= 20:
                break

    if not identity and competition_key and player_key.isdigit() and name and not group:
        from collector.football_scorers import scorers
        board = scorers(db, competition_key, season=season, group=group)
        candidates = [r for r in board.get('rows') or [] if str(r.get('player_id')) == player_key]
        if (board.get('available') and board.get('competition_key') == competition_key and
                (not season or board.get('season') == season) and len(candidates) == 1 and
                _names_equivalent(candidates[0].get('name') or '', name)):
            scorer = candidates[0]
            identity = {'id': player_key, 'name': scorer['name'], 'image': scorer.get('photo')}
            profile_ref = {'family': 'fotmob', 'id': player_key}
            # Do not misrepresent season totals as a recorded match performance.
    if identity and profile_ref:
        from collector.player_enrichment import enriched_profile
        identity.update(enriched_profile(profile_ref['id'], str(identity.get('name') or name)))
    identity.pop('profile_ref', None)
    if not identity:
        return {
            "available": False,
            "player_key": player_key,
            "name": name,
            "player": None,
            "appearances": [],
        }
    return {
        "available": True,
        "player_key": player_key,
        "name": str(identity.get("display_name") or identity.get("name") or name),
        "player": identity,
        "appearances": appearances,
    }
