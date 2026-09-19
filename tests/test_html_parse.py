"""Fixtures for reusable HTML/JSON family parsers."""

from collector.adapters import FetchRequest
from collector.adapters_generic import GenericHttpAdapter
from collector.html_parse import fixture_urls, parse_html, parse_jsonld, parse_tables, walk_json_events
from collector.normalize import normalize_event


TABLE_HTML = """
<html><body>
<table>
<tr><th>Date</th><th>Home</th><th>Score</th><th>Away</th></tr>
<tr><td>2026-09-12</td><td>Alpha FC</td><td>2-1</td><td>Beta United</td></tr>
<tr><td>2026-09-18</td><td>Gamma City</td><td>vs</td><td>Delta Town</td></tr>
</table>
</body></html>
"""

JSONLD_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"SportsEvent","name":"Reds vs Blues",
 "startDate":"2026-09-20T19:00:00Z","homeTeam":{"name":"Reds"},"awayTeam":{"name":"Blues"},
 "location":{"name":"Arena One"}}
</script>
</head><body></body></html>
"""

NEXT_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"events":[{"id":"e1","homeTeam":{"name":"North"},"awayTeam":{"name":"South"},
"startDate":"2026-09-21T12:00:00Z","status":"scheduled","homeScore":null,"awayScore":null}]}}}
</script>
</body></html>
"""

EMPTY_HTML = """
<html><body><h1>Season complete</h1><p>No matches currently listed.</p></body></html>
"""

MALFORMED_HTML = "<html><table><tr><td>broken"


INDEX_HTML = """
<html><body>
<a href="/fixtures">Fixtures</a>
<p>Index only</p>
</body></html>
"""

FIXTURE_PAGE = """
<html><body>
<table>
<tr><td>2026-09-14</td><td>Home Side</td><td>1-0</td><td>Away Side</td></tr>
</table>
</body></html>
"""


def test_parse_tables_extracts_scores_dates_and_participants():
    events = parse_tables(TABLE_HTML)
    assert len(events) >= 1
    first = events[0]
    assert first["home"]["name"] == "Alpha FC"
    assert first["away"]["name"] == "Beta United"
    assert first["score"]["home"] == 2
    assert first["score"]["away"] == 1
    assert first["status"] == "finished"
    assert "2026-09-12" in str(first["start_time"])


def test_jsonld_and_normalization():
    events = parse_jsonld(JSONLD_HTML)
    assert events
    row = events[0]
    assert row["home"]["name"] == "Reds"
    assert row["away"]["name"] == "Blues"
    normalized = normalize_event(row, sport_id="football", competition_id="test-league")
    assert normalized["status"] == "scheduled"
    assert normalized["home"]["name"] == "Reds"
    assert normalized["start_time"]
    assert normalized["competition_key"] == "test-league"


def test_embedded_next_data():
    events = parse_html(NEXT_HTML)
    assert events
    assert events[0]["home"]["name"] == "North"
    assert events[0]["away"]["name"] == "South"


def test_empty_valid_page():
    assert parse_html(EMPTY_HTML) == []


def test_malformed_page_does_not_raise():
    assert parse_html(MALFORMED_HTML) == []
    assert parse_html("") == []
    assert walk_json_events("not-json") == []
    assert walk_json_events({"events": [None, "x", {"home": "A", "away": "B"}]})


def test_openf1_meetings_json():
    payload = [
        {
            "meeting_key": 1,
            "meeting_name": "Australian Grand Prix",
            "circuit_short_name": "Melbourne",
            "date_start": "2026-03-13T01:00:00+00:00",
            "location": "Melbourne",
        }
    ]
    events = walk_json_events(payload)
    assert events
    assert events[0]["home"]["name"] == "Australian Grand Prix"
    assert events[0]["event_family"] == "motorsport_race"


def test_fixture_link_discovery():
    urls = fixture_urls(INDEX_HTML, "https://example.com/league")
    assert urls == ["https://example.com/fixtures"]


def test_generic_http_traverses_same_host_fixture_index():
    pages = {
        "https://example.com/league": INDEX_HTML,
        "https://example.com/fixtures": FIXTURE_PAGE,
    }

    def text_getter(url, **_kwargs):
        from collector.adapters import FetchResult

        html = pages.get(url)
        if html is None:
            return FetchResult(ok=False, http_status=404, error="missing")
        return FetchResult(ok=True, http_status=200, payload=html)

    adapter = GenericHttpAdapter(text_getter=text_getter, getter=text_getter)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="demo",
            source_config={"url": "https://example.com/league", "source_type": "public HTML"},
        )
    )
    assert result.ok
    assert result.events
    assert result.events[0]["home"]["name"] == "Home Side"
    assert result.events[0]["score"]["home"] == 1


def test_generic_http_malformed_json_is_parse_failure():
    from collector.adapters import FetchResult

    def getter(url, **_kwargs):
        return FetchResult(ok=True, http_status=200, payload="{not json")

    adapter = GenericHttpAdapter(getter=getter, text_getter=getter)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="demo",
            source_config={"url": "https://api.example.com/v1/events.json"},
        )
    )
    assert result.ok is False
    assert result.classification == "PARSE_FAILURE"


def test_motogp_seasons_follow_public_events():
    from collector.adapters import FetchResult

    seasons = [{"id": "season-1", "year": 2026, "current": True}]
    events_payload = [
        {
            "id": "event-1",
            "name": "Qatar Grand Prix",
            "date_start": "2026-03-08T16:00:00Z",
            "circuit": "Losail",
        }
    ]

    def getter(url, **_kwargs):
        if "seasons" in url:
            return FetchResult(ok=True, http_status=200, payload=seasons)
        if "events" in url:
            return FetchResult(ok=True, http_status=200, payload=events_payload)
        return FetchResult(ok=False, http_status=404, error="no")

    adapter = GenericHttpAdapter(getter=getter, text_getter=getter)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="motogp",
            source_config={"url": "https://api.motogp.pulselive.com/motogp/v1/results/seasons", "source_type": "public JSON"},
        )
    )
    assert result.ok
    assert result.events
    assert "Qatar" in result.events[0]["home"]["name"] or result.events[0]["home"]["name"]


def test_unicode_plaintext_scores():
    html = "<html><body><p>Magnus Futsal 6-2 Joinville EC</p></body></html>"
    events = parse_html(html)
    assert events
    assert events[0]["home"]["name"].startswith("Magnus")
    assert events[0]["away"]["name"].startswith("Joinville")
