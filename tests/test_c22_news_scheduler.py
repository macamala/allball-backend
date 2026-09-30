"""Mocked I/O regression tests. No real News, credentials, DB or AI requests."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
import pytest
from bot.news_budget import AiRequestBudget, reserve_ai_request
from tests.test_c22_news_runtime import settings


def cycle(monkeypatch, tmp_path, *, history='0'):
    env = settings(tmp_path); env['NEWS_HISTORICAL_REPAIR_ENABLED'] = history
    for key,value in env.items(): monkeypatch.setenv(key,value)
    calls=[]
    class Session:
        def close(self): calls.append('close')
    def module(name, **kwargs):
        result=types.ModuleType(name); result.__dict__.update(kwargs)
        monkeypatch.setitem(sys.modules,name,result)
        return result
    def fetch(**kw): calls.append(('fetch',kw)); return 1
    def summary(**kw): calls.append(('summary',kw)); return {}
    def contaminated(**kw): calls.append(('contaminated',kw)); return {}
    def index(db, **kw): calls.append(('index',kw)); return 400 if history == '1' else 1
    def images(db, **kw): calls.append(('images',kw)); return 0
    def mislabels(db, **kw): calls.append(('mislabels',kw)); return 0
    def unresolved(db, **kw): calls.append(('unresolved',kw)); return 0
    def duplicates(db, **kw): calls.append(('duplicates',kw)); return 0
    def gossip(db, **kw): calls.append(('gossip',kw)); return 0
    def inventory(db, **kw): calls.append(('inventory',kw)); return {'football': 2}
    def session(): calls.append('session'); return Session()
    sources=module('bot.fetch_sources',fetch_and_store_all_articles=fetch)
    module('bot.rewrite_ai',reset_openai_rate_limit=lambda:calls.append('reset'))
    module('public_cache',bump_public_cache=lambda:calls.append('cache'))
    repairs=module('repair_content',repair_summary_only=summary,repair_contaminated=contaminated)
    module('database',SessionLocal=session)
    module('bot.news_publication_clock',ensure_news_publication_clock=lambda db:None)
    module(
        'public_index',
        index_missing=index,
        repair_recent_news_images=images,
        repair_recent_sport_mislabels=mislabels,
        repair_recent_unresolved=unresolved,
        repair_recent_duplicate_news=duplicates,
        repair_recent_gossip_news=gossip,
        recent_public_sport_inventory=inventory,
    )
    path=Path(__file__).parents[1]/'bot/scheduler.py'
    spec=importlib.util.spec_from_file_location('bot._c22_scheduler_fixture',path)
    scheduler=importlib.util.module_from_spec(spec);spec.loader.exec_module(scheduler)
    # Storage is tested separately. This unit exercises cycle routing and quotas.
    monkeypatch.setattr(scheduler,'_start_errors',lambda:[],raising=False)
    return scheduler,calls,sources,repairs,env


def test_historical_off_scheduler_does_not_open_legacy_index_database(monkeypatch,tmp_path):
    scheduler,calls,_,_,_=cycle(monkeypatch,tmp_path)
    scheduler.job()
    # Bounded current-News maintenance still runs; legacy backfill stays off.
    assert calls.count('session') == calls.count('close') == 1
    assert not any(isinstance(c,tuple) and c[0] in ('index','summary','contaminated') for c in calls)
    assert sum(isinstance(c,tuple) and c[0]=='fetch' for c in calls)==1


def test_opt_in_history_is_bounded_to_one_index_batch(monkeypatch,tmp_path):
    scheduler,calls,_,_,_=cycle(monkeypatch,tmp_path,history='1')
    assert scheduler.job()==1
    assert ('summary',{'max_pages':1,'max_rewrite':2}) in calls
    assert [c for c in calls if isinstance(c,tuple) and c[0]=='index']==[('index',{'limit':400})]
    assert ('contaminated',{'max_pages':1}) in calls and calls.count('close')==2


def test_historical_and_new_requests_share_same_cycle_limit(monkeypatch,tmp_path):
    scheduler,calls,sources,repairs,env=cycle(monkeypatch,tmp_path,history='1')
    decisions=[]
    def repair(**kw): decisions.append(reserve_ai_request()); return {}
    def fetch(**kw):
        decisions.extend([reserve_ai_request(),reserve_ai_request()]); return 1
    repairs.repair_summary_only=repair;sources.fetch_and_store_all_articles=fetch
    scheduler.job()
    assert decisions==[True,True,False]
    assert not AiRequestBudget(2,env['NEWS_AI_LEDGER_PATH'],daily_limit=2).can_start()


def test_exhausted_daily_quota_still_runs_zero_ai_public_repairs(monkeypatch,tmp_path):
    scheduler,calls,_,_,env=cycle(monkeypatch,tmp_path,history='1')
    b=AiRequestBudget(3,env['NEWS_AI_LEDGER_PATH'],daily_limit=3)
    assert all(b.reserve() for _ in range(3))
    assert scheduler.job()==0
    probe=AiRequestBudget(3,env['NEWS_AI_LEDGER_PATH'],daily_limit=3)
    assert not probe.can_start()
    assert probe.blocked_reason == 'daily_request_limit'
    assert ('images',{'limit':80,'max_age_hours':72,'recover_limit':8}) in calls
    assert ('mislabels',{'limit':600,'max_age_hours':168}) in calls
    assert ('unresolved',{'limit':24}) in calls
    assert ('duplicates',{'limit':600,'max_age_hours':168}) in calls
    assert ('inventory',{'max_age_hours':72}) in calls
    assert not any(isinstance(c,tuple) and c[0] in ('fetch','index','summary','contaminated') for c in calls)


def test_zero_article_limit_still_runs_zero_ai_public_repairs(monkeypatch,tmp_path):
    scheduler,calls,_,_,_=cycle(monkeypatch,tmp_path)
    monkeypatch.setenv('NEWS_MAX_AI_ARTICLES','0')
    assert scheduler.job()==0
    assert ('mislabels',{'limit':600,'max_age_hours':168}) in calls
    assert ('inventory',{'max_age_hours':72}) in calls
    assert not any(isinstance(c,tuple) and c[0]=='fetch' for c in calls)


def test_invalidated_configuration_stops_next_cycle(monkeypatch,tmp_path):
    scheduler,calls,_,_,_=cycle(monkeypatch,tmp_path)
    monkeypatch.setattr(scheduler,'_start_errors',lambda:['news_worker_not_explicitly_enabled'])
    assert scheduler.job()==0 and not calls


def test_cycle_error_does_not_echo_secret_message(monkeypatch,tmp_path,caplog):
    scheduler,calls,sources,_,_=cycle(monkeypatch,tmp_path)
    def fail(**kw): raise RuntimeError('postgresql://private:DO_NOT_PRINT@private.example/')
    sources.fetch_and_store_all_articles=fail
    assert scheduler.job()==0
    assert 'RuntimeError' in caplog.text and 'DO_NOT_PRINT' not in caplog.text


def test_live_owner_blocks_manual_duplicate_job(monkeypatch,tmp_path):
    from news_runtime import news_owner
    scheduler,calls,_,_,env=cycle(monkeypatch,tmp_path)
    with news_owner(env['NEWS_AI_LEDGER_PATH']):
        assert scheduler.job()==0
    assert calls==[]


def test_disabled_budget_does_not_invalidate_public_cache(monkeypatch,tmp_path):
    scheduler,calls,sources,_,_=cycle(monkeypatch,tmp_path)
    sources.fetch_and_store_all_articles=lambda **kw:0
    assert scheduler.job()==0
    assert 'cache' not in calls


def test_next_interval_boundary_is_shared_across_redeploys(monkeypatch,tmp_path):
    scheduler,_,_,_,_=cycle(monkeypatch,tmp_path)
    first=scheduler._next_interval_boundary(
        datetime(2026,9,27,11,47,0,tzinfo=timezone.utc),30
    )
    second=scheduler._next_interval_boundary(
        datetime(2026,9,27,11,59,59,tzinfo=timezone.utc),30
    )
    assert first == second == datetime(2026,9,27,12,0,0,tzinfo=timezone.utc)


def test_image_health_job_is_zero_ai_and_uses_same_owner(monkeypatch,tmp_path):
    scheduler,calls,_,_,_=cycle(monkeypatch,tmp_path)
    assert scheduler.image_health_job()==0
    assert ('images',{'limit':160,'max_age_hours':72,'recover_limit':16}) in calls
    assert not any(isinstance(c,tuple) and c[0]=='fetch' for c in calls)


def test_main_releases_cycle_owner_before_scheduler_shutdown(monkeypatch,tmp_path):
    from news_runtime import news_owner
    scheduler,calls,_,_,env=cycle(monkeypatch,tmp_path)
    state=[];scheduled=[]
    class Blocking:
        running=False
        def add_job(self,func,*a,**kw):
            trigger = a[0] if a else None
            scheduled.append((func.__name__, trigger, kw.get('id'), kw.get('start_date'), kw.get('minutes')))
            assert trigger == 'interval'
            assert kw['max_instances']==1 and kw['coalesce'] is True
            assert kw.get('start_date') is not None
            assert kw['start_date'].tzinfo is not None
            if func is scheduler.job:
                assert kw['id']=='news-interval-cycle'
                assert kw['next_run_time'] == kw['start_date']
                assert kw['misfire_grace_time'] == 120
            elif func is scheduler.image_health_job:
                assert kw['id']=='news-image-health-cycle'
                assert kw['minutes']==10
            else:
                raise AssertionError(func)
        def start(self):
            self.running=True
            raise KeyboardInterrupt()
        def shutdown(self,wait):
            assert wait is True
            # Per-cycle ownership is already released once the job returns.
            with news_owner(env['NEWS_AI_LEDGER_PATH']): pass
            self.running=False;state.append('shutdown_after_cycle')
    fake=types.ModuleType('apscheduler.schedulers.blocking');fake.BlockingScheduler=Blocking
    monkeypatch.setitem(sys.modules,'apscheduler.schedulers.blocking',fake)
    with pytest.raises(KeyboardInterrupt): scheduler.main()
    assert state==['shutdown_after_cycle']
    assert len(scheduled)==2
    assert {(row[0],row[2]) for row in scheduled} == {
        ('job','news-interval-cycle'),
        ('image_health_job','news-image-health-cycle'),
    }


def test_image_health_boundary_is_offset_from_writer_boundary(monkeypatch,tmp_path):
    scheduler,_,_,_,_=cycle(monkeypatch,tmp_path)
    now=datetime(2026,9,27,12,51,0,tzinfo=timezone.utc)
    writer=scheduler._next_interval_boundary(now,30)
    image=scheduler._next_interval_boundary(now,10,offset_minutes=5)
    assert writer == datetime(2026,9,27,13,0,0,tzinfo=timezone.utc)
    assert image == datetime(2026,9,27,12,55,0,tzinfo=timezone.utc)
    assert writer != image
    assert image.minute % 10 == 5
