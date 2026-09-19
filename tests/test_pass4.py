"""Pass 4: host-family parsers, 429 failover, capability vs window, URL inference."""

from collector.adapters import FetchRequest, FetchResult, register_adapter
from collector.adapters_generic import GenericHttpAdapter
from collector.adapters_sites import events_for_host, parse_cycling, parse_nrl, parse_racing, parse_wnba
from collector.family_catalog import infer_url
from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition
from collector.smoke import classify_competition
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


NEXT_NRL = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"fixtures":[{"id":"n1","homeTeam":{"name":"Broncos"},"awayTeam":{"name":"Storm"},
"startDate":"2026-09-18T09:00:00Z","status":"scheduled"}]}}}
</script>
</body></html>
"""

NEXT_WNBA = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"games":[{"id":"w1","home":{"name":"Aces"},"away":{"name":"Liberty"},
"startTime":"2026-09-19T00:00:00Z","status":"scheduled"}]}}}
</script>
</body></html>
"""

CYCLING_HTML = """
<html><body>
<p>Stage 12 Alpe d'Huez 2026-07-16</p>
<p>Stage 13 Gap 2026-07-17</p>
</body></html>
"""

RACING_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"meetings":[{"id":"m1","homeTeam":{"name":"Race 1"},"awayTeam":{"name":"Wentworth Park"},
"startDate":"2026-09-17T08:00:00Z"}]}}}
</script>
</body></html>
"""


def test_nrl_and_wnba_next_data():
    nrl = parse_nrl(NEXT_NRL)
    assert nrl and nrl[0]["home"]["name"] == "Broncos"
    wnba = parse_wnba(NEXT_WNBA)
    assert wnba and wnba[0]["home"]["name"] == "Aces"
    assert events_for_host(NEXT_NRL, "https://www.nrl.com/draw")
    assert events_for_host(NEXT_WNBA, "https://www.wnba.com/schedule")


def test_cycling_and_racing_family_parsers():
    stages = parse_cycling(CYCLING_HTML)
    assert any("Stage 12" in (event.get("home") or {}).get("name", "") for event in stages)
    races = parse_racing(RACING_HTML)
    assert races
    assert races[0].get("event_family") == "racing"


def test_host_adapter_used_by_generic_http():
    adapter = GenericHttpAdapter(
        text_getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload=NEXT_WNBA),
        getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload=NEXT_WNBA),
    )
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="wnba",
            source_config={"url": "https://www.wnba.com/schedule", "source_type": "HTML"},
        )
    )
    assert result.events
    assert result.events[0]["home"]["name"] == "Aces"


def test_infer_url_prefers_source_slug_over_family_default():
    url = infer_url("lnf-web", "lnfoficial-com-br-tabela-classificacao", "", "futsal")
    assert "lnfoficial.com.br" in url
    assert "lnfs.es" not in url
    vpf = infer_url("vpf-web", "vpf.vn V.League 1 table", "fetch 200 points table", "football")
    assert "vpf.vn" in vpf
    rugby = infer_url("super-rugby-web", "super.rugby fixtures/tables", "fetch 200 fixtures hub", "rugby")
    assert rugby == "https://super.rugby"


def test_rate_limit_on_primary_uses_fallback():
    fallback = DeterministicMockAdapter("fifa")
    fallback.events = [mock_event(id="afcon-1", home={"name":"Senegal"}, away={"name":"Egypt"}, competition="AFCON")]

    class Limited:
        adapter_key = "limited"

        def __init__(self, source_id="limited"):
            self.source_id = source_id

        def fetch(self, request):
            return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")

    register_adapter("limited", Limited)
    register_adapter("fifa", lambda source_id="fifa": fallback)
    db = _session()
    try:
        limited = _source(db, "pass4-limited", "limited")
        fifa = _source(db, "pass4-fifa", "fifa")
        limited.upstream_family = "thesportsdb"
        fifa.upstream_family = "fifa-digital"
        _competition(db, "pass4-afcon", "football")
        _map(db, "pass4-afcon", "pass4-limited", 1)
        _map(db, "pass4-afcon", "pass4-fifa", 2)
        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="pass4-limited").one().upstream_family = "thesportsdb"
        db.query(SportsSourceCompetition).filter_by(source_id="pass4-fifa").one().upstream_family = "fifa-digital"
        db.commit()
        competition = db.query(SportsCompetition).filter_by(competition_id="pass4-afcon").one()
        result = classify_competition(db, competition, "snapshot")
        assert result["classification"] == "WORKING_FALLBACK"
        assert result["events"] == 1
        assert result["capability_status"] == "VERIFIED_OPERATIONAL"
        assert result["window_status"] == "HAS_EVENTS"
        assert "fifa-digital" in result["verified_families"]
    finally:
        db.close()
        _cleanup_adapters("limited", "fifa")


def test_healthy_empty_is_verified_operational_without_events():
    class EmptyOk:
        adapter_key = "emptyok"

        def __init__(self, source_id="emptyok"):
            self.source_id = source_id

        def fetch(self, request):
            return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")

    register_adapter("emptyok", EmptyOk)
    db = _session()
    try:
        source = _source(db, "pass4-emptyok", "emptyok")
        source.upstream_family = "thesportsdb"
        _competition(db, "pass4-offseason", "football")
        _map(db, "pass4-offseason", "pass4-emptyok", 1)
        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="pass4-emptyok").one().upstream_family = "thesportsdb"
        db.commit()
        competition = db.query(SportsCompetition).filter_by(competition_id="pass4-offseason").one()
        result = classify_competition(db, competition, "snapshot")
        assert result["classification"] == "NO_CURRENT_EVENTS"
        assert result["capability_status"] == "PARTIAL_OPERATIONAL"
        assert result["window_status"] == "NO_EVENTS"
    finally:
        db.close()
        _cleanup_adapters("emptyok")
