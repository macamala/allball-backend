from collector.espn_tennis_breadth import parse_board


def test_espn_tennis_flat_event_shape():
    payload = {
        "events": [{
            "id": "flat-1",
            "name": "Wimbledon",
            "date": "2026-09-25T10:00:00Z",
            "status": {"type": {"name": "STATUS_FINAL", "shortDetail": "Final"}},
            "competitors": [
                {
                    "homeAway": "home",
                    "athlete": {"id": "1", "displayName": "Player A"},
                    "linescores": [{"value": 6}, {"value": 7}],
                },
                {
                    "homeAway": "away",
                    "athlete": {"id": "2", "displayName": "Player B"},
                    "linescores": [{"value": 4}, {"value": 5}],
                },
            ],
        }]
    }
    rows = parse_board(payload)
    assert len(rows) == 1
    assert rows[0]["competition"] == "Wimbledon"
    assert rows[0]["home"]["name"] == "Player A"
    assert rows[0]["away"]["name"] == "Player B"
    assert rows[0]["status"] == "finished"
    assert rows[0]["score"] == {"home": 2, "away": 0}
    assert len(rows[0]["periods"]) == 2


def test_espn_tennis_grouped_tournament_shape():
    payload = {
        "events": [{
            "id": "tokyo-2026",
            "name": "Tokyo Open",
            "groupings": [{
                "grouping": {"displayName": "Men's Singles"},
                "competitions": [{
                    "id": "match-22",
                    "date": "2026-09-25T04:30:00Z",
                    "status": {"type": {"name": "STATUS_IN_PROGRESS", "shortDetail": "2nd"}},
                    "competitors": [
                        {
                            "homeAway": "away",
                            "athlete": {"id": "20", "displayName": "Player B"},
                            "linescores": [{"value": 4}, {"value": 2}],
                        },
                        {
                            "homeAway": "home",
                            "athlete": {"id": "10", "displayName": "Player A"},
                            "linescores": [{"value": 6}, {"value": 3}],
                        },
                    ],
                }],
            }],
        }]
    }
    rows = parse_board(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "espn-tennis:match-22"
    assert row["competition"] == "Tokyo Open"
    assert row["round"] == "Men's Singles"
    assert row["home"]["name"] == "Player A"
    assert row["away"]["name"] == "Player B"
    assert row["status"] == "live"
    assert row["extra"]["source_event_ids"] == {"espn-json": "match-22"}


def test_espn_tennis_scheduled_match_hides_placeholder_score():
    payload = {
        "events": [{
            "id": "future-1",
            "name": "Future Event",
            "date": "2026-09-26T08:00:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "shortDetail": "Scheduled"}},
            "competitors": [
                {"homeAway": "home", "athlete": {"displayName": "Player A"}},
                {"homeAway": "away", "athlete": {"displayName": "Player B"}},
            ],
        }]
    }
    row = parse_board(payload)[0]
    assert row["status"] == "scheduled"
    assert row["score"] == {"home": None, "away": None}
