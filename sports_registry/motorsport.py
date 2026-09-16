"""Motorsport domain contracts for multiple series.

Model: series → season → event/weekend → session.
No schedules or results are seeded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

SESSION_TYPES = ("practice", "qualifying", "sprint", "race")

SERIES_IDS = (
    "formula-1",
    "formula-2",
    "formula-3",
    "motogp",
    "moto2",
    "moto3",
    "nascar",
    "indycar",
    "wec",
    "wrc",
    "formula-e",
    "supercars",
)


class MotorsportSeries(TypedDict, total=False):
    series_id: str
    sport_id: str
    name: str
    active: bool


class MotorsportSeason(TypedDict, total=False):
    series_id: str
    season: str


class MotorsportWeekend(TypedDict, total=False):
    event_id: str
    series_id: str
    season: Optional[str]
    name: Optional[str]
    country_id: Optional[str]
    start_time: Optional[str]


class MotorsportSession(TypedDict, total=False):
    session_id: str
    event_id: str
    session_type: str
    start_time: Optional[str]
    status: str
    classification: List[Dict[str, Any]]


def empty_motorsport_payload(series_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "sport_id": "motorsport",
        "series_id": series_id,
        "connected": False,
        "series": [],
        "events": [],
        "sessions": [],
        "message": "Motorsport sessions appear when a sports-data provider is connected.",
    }
