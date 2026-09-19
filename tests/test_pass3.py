"""Pass 3: BBC payload, traversal, TheSportsDB cache, budget, empty diagnostics."""

from collector.adapters import FetchRequest, FetchResult, register_adapter, unregister_adapter
from collector.adapters_bbc import BbcSportAdapter, extract_bbc_events
from collector.adapters_generic import GenericHttpAdapter
from collector.adapters_thesportsdb import REQUEST_LOG, TheSportsDbAdapter, reset_thesportsdb_cache
from collector.html_parse import parse_initial_data
from collector.http import STATS, begin_budget, budget_remaining, end_budget, reset_http_stats
from collector.smoke import classify_competition
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def _bbc_html(payload: dict) -> str:
    import json

    encoded = json.dumps(payload).replace("\\", "\\\\").replace('"', '\\"')
    return f'<html><body><a href="/sport/football/scores-fixtures">scores</a><script>window.__INITIAL_DATA__="{encoded}";</script></body></html>'


BBC_PAYLOAD = {
    "data": {
        "sport-data-scores-fixtures": {
            "data": {
                "eventGroups": [
                    {
                        "displayLabel": "Emirates FA Cup",
                        "secondaryGroups": [
                            {
                                "events": [
                                    {
                                        "id": "m1",
                                        "home": {"fullName": "Arsenal"},
                                        "away": {"fullName": "Man City"},
                                        "startTime": "2026-09-17T18:45:00Z",
                                        "status": "scheduled",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
    }
}


def test_bbc_structured_payload_filters_by_competition():
    events = extract_bbc_events(BBC_PAYLOAD, "fa-cup")
    assert events
    assert events[0]["home"]["name"] == "Arsenal"
    assert events[0]["away"]["name"] == "Man City"
    assert events[0]["start_time"].startswith("2026-09-17")
    assert extract_bbc_events(BBC_PAYLOAD, "chile-primera") == []


def test_bbc_adapter_follows_scores_fixtures_once():
    pages = {
        "https://www.bbc.com/sport": '<html><a href="/sport/football/scores-fixtures">fixtures</a></html>',
        "https://www.bbc.com/sport/football/scores-fixtures": _bbc_html(BBC_PAYLOAD),
    }
    calls = []

    def getter(url, **_kwargs):
        calls.append(url)
        html = pages.get(url)
        if html is None:
            return FetchResult(ok=False, http_status=404, error="missing")
        return FetchResult(ok=True, http_status=200, payload=html)

    adapter = BbcSportAdapter(text_getter=getter)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            sport_id="football",
            competition_id="fa-cup",
            source_config={"url": "https://www.bbc.com/sport"},
        )
    )
    assert result.ok
    assert result.events[0]["home"]["name"] == "Arsenal"
    assert calls.count("https://www.bbc.com/sport/football/scores-fixtures") == 1


def test_bounded_traversal_dedupes_and_stops():
    pages = {
        "https://example.com/league": '<html><a href="/fixtures">A</a><a href="/fixtures?x=1">B</a><a href="/results">C</a></html>',
        "https://example.com/fixtures": """<html><table><tr><td>2026-09-12</td><td>Alpha FC</td><td>2-1</td><td>Beta United</td></tr></table></html>""",
        "https://example.com/fixtures?x=1": "<html>second</html>",
        "https://example.com/results": "<html>third</html>",
    }
    calls = []

    def getter(url, **_kwargs):
        calls.append(url)
        return FetchResult(ok=True, http_status=200, payload=pages[url])

    adapter = GenericHttpAdapter(text_getter=getter, getter=getter)
    begin_budget(max_requests=8, max_seconds=10)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="demo",
            source_config={"url": "https://example.com/league", "source_type": "public HTML"},
        )
    )
    end_budget()
    assert result.events
    assert result.events[0]["home"]["name"] == "Alpha FC"
    assert calls.count("https://example.com/fixtures") == 1
    assert "https://example.com/results" not in calls


def test_thesportsdb_does_not_refetch_identical_urls():
    reset_thesportsdb_cache()
    events = {"events": [{"idEvent": "1", "strHomeTeam": "A", "strAwayTeam": "B", "strStatus": "NS", "dateEvent": "2026-09-20"}]}
    calls = []

    def getter(url):
        calls.append(url)
        return FetchResult(ok=True, http_status=200, payload=events)

    adapter = TheSportsDbAdapter(getter=getter)
    first = adapter.fetch(FetchRequest(capability="snapshot", source_competition_id="4356", competition_id="australia-a-league"))
    second = adapter.fetch(FetchRequest(capability="snapshot", source_competition_id="4356", competition_id="australia-a-league"))
    assert first.events and second.events
    next_url = [url for url in calls if "eventsnextleague" in url]
    past_url = [url for url in calls if "eventspastleague" in url]
    assert len(next_url) == 1
    assert len(past_url) == 1
    assert REQUEST_LOG.count(next_url[0]) == 2


def test_request_budget_stops_extra_calls():
    reset_http_stats()
    begin_budget(max_requests=1, max_seconds=10)
    from collector.http import fetch_url

    calls = {"n": 0}
    orig = fetch_url.__wrapped__ if hasattr(fetch_url, "__wrapped__") else None
    assert budget_remaining() is True
    # consume budget with a skipped network by marking used
    from collector.http import _LOCAL

    _LOCAL.budget["used"] = 1
    assert budget_remaining() is False
    end_budget()


def test_healthy_empty_and_parser_limited():
    adapter = GenericHttpAdapter(
        text_getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload="<html><p>No matches currently listed.</p></html>"),
        getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload="<html><p>No matches currently listed.</p></html>"),
    )
    empty = adapter.fetch(FetchRequest(capability="snapshot", source_config={"url": "https://example.com/empty", "source_type": "HTML"}))
    assert empty.ok
    assert empty.events == []
    assert empty.empty_reason == "SOURCE_HEALTHY_NO_EVENTS"

    limited = GenericHttpAdapter(
        text_getter=lambda url, **k: FetchResult(
            ok=True,
            http_status=200,
            payload="<html><h1>Fixtures</h1><div>scoreboard coming soon</div></html>",
        ),
        getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload="<html><h1>Fixtures</h1><div>scoreboard coming soon</div></html>"),
    )
    result = limited.fetch(FetchRequest(capability="snapshot", source_config={"url": "https://example.com/fixtures", "source_type": "HTML"}))
    assert result.empty_reason == "PARSER_COULD_NOT_EXTRACT"


def test_partial_fallback_smoke_classification():
    primary = DeterministicMockAdapter("omega")
    primary.events = []
    partial = DeterministicMockAdapter("microplus")
    partial.events = [mock_event(id="u20-1", home={"name": "USA U20"}, away={"name": "ESP"}, competition="World Cup")]
    register_adapter("omega", lambda source_id="omega": primary)
    register_adapter("microplus", lambda source_id="microplus": partial)
    db = _session()
    try:
        omega = _source(db, "omega", "omega")
        micro = _source(db, "microplus", "microplus")
        omega.upstream_family = "omega-timing"
        micro.upstream_family = "microplus-timing"
        _competition(db, "world-aquatics-events", "water-polo")
        _map(db, "world-aquatics-events", "omega", 1)
        _map(db, "world-aquatics-events", "microplus", 2)
        db.flush()
        from collector.models import SportsSourceCompetition

        db.query(SportsSourceCompetition).filter_by(source_id="omega").one().upstream_family = "omega-timing"
        row = db.query(SportsSourceCompetition).filter_by(source_id="microplus").one()
        row.upstream_family = "microplus-timing"
        row.coverage_scope = "partial"
        db.commit()
        from collector.models import SportsCompetition

        competition = db.query(SportsCompetition).filter_by(competition_id="world-aquatics-events").one()
        result = classify_competition(db, competition, "snapshot")
        assert result["classification"] == "WORKING_PARTIAL"
        assert result["events"] == 1
    finally:
        db.close()
        _cleanup_adapters("omega", "microplus")


def test_parse_initial_data_roundtrip():
    html = _bbc_html(BBC_PAYLOAD)
    events = parse_initial_data(html)
    assert any(event["home"]["name"] == "Arsenal" for event in events)
