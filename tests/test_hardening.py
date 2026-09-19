from collector.adapters import FetchRequest
from collector.adapters_thesportsdb import TheSportsDbAdapter, _event
from collector.live_state import guard_future_status
from collector.match import same_canonical_event
from collector.normalize import normalize_event
from collector.timezones import resolve_event_time


def test_bundesliga_two_hour_kickoff_is_same_event():
    openliga = normalize_event(
        {
            "home": {"name": "FC Bayern München"},
            "away": {"name": "FC Schalke 04"},
            "start_time": "2026-09-19T15:30:00Z",
            "source_family": "openligadb",
            "season": "2026",
        },
        sport_id="football",
        competition_id="germany-bundesliga",
    )
    tsdb = normalize_event(
        {
            "home": {"name": "Bayern Munich"},
            "away": {"name": "Schalke 04"},
            "start_time": "2026-09-19T17:30:00",
            "source_family": "thesportsdb",
            "season": "2026",
        },
        sport_id="football",
        competition_id="germany-bundesliga",
    )
    from collector.aliases import canonical_name_key

    # names must match after alias/slug; use identical names for the identity contract
    openliga["home"]["name"] = tsdb["home"]["name"] = "FC Bayern München"
    openliga["away"]["name"] = tsdb["away"]["name"] = "FC Schalke 04"
    openliga["home"]["slug"] = tsdb["home"]["slug"] = canonical_name_key("FC Bayern München")
    openliga["away"]["slug"] = tsdb["away"]["slug"] = canonical_name_key("FC Schalke 04")
    assert same_canonical_event(openliga, tsdb)
    week_later = dict(tsdb)
    week_later["start_time"] = "2026-09-26T15:30:00Z"
    week_later["_resolved_time"] = resolve_event_time(
        week_later["start_time"], competition_id="germany-bundesliga", provider="openligadb"
    )
    assert not same_canonical_event(openliga, week_later)


def test_nested_iso_timestamp_resolves():
    resolved = resolve_event_time(
        {"iso": "2026-09-18T19:00:00Z", "time": "20:00"},
        competition_id="womens-super-league",
        provider="bbc-sport",
    )
    assert resolved.method == "explicit_source_offset"
    assert resolved.utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-09-18T19:00:00Z"
    resolved = resolve_event_time(
        "2026-09-19T17:30:00",
        competition_id="germany-bundesliga",
        provider="thesportsdb",
    )
    assert resolved.method == "competition_timezone"
    assert resolved.source_timezone == "Europe/Berlin"
    assert resolved.utc.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-09-19T15:30:00Z"


def test_future_volleyball_score_is_scheduled():
    assert guard_future_status("finished", "2026-09-21T19:00:00Z", inferred=True, sport_id="volleyball") == "scheduled"
    event = normalize_event(
        {
            "home": {"name": "Italy"},
            "away": {"name": "Poland"},
            "start_time": "2026-09-21T19:00:00Z",
            "status": "finished",
            "status_inferred": True,
            "score": {"home": 0, "away": 0},
        },
        sport_id="volleyball",
        competition_id="cev-eurovolley-men",
    )
    assert event["status"] == "scheduled"


def test_tsdb_family_cooldown_skips_http(monkeypatch):
    from collector.family_health import note_family_failure, reset_family_health

    reset_family_health()
    note_family_failure("thesportsdb", http_status=429, error_type="RATE_LIMITED", retry_after_s=120)
    calls = []

    def getter(url, timeout=None):
        calls.append(url)
        raise AssertionError("should not hit network")

    adapter = TheSportsDbAdapter(getter=getter)
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="nba", source_competition_id="4387"))
    assert result.classification == "RATE_LIMITED"
    assert calls == []
    reset_family_health()


def test_tsdb_does_not_mark_ns_future_as_finished():
    raw = {
        "idEvent": "1",
        "strHomeTeam": "Italy",
        "strAwayTeam": "Poland",
        "strStatus": "NS",
        "intHomeScore": "0",
        "intAwayScore": "0",
        "dateEvent": "2026-09-21",
        "strTime": "19:00:00",
        "strSeason": "2026",
    }
    event = _event(raw, "cev-eurovolley-men")
    assert event["status"] == "scheduled"
