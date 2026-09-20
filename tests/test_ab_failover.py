"""Primary/fallback behaviour for every two-family mapped competition.

Uses in-process mocks. Does not hammer live providers.
"""

from collector.adapters import FetchResult, register_adapter
from collector.collect import collect_competition
from collector.models import SportsEvent, SportsSourceCompetition
from collector.registry import build_runtime_registry
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def _two_provider_rows():
    from collector.family_caps import family_caps

    runtime = build_runtime_registry()
    rows = []
    for competition_id, record in sorted(runtime["competitions"].items()):
        families = []
        seen = set()
        for mapping in record.get("sources") or []:
            if not mapping.get("enabled"):
                continue
            family = mapping.get("source_family")
            if not family or family in seen:
                continue
            if family_caps(family).get("production_status") == "ACCESS_BLOCKED":
                continue
            if (mapping.get("coverage") or "full") == "partial":
                continue
            seen.add(family)
            families.append(family)
        if len(families) >= 2:
            rows.append((competition_id, record.get("sport") or "football", families[0], families[1]))
    return rows


class _Fail:
    def __init__(self, source_id="fail", http_status=500, error="failed", classification="OTHER_ERROR", timeout=False, rate=False):
        self.source_id = source_id
        self.adapter_key = source_id
        self.http_status = http_status
        self.error = error
        self.classification = classification
        self.timeout = timeout
        self.rate = rate
        self.calls = 0

    def fetch(self, request):
        self.calls += 1
        if self.rate:
            return FetchResult(ok=False, http_status=429, error="http 429", classification="RATE_LIMITED")
        if self.timeout:
            return FetchResult(ok=False, http_status=0, error="timed out", classification="NETWORK_FAILURE")
        return FetchResult(
            ok=False,
            http_status=200,
            error="parser failed",
            parse_status="failed",
            classification="PARSE_FAILURE",
        )


def _bind(db, competition_id, sport, family_a, family_b, adapter_a, adapter_b):
    src_a = f"a-{competition_id}"
    src_b = f"b-{competition_id}"
    a = _source(db, src_a, adapter_a)
    b = _source(db, src_b, adapter_b)
    a.upstream_family = family_a
    b.upstream_family = family_b
    _competition(db, competition_id, sport)
    _map(db, competition_id, src_a, 1)
    _map(db, competition_id, src_b, 2)
    db.flush()
    db.query(SportsSourceCompetition).filter_by(source_id=src_a).one().upstream_family = family_a
    db.query(SportsSourceCompetition).filter_by(source_id=src_b).one().upstream_family = family_b
    db.commit()
    return db.query(type(a)).filter_by(source_id=src_a).one() and db.query(
        __import__("collector.models", fromlist=["SportsCompetition"]).SportsCompetition
    ).filter_by(competition_id=competition_id).one()


def _competition_row(db, competition_id):
    from collector.models import SportsCompetition

    return db.query(SportsCompetition).filter_by(competition_id=competition_id).one()


def test_every_two_provider_config_failsover_and_dedupes():
    rows = _two_provider_rows()
    assert len(rows) >= 150
    db = _session()
    created = []
    try:
        from collector.family_health import reset_family_health
        from collector.http import reset_http_stats

        for index, (competition_id, sport, family_a, family_b) in enumerate(rows):
            reset_family_health()
            reset_http_stats()
            cid = f"ab-{index}-{competition_id}"[:80]
            key_a = f"mock-a-{index}"
            key_b = f"mock-b-{index}"
            good_a = DeterministicMockAdapter(key_a)
            good_a.events = [
                mock_event(
                    id=f"{cid}-evt",
                    home={"name": f"Alpha {cid}"},
                    away={"name": f"Beta {cid}"},
                    start_time="2026-09-18T15:00:00Z",
                    competition=cid,
                    source_competition_id=cid,
                )
            ]
            good_b = DeterministicMockAdapter(key_b)
            good_b.events = [
                mock_event(
                    id=f"{cid}-evt-b",
                    home={"name": f"Alpha {cid}"},
                    away={"name": f"Beta {cid}"},
                    start_time="2026-09-18T15:00:00Z",
                    competition=cid,
                    source_competition_id=cid,
                )
            ]
            fail = _Fail(key_a)
            limited = _Fail(key_a, rate=True)
            timeout = _Fail(key_a, timeout=True)

            # TEST 1: A works -> A used, B not called
            register_adapter(key_a, lambda source_id=key_a, adapter=good_a: adapter)
            register_adapter(key_b, lambda source_id=key_b, adapter=good_b: adapter)
            _source(db, f"{cid}-a", key_a).upstream_family = family_a
            _source(db, f"{cid}-b", key_b).upstream_family = family_b
            _competition(db, cid, sport)
            _map(db, cid, f"{cid}-a", 1)
            _map(db, cid, f"{cid}-b", 2)
            created.extend([key_a, key_b])
            db.flush()
            db.query(SportsSourceCompetition).filter_by(source_id=f"{cid}-a").one().upstream_family = family_a
            db.query(SportsSourceCompetition).filter_by(source_id=f"{cid}-b").one().upstream_family = family_b
            db.commit()
            before_b = len(good_b.calls)
            result = collect_competition(db, _competition_row(db, cid), "snapshot", sleeper=lambda _d: None)
            db.commit()
            assert result["written"] >= 1
            assert db.query(SportsEvent).filter_by(competition_id=cid).count() == 1
            event = db.query(SportsEvent).filter_by(competition_id=cid).one()
            assert event.primary_source_id == f"{cid}-a"

            for label, failing in (("fail", fail), ("429", limited), ("timeout", timeout)):
                sub = f"{cid}-{label}"[:80]
                sub_key_a = f"{key_a}-{label}"
                register_adapter(sub_key_a, lambda source_id=sub_key_a, adapter=failing: adapter)
                register_adapter(key_b, lambda source_id=key_b, adapter=good_b: adapter)
                _source(db, f"{sub}-a", sub_key_a).upstream_family = family_a
                _source(db, f"{sub}-b", key_b).upstream_family = family_b
                # Fallback adapter must emit the same match for this competition, not TEST 1's names.
                good_b.events = [
                    mock_event(
                        id=f"{sub}-evt-b",
                        home={"name": f"Alpha {sub}"},
                        away={"name": f"Beta {sub}"},
                        start_time="2026-09-18T16:00:00Z",
                        competition=sub,
                        source_competition_id=sub,
                    )
                ]
                _competition(db, sub, sport)
                _map(db, sub, f"{sub}-a", 1)
                _map(db, sub, f"{sub}-b", 2)
                created.append(sub_key_a)
                db.flush()
                db.query(SportsSourceCompetition).filter_by(source_id=f"{sub}-a").one().upstream_family = family_a
                db.query(SportsSourceCompetition).filter_by(source_id=f"{sub}-b").one().upstream_family = family_b
                db.commit()
                before = len(good_b.calls)
                collect_competition(db, _competition_row(db, sub), "snapshot", sleeper=lambda _d: None)
                db.commit()
                assert db.query(SportsEvent).filter_by(competition_id=sub).count() == 1
                assert len(good_b.calls) >= before + 1
                if label in {"429", "timeout"}:
                    assert failing.calls == 1
    finally:
        db.close()
        _cleanup_adapters(*set(created))
