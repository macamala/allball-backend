"""Racing domain contracts for horse, greyhound, and harness racing.

Hierarchy: Sport → Country → Venue/Track → Meeting → Race → Runner.
No tracks, meetings, races, or runners are seeded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

RACING_SPORTS = ("horse-racing", "greyhound-racing", "harness-racing")


class RacingVenue(TypedDict, total=False):
    venue_id: str
    name: str
    country_id: Optional[str]
    sport_id: str


class RacingMeeting(TypedDict, total=False):
    meeting_id: str
    venue_id: Optional[str]
    country_id: Optional[str]
    sport_id: str
    start_time: Optional[str]
    status: Optional[str]


class RacingRunner(TypedDict, total=False):
    runner_id: str
    race_id: str
    name: str
    number: Optional[int]
    barrier: Optional[int]
    box: Optional[int]
    jockey: Optional[str]
    trainer: Optional[str]
    weight: Optional[str]
    horse: Optional[str]
    dog: Optional[str]


class RacingRace(TypedDict, total=False):
    race_id: str
    venue: Optional[str]
    country_id: Optional[str]
    meeting_id: Optional[str]
    race_number: Optional[int]
    race_name: Optional[str]
    start_time: Optional[str]
    distance: Optional[str]
    status: str
    runners: List[RacingRunner]
    result: Optional[List[Dict[str, Any]]]


def empty_race_payload(sport_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "sport_id": sport_id,
        "connected": False,
        "venues": [],
        "meetings": [],
        "races": [],
        "runners": [],
        "message": "Racing fixtures appear when a sports-data provider is connected.",
    }
