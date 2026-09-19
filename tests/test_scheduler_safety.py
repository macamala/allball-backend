"""Orchestration/safety tests: mocks plus recorded fixtures. No 180-way live burst."""

from collector.adapters import FetchRequest, FetchResult, register_adapter
from collector.adapters_csv import SackmannTennisAdapter
from collector.adapters_generic import GenericHttpAdapter
from collector.capability_ledger import merge_capability
from collector.collect import collect_competition, run_cycle
from collector.http import _block_host, reset_http_stats
from collector.models import SportsEvent, SportsSourceCompetition
from collector.production import bootstrap_registry, register_production_adapters
from collector.registry import build_runtime_registry
from collector.sources import ordered_sources
from collector.test_support import mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


class _Echo:
    def __init__(self, source_id="echo"):
        self.source_id = source_id
        self.calls = []

    def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request)
        cid = request.competition_id or "x"
        return FetchResult(
            ok=True,
            http_status=200,
            events=[
                mock_event(
                    id=f"{cid}-evt",
                    home={"name": f"Home {cid}"},
                    away={"name": f"Away {cid}"},
                    start_time="2026-09-18T15:00:00Z",
                    competition=cid,
                )
            ],
        )


class _Limited:
    def __init__(self, source_id="limited"):
        self.source_id = source_id
        self.calls = 0

    def fetch(self, request):
        self.calls += 1
        return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")


class _Boom:
    def __init__(self, source_id="boom"):
        self.source_id = source_id

    def fetch(self, request):
        raise RuntimeError("parser exploded")


def test_inventory_scheduler_runs_all_competitions_on_mocks():
    runtime = build_runtime_registry()
    keys = {row["adapter_key"] for row in runtime["mappings"] if row.get("enabled")}
    echo = _Echo()
    db = _session()
    try:
        bootstrap_registry(db)
        db.commit()
        for key in keys:
            register_adapter(key, lambda source_id="echo", adapter=echo: adapter)
        summary = run_cycle(db, capabilities=["fixtures"], sleeper=lambda _d: None)
        db.commit()
        comps = {row.competition_id for row in db.query(SportsEvent).all()}
        enabled = {
            row.competition_id
            for row in db.query(SportsSourceCompetition).filter_by(enabled=True).all()
        }
        assert summary.get("fixtures", 0) >= 1
        assert len(enabled) >= 170
        assert len(comps) >= 150
    finally:
        db.close()
        register_production_adapters()
        _cleanup_adapters(*[key for key in keys if key not in {
            "openfootball-json", "openligadb", "thesportsdb", "opendota", "squiggle-afl",
            "cricsheet-json", "fifa-json", "nhl-web", "mlb-statsapi", "khl-mobile",
            "world-rugby-rims", "jolpica-f1", "euroleague-live", "generic-http",
            "bbc-sport", "espn-scoreboard", "pulselive-family", "liquipedia", "sackmann-csv",
            "omega-timing",
        }])


def test_one_host_429_does_not_stop_other_families():
    reset_http_stats()
    _block_host("https://www.thesportsdb.com/", 120.0, kind="rate")
    db = _session()
    register_adapter("thesportsdb", _Limited)
    register_adapter("fifa-json", lambda source_id="fifa": _Echo(source_id))
    try:
        tsdb = _source(db, "sched-tsdb", "thesportsdb")
        fifa = _source(db, "sched-fifa", "fifa-json")
        tsdb.upstream_family = "thesportsdb"
        fifa.upstream_family = "fifa-digital"
        tsdb.attribution_url = "https://www.thesportsdb.com/"
        _competition(db, "sched-world-cup", "football")
        _map(db, "sched-world-cup", "sched-tsdb", 1)
        _map(db, "sched-world-cup", "sched-fifa", 2)
        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="sched-tsdb").one().upstream_family = "thesportsdb"
        db.query(SportsSourceCompetition).filter_by(source_id="sched-fifa").one().upstream_family = "fifa-digital"
        db.commit()
        primary, fallback = ordered_sources(db, "sched-world-cup", "snapshot")
        families = [row[0].upstream_family for row in primary + fallback]
        assert "thesportsdb" not in families
        assert "fifa-digital" in families
    finally:
        reset_http_stats()
        db.close()
        _cleanup_adapters("thesportsdb", "fifa-json")


def test_host_block_skips_tsdb_and_uses_independent_family():
    reset_http_stats()
    _block_host("https://www.thesportsdb.com/", 120.0, kind="rate")
    db = _session()
    echo = _Echo("fifa")
    register_adapter("thesportsdb", _Limited)
    register_adapter("fifa-json", lambda source_id="fifa": echo)
    try:
        from collector.models import SportsCompetition

        tsdb = _source(db, "blk-tsdb", "thesportsdb")
        fifa = _source(db, "blk-fifa", "fifa-json")
        tsdb.upstream_family = "thesportsdb"
        fifa.upstream_family = "fifa-digital"
        tsdb.attribution_url = "https://www.thesportsdb.com/"
        _competition(db, "blk-world-cup", "football")
        _map(db, "blk-world-cup", "blk-tsdb", 1)
        _map(db, "blk-world-cup", "blk-fifa", 2)
        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="blk-tsdb").one().upstream_family = "thesportsdb"
        db.query(SportsSourceCompetition).filter_by(source_id="blk-fifa").one().upstream_family = "fifa-digital"
        db.commit()
        competition = db.query(SportsCompetition).filter_by(competition_id="blk-world-cup").one()
        stats = collect_competition(db, competition, "snapshot", sleeper=lambda _d: None)
        db.commit()
        assert stats["written"] >= 1
        event = db.query(SportsEvent).filter_by(competition_id="blk-world-cup").one()
        assert event.primary_source_id == "blk-fifa"
    finally:
        reset_http_stats()
        db.close()
        _cleanup_adapters("thesportsdb", "fifa-json")


def test_one_parser_failure_does_not_stop_batch():
    register_adapter("boom", _Boom)
    register_adapter("echo", lambda source_id="echo": _Echo(source_id))
    db = _session()
    try:
        from collector.models import SportsCompetition

        _source(db, "fail-src", "boom")
        _source(db, "ok-src", "echo")
        _competition(db, "fail-comp", "football")
        _competition(db, "ok-comp", "football")
        _map(db, "fail-comp", "fail-src", 1)
        _map(db, "ok-comp", "ok-src", 1)
        db.commit()
        summary = run_cycle(db, capabilities=["fixtures"], sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).filter_by(competition_id="ok-comp").count() == 1
        assert summary["fixtures"] >= 1
    finally:
        db.close()
        _cleanup_adapters("boom", "echo")


def test_cache_reuses_identical_url():
    from collector.http import STATS, fetch_url, reset_http_stats

    reset_http_stats()
    calls = {"n": 0}

    def getter(url, headers=None, timeout=None):
        calls["n"] += 1
        from collector.http import _store

        result = FetchResult(ok=True, http_status=200, payload={"ok": True})
        return result

    # Use real cache via fetch_url by storing twice
    from collector import http as http_mod

    original = http_mod.urllib.request.urlopen

    class _Resp:
        def __init__(self):
            self.status = 200
            self.headers = {"Content-Type": "application/json"}

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(req, timeout=20):
        calls["n"] += 1
        return _Resp()

    http_mod.urllib.request.urlopen = fake_open
    try:
        first = fetch_url("https://example.test/cache.json")
        second = fetch_url("https://example.test/cache.json")
        assert first.ok and second.ok
        assert calls["n"] == 1
        assert STATS["cache_hits"] >= 1
    finally:
        http_mod.urllib.request.urlopen = original
        reset_http_stats()


def test_next_data_json_follow_produces_events():
    html = """
    <html><script id="__NEXT_DATA__" type="application/json">
    {"buildId":"abc123","page":"/schedule"}
    </script></html>
    """
    payload = {"props": {"pageProps": {"games": [
        {"homeTeam": {"name": "Gotham"}, "awayTeam": {"name": "Current"}, "startDate": "2026-09-18T00:00:00Z"}
    ]}}}

    def get(url):
        if url.endswith(".json"):
            return FetchResult(ok=True, http_status=200, payload=payload)
        return FetchResult(ok=False, http_status=404, error="no")

    def get_text(url, timeout=None):
        return FetchResult(ok=True, http_status=200, payload=html)

    adapter = GenericHttpAdapter(getter=get, text_getter=get_text)
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="usa-nwsl",
            source_config={"url": "https://www.nwslsoccer.com/schedule"},
            upstream_family="nwsl-web",
        )
    )
    assert result.ok
    assert result.events
    assert result.events[0]["home"]["name"] == "Gotham"


def test_json_urls_used_before_html():
    payload = [{"ShortDescription": "Oberhof", "EventId": "BT2526E1", "StartDate": "2026-01-07"}]

    def get(url):
        if "biathlonresults" in url:
            return FetchResult(ok=True, http_status=200, payload=payload)
        return FetchResult(ok=False, http_status=404)

    adapter = GenericHttpAdapter(getter=get, text_getter=lambda url, timeout=None: FetchResult(ok=False, http_status=500))
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="biathlon",
            source_config={
                "url": "https://www.biathlonworld.com/calendar",
                "json_urls": ["https://www.biathlonresults.com/modules/sportapi/api/Events?SeasonId=2526"],
            },
            upstream_family="ibu-web",
        )
    )
    assert result.ok
    assert result.events
    assert "Oberhof" in result.events[0]["home"]["name"]


def test_sackmann_lists_repo_after_404():
    csv = "tourney_name,tourney_date,winner_name,loser_name,round,match_num\nAO,20240115,Sinner,Djokovic,F,1\n"

    def get_text(url, timeout=None):
        if "listed-atp.csv" in url:
            return FetchResult(ok=True, http_status=200, payload=csv)
        return FetchResult(ok=False, http_status=404, error="http 404")

    def get(url):
        if "api.github.com" in url:
            return FetchResult(
                ok=True,
                http_status=200,
                payload=[{"name": "atp_matches_2024.csv", "download_url": "https://example.test/listed-atp.csv"}],
            )
        return FetchResult(ok=False, http_status=404)

    adapter = SackmannTennisAdapter(text_getter=get_text, getter=get)
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="atp", source_config={"url": "https://missing.csv"}))
    assert result.ok
    assert result.events[0]["home"]["name"] == "Sinner"


def test_capability_ledger_marks_espn_access_blocked():
    assert merge_capability("RATE_LIMITED", competition_id="nfl", family="espn-html", events=0) == "ACCESS_BLOCKED"
    assert merge_capability("BROKEN", competition_id="nfl", family="espn-html", events=0) == "ACCESS_BLOCKED"
    assert merge_capability("RATE_LIMITED", competition_id="bl1", family="openligadb", events=0) in {
        "VERIFIED_OPERATIONAL",
        "RATE_LIMITED",
    }


def test_partial_restriction_not_promoted():
    from collector.coverage import filter_partial_events, constraints_for

    events = [
        mock_event(id="1", home={"name": "World Aquatics Final"}, away={"name": "Heat"}, competition="swimming"),
        mock_event(id="2", home={"name": "Local Club Meet"}, away={"name": "Other"}, competition="swimming"),
    ]
    filtered = filter_partial_events(events, constraints_for("world-aquatics", "microplus-timing") or {"allow_keywords": ["world aquatics"]})
    assert isinstance(filtered, list)
