"""Pass 5: official family adapters, ESPN scoreboard, TSDB 429 failover, pacing."""

from collector.adapters import FetchRequest, FetchResult, register_adapter
from collector.adapters_espn import EspnScoreboardAdapter, parse_espn_scoreboard
from collector.adapters_cricsheet import CricsheetAdapter
from collector.family_catalog import infer_url
from collector.http import STATS, _pace_host, reset_http_stats
from collector.models import SportsCompetition, SportsSourceCompetition
from collector.smoke import classify_competition
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


ESPN_PAYLOAD = {
    "leagues": [{"name": "NFL"}],
    "events": [
        {
            "id": "401",
            "date": "2026-09-18T00:20:00Z",
            "name": "Chiefs at Ravens",
            "competitions": [
                {
                    "id": "401-1",
                    "competitors": [
                        {"homeAway": "home", "score": "24", "team": {"displayName": "Baltimore Ravens"}},
                        {"homeAway": "away", "score": "21", "team": {"displayName": "Kansas City Chiefs"}},
                    ],
                    "status": {"type": {"state": "post"}},
                }
            ],
        }
    ],
}


def test_espn_scoreboard_parser():
    events = parse_espn_scoreboard(ESPN_PAYLOAD)
    assert events
    assert events[0]["home"]["name"] == "Baltimore Ravens"
    assert events[0]["away"]["name"] == "Kansas City Chiefs"
    assert events[0]["status"] == "finished"
    assert events[0]["score"]["home"] == 24


def test_espn_adapter_uses_public_json():
    adapter = EspnScoreboardAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=ESPN_PAYLOAD))
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="nfl"))
    assert result.ok
    assert result.events[0]["home"]["name"] == "Baltimore Ravens"


def test_tsdb_429_does_not_zero_nfl_when_espn_works():
    class Limited:
        adapter_key = "thesportsdb"

        def __init__(self, source_id="thesportsdb"):
            self.source_id = source_id

        def fetch(self, request):
            return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")

    espn = EspnScoreboardAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=ESPN_PAYLOAD))
    register_adapter("thesportsdb", Limited)
    register_adapter("espn-scoreboard", lambda source_id="espn": espn)
    db = _session()
    try:
        tsdb = _source(db, "pass5-tsdb", "thesportsdb")
        html = _source(db, "pass5-espn", "espn-scoreboard")
        tsdb.upstream_family = "thesportsdb"
        html.upstream_family = "espn-html"
        _competition(db, "pass5-nfl", "american-football")
        _map(db, "pass5-nfl", "pass5-tsdb", 1)
        _map(db, "pass5-nfl", "pass5-espn", 2)
        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="pass5-tsdb").one().upstream_family = "thesportsdb"
        db.query(SportsSourceCompetition).filter_by(source_id="pass5-espn").one().upstream_family = "espn-html"
        db.commit()
        competition = db.query(SportsCompetition).filter_by(competition_id="pass5-nfl").one()
        result = classify_competition(db, competition, "snapshot")
        assert result["classification"] == "WORKING_FALLBACK"
        assert result["capability_status"] == "VERIFIED_OPERATIONAL"
        assert "espn-html" in result["verified_families"]
    finally:
        db.close()
        _cleanup_adapters("thesportsdb", "espn-scoreboard")


def test_handball_and_basketball_official_failover():
    class Limited:
        adapter_key = "thesportsdb"

        def __init__(self, source_id="thesportsdb"):
            self.source_id = source_id

        def fetch(self, request):
            return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")

    hbl = DeterministicMockAdapter("hbl")
    hbl.events = [mock_event(id="h1", home={"name": "Kiel"}, away={"name": "Flensburg"}, competition="HBL")]
    acb = DeterministicMockAdapter("acb")
    acb.events = [mock_event(id="a1", home={"name": "Real Madrid"}, away={"name": "Barca"}, competition="ACB")]
    register_adapter("thesportsdb", Limited)
    register_adapter("hbl", lambda source_id="hbl": hbl)
    register_adapter("acb", lambda source_id="acb": acb)
    db = _session()
    try:
        for comp_id, sport, src, key, family in (
            ("pass5-hbl-league", "handball", "pass5-hbl", "hbl", "hbl-web"),
            ("pass5-acb-league", "basketball", "pass5-acb", "acb", "acb-web"),
        ):
            tsdb = _source(db, f"tsdb-{comp_id}", "thesportsdb")
            official = _source(db, src, key)
            tsdb.upstream_family = "thesportsdb"
            official.upstream_family = family
            _competition(db, comp_id, sport)
            _map(db, comp_id, f"tsdb-{comp_id}", 1)
            _map(db, comp_id, src, 2)
        db.flush()
        for source_id, family in (("tsdb-pass5-hbl-league", "thesportsdb"), ("pass5-hbl", "hbl-web"), ("tsdb-pass5-acb-league", "thesportsdb"), ("pass5-acb", "acb-web")):
            db.query(SportsSourceCompetition).filter_by(source_id=source_id).one().upstream_family = family
        db.commit()
        handball = classify_competition(db, db.query(SportsCompetition).filter_by(competition_id="pass5-hbl-league").one(), "snapshot")
        basketball = classify_competition(db, db.query(SportsCompetition).filter_by(competition_id="pass5-acb-league").one(), "snapshot")
        assert handball["capability_status"] == "VERIFIED_OPERATIONAL"
        assert basketball["capability_status"] == "VERIFIED_OPERATIONAL"
        assert "hbl-web" in handball["verified_families"]
        assert "acb-web" in basketball["verified_families"]
    finally:
        db.close()
        _cleanup_adapters("thesportsdb", "hbl", "acb")


def test_infer_url_uses_schedule_and_sporting_life_paths():
    nwsl = infer_url("nwsl-web", "nwslsoccer.com schedule", "fetch 200", "football")
    assert nwsl.endswith("/schedule")
    grey = infer_url("sporting-life", "Sporting Life greyhound results", "fetch 200 meeting cards", "greyhound-racing")
    assert "greyhounds" in grey


def test_cricsheet_filters_t20():
    adapter = CricsheetAdapter(
        getter=lambda url: FetchResult(
            ok=True,
            http_status=200,
            payload=[
                {"info": {"teams": ["A", "B"], "match_type": "T20", "dates": ["2026-09-01"], "outcome": {"winner": "A"}}, "innings": []},
                {"info": {"teams": ["C", "D"], "match_type": "Test", "dates": ["2026-09-02"], "outcome": {"winner": "C"}}, "innings": []},
            ],
        )
    )
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="t20-internationals"))
    assert len(result.events) == 1
    assert result.events[0]["home"]["name"] == "A"


def test_thesportsdb_host_is_paced():
    reset_http_stats()
    _pace_host("https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=1")
    _pace_host("https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=2")
    assert STATS.get("paced", 0) >= 1
