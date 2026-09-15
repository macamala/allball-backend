"""Predictions HTTP API.

Reads cached prediction snapshots. Never invents probabilities, and never
runs the prediction engine during a page request.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth import get_db
from models import SportsPrediction
from prediction_engine import (
    empty_performance_payload,
    empty_prediction_detail,
    empty_prediction_payload,
    market_for_sport,
    serialize_stored_prediction,
)
from sports_provider import get_active_provider

router = APIRouter(tags=["predictions"])


def _latest_snapshots(db: Session, event_ids: List[str]) -> Dict[str, dict]:
    if not event_ids:
        return {}
    rows = (
        db.query(SportsPrediction)
        .filter(SportsPrediction.event_id.in_(event_ids))
        .order_by(SportsPrediction.predicted_at.desc())
        .all()
    )
    out: Dict[str, dict] = {}
    for row in rows:
        if row.event_id not in out:
            out[row.event_id] = serialize_stored_prediction(row)
    return out


@router.get("/predictions")
def list_predictions(
    sport: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    provider = get_active_provider()
    status = provider.status()
    payload = empty_prediction_payload(sport, competition, period)
    payload["connected"] = bool(status.get("connected"))
    payload["provider"] = status.get("provider")
    if sport:
        payload["market"] = market_for_sport(sport)
    if not payload["connected"]:
        return payload

    events = provider.get_events(
        sport=sport,
        competition=competition,
        date_from=date_from,
        date_to=date_to,
    )
    snapshots = _latest_snapshots(
        db, [str(event.get("id") or "") for event in events if event.get("id")]
    )
    items = []
    for event in events:
        event_id = str(event.get("id") or "")
        items.append(
            {
                "event": event,
                "prediction": snapshots.get(event_id),
            }
        )
    payload["items"] = items
    payload["count"] = len(items)
    return payload


@router.get("/predictions/performance")
def prediction_performance(db: Session = Depends(get_db)):
    payload = empty_performance_payload()
    completed = (
        db.query(SportsPrediction)
        .filter(SportsPrediction.evaluated_at.isnot(None))
        .count()
    )
    payload["completed_count"] = int(completed or 0)
    if payload["completed_count"] == 0:
        payload["available"] = False
    return payload


@router.get("/predictions/{event_id}")
def prediction_detail(event_id: str, db: Session = Depends(get_db)):
    provider = get_active_provider()
    status = provider.status()
    payload = empty_prediction_detail(event_id)
    payload["connected"] = bool(status.get("connected"))
    payload["provider"] = status.get("provider")
    event = provider.get_event(event_id)
    if event:
        payload["event"] = event
        payload["statistics"] = provider.get_statistics(event_id)
        payload["availability"] = provider.get_availability(event_id) or []
        home_id = (event.get("home") or {}).get("id")
        away_id = (event.get("away") or {}).get("id")
        form = {}
        if home_id:
            form["home"] = provider.get_team_form(home_id)
        if away_id:
            form["away"] = provider.get_team_form(away_id)
        payload["form"] = form if any(form.values()) else None
        payload["standings"] = provider.get_standings(event.get("competition_key")) or None
    snapshots = _latest_snapshots(db, [event_id])
    stored = snapshots.get(event_id)
    if stored:
        payload["prediction"] = stored
        payload["evidence"] = stored.get("evidence") or []
        payload["model_version"] = stored.get("model_version") or payload["model_version"]
    return payload
