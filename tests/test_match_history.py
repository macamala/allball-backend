from datetime import datetime

from collector.models import SportsEvent
from collector.provider import _history_context_from_rows
from collector.util import dump_json


def event(event_id, when, home, away, home_score=None, away_score=None, competition="england-premier-league", status="finished"):
    return SportsEvent(
        event_id=event_id,
        sport_id="football",
        competition_id=competition,
        event_family="team_match",
        start_time=when,
        status=status,
        participants_json=dump_json({"home": home, "away": away}),
        score_json=dump_json({"home": home_score, "away": away_score}),
    )


def test_match_history_builds_h2h_and_recent_form_from_canonical_rows():
    current = event(
        "current",
        datetime(2026, 9, 23, 20, 0),
        {"id": "ars", "name": "Arsenal"},
        {"id": "che", "name": "Chelsea"},
        status="scheduled",
    )
    rows = [
        event("recent-h2h", datetime(2026, 5, 1, 19, 0), {"id": "che", "name": "Chelsea"}, {"id": "ars", "name": "Arsenal"}, 1, 2),
        event("older-h2h", datetime(2026, 1, 10, 18, 0), {"id": "ars", "name": "Arsenal"}, {"id": "che", "name": "Chelsea"}, 0, 0),
        event("ars-form", datetime(2025, 12, 20, 18, 0), {"id": "ars", "name": "Arsenal"}, {"id": "liv", "name": "Liverpool"}, 3, 1),
        event("che-form", datetime(2025, 12, 19, 18, 0), {"id": "mci", "name": "Manchester City"}, {"id": "che", "name": "Chelsea"}, 2, 0),
    ]

    h2h, form = _history_context_from_rows(current, rows)

    assert [row["id"] for row in h2h] == ["recent-h2h", "older-h2h"]
    assert h2h[0]["label"] == "Chelsea 1–2 Arsenal"
    assert form["home"]["summary"] == "W · D · W"
    assert form["away"]["summary"] == "L · D · L"
    assert form["home"]["results"][0]["outcome"] == "W"
    assert form["away"]["results"][0]["outcome"] == "L"
