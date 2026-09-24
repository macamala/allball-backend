"""Regression tests for production live-score recovery (no upstream/network I/O)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from collector.family_health import reset_family_health
from collector.models import SportsCompetition, SportsEvent, SportsSchedulerSlot, SportsSource, SportsSourceCompetition
from collector.util import dump_json, load_json
from collector.urgency import job_dict
from database import SessionLocal
import collector.incremental as inc


@pytest.fixture(autouse=True)
def recovery_state(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "true")
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "true")
    reset_family_health()
    inc._live_registry.clear()
    yield
    reset_family_health()
    inc._live_registry.clear()


def _setup(db, count=2, status="live"):
    now = datetime.utcnow()
    source = SportsSource(source_id="recovery-fotmob", display_name="recovery", enabled=True,
                          adapter_key="fotmob", upstream_family="fotmob", kind="test")
    db.add(source)
    jobs = []
    for index in range(count):
        cid = f"recovery-comp-{index}"
        db.add(SportsCompetition(competition_id=cid, sport_id="football", name=cid, slug=cid,
                                active=True, event_model="team_match", identity_only=False))
        db.add(SportsSourceCompetition(competition_id=cid, source_id=source.source_id,
                                      enabled=True, upstream_family="fotmob", priority=1))
        db.add(SportsEvent(event_id=f"recovery-{index}", competition_id=cid, sport_id="football",
                           canonical_event_id=None, display_eligible=True, status=status, event_family="team_match",
                           start_time=now-timedelta(minutes=10), score_json=dump_json({"home":0,"away":0}),
                           extra_json=dump_json({"start_precision":"EXACT_TIME", "source_family":"fotmob",
                                                 "source_status":status,"source_fetch_time":now.isoformat()+"Z"})))
        jobs.append(job_dict(competition_id=cid, family="fotmob", urgency="LIVE", reason="test",
                             source_id=source.source_id, request_key="shared-board", job_key=f"refresh:{cid}:fotmob:live_scores",
                             interval=60, sport="football"))
    db.commit()
    return jobs


def test_every_competition_consumes_shared_live_board(monkeypatch):
    db = SessionLocal()
    try:
        jobs = _setup(db)
        seen = []
        monkeypatch.setattr(inc, "build_due_jobs", lambda *_a, **_kw: jobs)
        def collect(_db, competition, capability, **kwargs):
            index = int(competition.competition_id.rsplit("-",1)[1])
            seen.append(competition.competition_id)
            _db.get(SportsEvent, f"recovery-{index}").score_json = dump_json({"home": index+1, "away":0})
            return {"classification":"WORKING_PRIMARY","written":1}
        monkeypatch.setattr("collector.collect.collect_competition", collect)
        monkeypatch.setattr("collector.canonical_collapse.collapse_canonical_events", lambda *_a, **_k: pytest.fail("Global collapse on live path"))
        monkeypatch.setattr("collector.canonical_collapse.promote_observation_enrichment", lambda *_a, **_k: pytest.fail("Global enrichment on live path"))
        out = inc.run_incremental_tick(db, liveish_only=True)
        db.commit()
        assert len(seen) == 2
        assert out["jobs_processed"] == 2
        assert load_json(db.get(SportsEvent,"recovery-0").score_json)["home"] == 1
        assert load_json(db.get(SportsEvent,"recovery-1").score_json)["home"] == 2
        assert db.query(SportsEvent).count() == 2
    finally:
        db.close()


def test_budget_does_not_advance_unexecuted_job(monkeypatch):
    db = SessionLocal()
    try:
        jobs = _setup(db)
        monkeypatch.setattr(inc, "build_due_jobs", lambda *_a, **_kw: jobs)
        monkeypatch.setattr(inc, "TICK_LIVE_BUDGET_S", 0)
        monkeypatch.setattr("collector.collect.collect_competition", lambda *_a, **_k: {"classification":"WORKING_PRIMARY","written":0})
        out = inc.run_incremental_tick(db, liveish_only=True)
        db.commit()
        assert out["jobs_processed"] == 1
        assert db.get(SportsSchedulerSlot,jobs[0]["job_key"]) is not None
        assert db.get(SportsSchedulerSlot,jobs[1]["job_key"]) is None
    finally:
        db.close()


def test_finished_event_never_becomes_kickoff_candidate():
    db = SessionLocal()
    try:
        _setup(db,1,status="finished")
        jobs = inc.build_due_jobs(db, live_only=True, sport_id="football", source_family="fotmob")
        assert jobs
        assert {job["urgency"] for job in jobs} == {"RECENTLY_FINISHED"}
    finally:
        db.close()


def test_fotmob_batch_reuses_one_board_after_normal_ttl(monkeypatch):
    import collector.adapters_fotmob as fm
    fm._BOARD.clear(); fm._BOARD_AT.clear()
    clock = [100.0]
    calls = []
    monkeypatch.setattr(fm.time,"monotonic",lambda:clock[0])
    def getter(url):
        calls.append(url)
        return SimpleNamespace(ok=True,payload={"leagues":[{"id":47,"name":"Premier League", "matches":[
            {"id":1,"home":{"name":"Alpha","id":1},"away":{"name":"Beta","id":2},"status":{"started":True}}
        ]}]})
    with fm.shared_board_batch():
        a=fm._load_boards(getter,dates=["20260924"],ttl_seconds=5)
        clock[0]+=20
        b=fm._load_boards(getter,dates=["20260924"],ttl_seconds=5)
    assert a is b
    assert len(calls)==1
    fm._load_boards(getter,dates=["20260924"],ttl_seconds=5)
    assert len(calls)==2


def test_tick_failure_releases_owned_write_lease(monkeypatch):
    from collector.lock import acquire_write_lock, owner_identity
    db=SessionLocal()
    try:
        assert acquire_write_lock(db,owner=owner_identity())
        db.commit()
        def fail(*args,**kwargs): raise RuntimeError("simulated due-build failure")
        monkeypatch.setattr(inc,"build_due_jobs",fail)
        with pytest.raises(RuntimeError,match="simulated due-build"):
            inc.run_incremental_tick(db,liveish_only=True)
        db.commit()
        assert acquire_write_lock(db,owner="next-worker")
        db.rollback()
    finally: db.close()


def test_priority_cycle_defers_bulk_but_keeps_discovery(monkeypatch):
    import collector.priority_cycle as pc
    from collector.lock import acquire_scheduler_lock
    db=SessionLocal()
    try:
        _setup(db,1)
        assert acquire_scheduler_lock(db,owner="cycle-test")
        db.commit()
        calls=[]
        def tick(_db,**kwargs):
            calls.append(kwargs)
            return {"jobs_processed":1,"events_changed":1}
        monkeypatch.setattr(pc,"run_incremental_tick",tick)
        monkeypatch.setattr(pc,"_last_discovery",-1e10)
        assert pc.run_priority_cycle(db,owner="cycle-test") is True
        assert len(calls)==3
        assert all(call["run_maintenance"] is False for call in calls)
        assert calls[-1]["discovery_only"] is True
        assert calls[-1]["max_physical"]==1
        assert pc.run_priority_cycle(db,owner="cycle-test") is True
        assert len(calls)==5  # discovery is rate limited, not repeated every tick
    finally: db.close()


def test_priority_window_excludes_future_finished_and_hidden():
    from collector.priority_cycle import has_priority_events
    db=SessionLocal()
    try:
        _setup(db,1,status="finished")
        row=db.get(SportsEvent,"recovery-0")
        assert not has_priority_events(db)
        row.status="scheduled"; row.start_time=datetime.utcnow()+timedelta(days=2)
        db.commit(); assert not has_priority_events(db)
        row.start_time=datetime.utcnow(); row.display_eligible=False
        db.commit(); assert not has_priority_events(db)
        row.display_eligible=True
        db.commit(); assert has_priority_events(db)
    finally: db.close()


def test_fotmob_group_ids_resolve_through_exact_parent_competition(monkeypatch):
    import json
    from pathlib import Path
    from collector.adapters import FetchRequest, FetchResult
    import collector.adapters_fotmob as fm
    payload=json.loads((Path(__file__).parent / "fixtures/fotmob_nations_groups_20260924.json").read_text())
    fm._BOARD.clear(); fm._BOARD_AT.clear()
    monkeypatch.setattr(fm,"board_dates",lambda **kwargs:["20260924"])
    adapter=fm.FotMobAdapter(getter=lambda url:FetchResult(ok=True,http_status=200,payload=payload))
    result=adapter.fetch(FetchRequest(capability="live_scores",sport_id="football",competition_id="uefa-nations-league"))
    assert len(result.events)==5
    by_id={row["id"]:row for row in result.events}
    netherlands=by_id["5181825"]
    assert netherlands["status"]=="finished"
    assert netherlands["score"]=={"home":1,"away":1}
    assert netherlands["source_competition_id"]=="9806"
    assert netherlands["source_group_id"]=="920744"
    assert netherlands["group"].endswith("A Grp. 2")
    assert by_id["5181861"]["group"].endswith("A Grp. 4")
    assert netherlands["competition_logo"].endswith("/9806.png")
    assert by_id["5181880"]["score"]["home"]==0
    assert fm._matching_league_id({"id":920744,"primaryId":9806},{"9807"})==""
    assert fm._matching_league_id({"id":920744,"primaryId":9806},{"920744"})=="920744"
    from collector.competition_identity import event_accepted_for_mapping
    accepted,_=event_accepted_for_mapping(netherlands,"uefa-nations-league")
    assert accepted


def test_overdue_football_recovers_results_without_inventing_live():
    db=SessionLocal()
    try:
        _setup(db,1,status="scheduled")
        row=db.get(SportsEvent,"recovery-0")
        row.start_time=datetime.utcnow()-timedelta(hours=20)
        db.commit()
        jobs=inc.build_due_jobs(db,live_only=True,sport_id="football",source_family="fotmob")
        assert len(jobs)==1
        assert jobs[0]["urgency"]=="RESULT_CATCHUP"
        assert jobs[0]["capability"]=="results"
        assert row.status=="scheduled"
        assert inc.filter_due_jobs(jobs,live_only=True)==jobs
    finally: db.close()


def test_result_updates_existing_canonical_id_without_losing_assets():
    import copy, json
    from pathlib import Path
    from collector.adapters import FetchResult
    from collector.adapters_fotmob import _extract_matches, match_to_event
    from collector.collect import _consume_result
    from tests.test_collector_architecture import _source, _competition, _map
    payload=json.loads((Path(__file__).parent/"fixtures/fotmob_nations_groups_20260924.json").read_text())
    finished=match_to_event(_extract_matches(payload)[0],"uefa-nations-league",source_league_id="9806")
    scheduled=copy.deepcopy(finished)
    scheduled["status"]="scheduled"; scheduled["score"]={"home":None,"away":None}
    scheduled["extra"]["source_status"]="scheduled"
    db=SessionLocal()
    try:
        source=_source(db,"recovery-nations","fotmob")
        source.upstream_family="fotmob"
        comp=_competition(db,"uefa-nations-league","football")
        mapping=_map(db,comp.competition_id,source.source_id,source_competition_id="9806",upstream_family="fotmob")
        db.commit()
        _consume_result(db,source=source,mapping=mapping,competition=comp,capability="fixtures",result=FetchResult(ok=True,http_status=200,events=[scheduled]))
        db.commit()
        row=db.query(SportsEvent).one()
        original=row.event_id
        participants=load_json(row.participants_json)
        participants["home"]["country_id"]="nl"
        row.participants_json=dump_json(participants); db.commit()
        _consume_result(db,source=source,mapping=mapping,competition=comp,capability="results",result=FetchResult(ok=True,http_status=200,events=[finished]))
        db.commit(); db.refresh(row)
        assert db.query(SportsEvent).count()==1
        assert row.event_id==original
        assert row.status=="finished"
        assert load_json(row.score_json)["home"]==1
        assert load_json(row.participants_json)["home"]["country_id"]=="nl"
        assert load_json(row.participants_json)["home"]["logo"]
        extra=load_json(row.extra_json)
        assert extra["group"].endswith("A Grp. 2")
        assert extra["source_group_id"]=="920744"
        assert row.display_eligible is True
    finally: db.close()


def test_group_crosswalk_keeps_known_parent_without_new_competition():
    from collector.fotmob_crosswalk import _fotmob_competition_identity
    cid,lid,name,country=_fotmob_competition_identity({"_league":{
        "id":920744,"primaryId":9806,"name":"UEFA Nations League A Grp. 2","ccode":"INT"}})
    assert cid=="uefa-nations-league"
    assert lid=="920744"


def test_artwork_first_fetch_not_blocked_by_fresh_host_uptime(monkeypatch):
    import collector.fotmob_asset_backfill as assets
    db=SessionLocal()
    try:
        _setup(db,1,status="scheduled")
        row=db.get(SportsEvent,"recovery-0")
        row.participants_json=dump_json({"home":{"name":"Alpha"},"away":{"name":"Beta"}})
        row.extra_json=dump_json({"source_family":"fotmob","source_competition_id":"47"})
        db.commit()
        monkeypatch.setattr(assets,"_last_league_fetch",{})
        assert dict(assets._candidate_competitions(db,10))[row.competition_id]==["47"]
        assets._last_league_fetch[row.competition_id]=10
        assert row.competition_id not in dict(assets._candidate_competitions(db,11))
    finally: db.close()
