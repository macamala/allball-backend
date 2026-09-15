"""Prediction engine boundary.

Predictions are produced from normalized sports data + a statistical model.
An LLM must never invent probabilities or evidence facts. Its only future
role is to rewrite already-verified evidence into a short explanation.

Until a sports-data provider and model are connected, predict() returns None.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, TypedDict

from sports_provider import NormalizedEvent

MODEL_VERSION = "ninko-unconfigured-0"

# Sport-specific markets. Football uses 1X2; basketball/tennis have no draw.
SPORT_MARKETS = {
    "football": "1x2",
    "basketball": "winner",
    "tennis": "winner",
}

CONFIDENCE_LEVELS = ("low", "medium", "high")

EVIDENCE_TYPES = (
    "recent_form",
    "home_away",
    "league_position",
    "scoring",
    "defensive",
    "head_to_head",
    "availability",
    "expected_lineup",
    "rest",
    "competition_performance",
    "advanced",
)


class PredictionEvidence(TypedDict, total=False):
    """Structured fact the UI may show. Never invent these in production."""

    type: str
    team: Optional[str]
    label: str
    facts: Dict[str, Any]


class PredictionResult(TypedDict, total=False):
    event_id: str
    sport: str
    market: str
    model_version: str
    home_win_pct: Optional[float]
    draw_pct: Optional[float]
    away_win_pct: Optional[float]
    predicted_outcome: Optional[str]
    predicted_score_home: Optional[int]
    predicted_score_away: Optional[int]
    confidence: Optional[str]
    evidence: List[PredictionEvidence]
    explanation: Optional[str]


class PredictionEngine(Protocol):
    def predict(
        self,
        event: NormalizedEvent,
        features: Optional[Dict[str, Any]] = None,
    ) -> Optional[PredictionResult]:
        ...


class UnconfiguredPredictionEngine:
    """Does not invent probabilities. Returns None until a real model exists."""

    version = MODEL_VERSION

    def predict(
        self,
        event: NormalizedEvent,
        features: Optional[Dict[str, Any]] = None,
    ) -> Optional[PredictionResult]:
        return None


def get_prediction_engine() -> PredictionEngine:
    return UnconfiguredPredictionEngine()


def market_for_sport(sport: str) -> Optional[str]:
    return SPORT_MARKETS.get(sport)


def empty_prediction_payload(
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    period: Optional[str] = None,
) -> Dict[str, Any]:
    from sports_provider import provider_status

    return {
        **provider_status(),
        "message": (
            "Predictions are being prepared. Live fixture data will appear "
            "here when sports data is connected."
        ),
        "sport": sport,
        "competition": competition,
        "period": period,
        "market": market_for_sport(sport or ""),
        "model_version": MODEL_VERSION,
        "items": [],
        "count": 0,
        "performance_available": False,
    }


def empty_prediction_detail(event_id: str) -> Dict[str, Any]:
    from sports_provider import provider_status

    return {
        **provider_status(),
        "message": (
            "Predictions are being prepared. Live fixture data will appear "
            "here when sports data is connected."
        ),
        "event_id": event_id,
        "event": None,
        "prediction": None,
        "evidence": [],
        "form": None,
        "statistics": None,
        "h2h": [],
        "availability": [],
        "standings": None,
        "model_version": MODEL_VERSION,
    }


def empty_performance_payload() -> Dict[str, Any]:
    return {
        "available": False,
        "reason": (
            "Model performance is shown only after enough real completed "
            "predictions exist. Missed predictions are never dropped."
        ),
        "windows": {"last_7_days": None, "last_30_days": None, "season": None},
        "by_sport": {},
        "model_version": MODEL_VERSION,
    }


def apply_result(row: Any, actual_outcome: str, at: Optional[datetime] = None) -> Any:
    """Evaluate a saved snapshot. Never mutates stored probabilities or evidence."""
    row.evaluated_at = at or datetime.utcnow()
    row.actual_outcome = actual_outcome
    if row.predicted_outcome is not None:
        row.was_correct = actual_outcome == row.predicted_outcome
    return row


def serialize_stored_prediction(row: Any) -> Dict[str, Any]:
    """Public shape for a persisted (immutable) prediction snapshot."""
    import json

    evidence = []
    raw = getattr(row, "evidence_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                evidence = parsed
        except (TypeError, ValueError):
            evidence = []
    return {
        "event_id": row.event_id,
        "sport": row.sport,
        "competition_key": row.competition_key,
        "market": row.market,
        "model_version": row.model_version,
        "predicted_at": row.predicted_at.isoformat() + "Z" if row.predicted_at else None,
        "home_win_pct": row.home_win_pct,
        "draw_pct": row.draw_pct,
        "away_win_pct": row.away_win_pct,
        "predicted_outcome": row.predicted_outcome,
        "predicted_score_home": row.predicted_score_home,
        "predicted_score_away": row.predicted_score_away,
        "confidence": row.confidence,
        "evidence": evidence,
        "explanation": row.explanation,
        "evaluated_at": row.evaluated_at.isoformat() + "Z" if row.evaluated_at else None,
        "actual_outcome": row.actual_outcome,
        "was_correct": row.was_correct,
    }
