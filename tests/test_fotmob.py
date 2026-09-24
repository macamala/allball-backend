from collector.adapters import FetchRequest, FetchResult
from collector.adapters_fotmob import FotMobAdapter, match_to_event


def test_fotmob_match_to_event_preserves_null_scores_when_scheduled():
    event = match_to_event(
        {
            "id": 1,
            "home": {"name": "A", "score": 0},
            "away": {"name": "B", "score": 0},
            "status": {"started": False, "finished": False, "utcTime": "2026-09-20T14:00:00.000Z"},
            "_league": {"id": 212},
        },
        "hungary-nb-i",
    )
    assert event["status"] == "scheduled"
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None
    assert event["source_family"] == "fotmob"


def test_fotmob_preserves_real_zero_zero():
    event = match_to_event(
        {
            "id": 2,
            "home": {"name": "A"},
            "away": {"name": "B"},
            "status": {"started": True, "finished": True, "scoreStr": "0-0"},
            "_league": {"id": 53},
        },
        "france-ligue-1",
    )
    assert event["status"] == "finished"
    assert event["score"]["home"] == 0
    assert event["score"]["away"] == 0


def test_fotmob_adapter_filters_shared_date_board_by_league_id():
    payload = {
        "leagues": [
            {
                "id": 212,
                "name": "Nemzeti Bajnokság I",
                "ccode": "HUN",
                "matches": [
                    {
                        "id": 99,
                        "home": {"name": "Ferencvaros", "score": 2},
                        "away": {"name": "Ujpest", "score": 1},
                        "status": {
                            "started": True,
                            "finished": False,
                            "scoreStr": "2-1",
                            "liveTime": {"short": "64'"},
                        },
                    }
                ],
            }
        ]
    }
    adapter = FotMobAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    from collector import adapters_fotmob as mod

    mod._BOARD.clear()
    result = adapter.fetch(FetchRequest(capability="live", competition_id="hungary-nb-i"))
    assert result.ok
    assert result.events[0]["status"] == "live"
    assert result.events[0]["score"] == {"home": 2, "away": 1, "minute": "64'"}



def test_fotmob_preserves_postponed_status_from_reason():
    event = match_to_event(
        {
            "id": 3,
            "home": {"name": "FAR Rabat", "score": 0},
            "away": {"name": "Raja Casablanca", "score": 0},
            "status": {
                "started": False,
                "finished": False,
                "utcTime": "2026-09-24T15:00:00.000Z",
                "reason": {"short": "Postp.", "long": "Postponed"},
            },
            "_league": {"id": 530, "name": "Botola Pro"},
        },
        "morocco-botola",
    )
    assert event["status"] == "postponed"
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None
    assert event["extra"]["source_status"] == "Postp."


def test_fotmob_preserves_delayed_status_from_reason():
    event = match_to_event(
        {
            "id": 4,
            "home": {"name": "A"},
            "away": {"name": "B"},
            "status": {
                "started": False,
                "finished": False,
                "reason": {"short": "Delayed"},
            },
            "_league": {"id": 53},
        },
        "france-ligue-1",
    )
    assert event["status"] == "delayed"



def test_fotmob_live_board_refreshes_after_ttl(monkeypatch):
    from collector import adapters_fotmob as mod

    calls = []
    payloads = [
        {
            "leagues": [{
                "id": 212,
                "name": "Nemzeti Bajnokság I",
                "matches": [{
                    "id": 99,
                    "home": {"name": "A", "score": 0},
                    "away": {"name": "B", "score": 0},
                    "status": {"started": True, "finished": False, "scoreStr": "0-0"},
                }],
            }]
        },
        {
            "leagues": [{
                "id": 212,
                "name": "Nemzeti Bajnokság I",
                "matches": [{
                    "id": 99,
                    "home": {"name": "A", "score": 1},
                    "away": {"name": "B", "score": 0},
                    "status": {"started": True, "finished": False, "scoreStr": "1-0"},
                }],
            }]
        },
    ]

    clock = {"value": 100.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock["value"])

    def getter(url):
        calls.append(url)
        index = 0 if len(calls) <= 2 else 1
        return FetchResult(ok=True, http_status=200, payload=payloads[index])

    mod._BOARD.clear()
    mod._BOARD_AT.clear()
    adapter = FotMobAdapter(getter=getter)

    first = adapter.fetch(FetchRequest(capability="live_scores", competition_id="hungary-nb-i"))
    assert first.events[0]["score"]["home"] == 0

    clock["value"] += mod.LIVE_BOARD_TTL_SECONDS + 0.1
    second = adapter.fetch(FetchRequest(capability="live_scores", competition_id="hungary-nb-i"))
    assert second.events[0]["score"]["home"] == 1
    assert len(calls) == 4


def test_fotmob_live_board_uses_only_yesterday_and_today():
    from collector import adapters_fotmob as mod

    urls = []
    def getter(url):
        urls.append(url)
        return FetchResult(ok=True, http_status=200, payload={"leagues": []})

    mod._BOARD.clear()
    mod._BOARD_AT.clear()
    FotMobAdapter(getter=getter).fetch(
        FetchRequest(capability="live_scores", competition_id="hungary-nb-i")
    )
    assert len(urls) == 2
