"""Send real process signals; prove rollback, no stolen leases and quick restart."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.models import SportsSchedulerLease
from collector.lock import acquire_scheduler_lock, lock_status, LOCK_NAME, WRITE_LOCK_NAME
from collector.worker_shutdown import graceful_shutdown

SCRIPT = r'''
import sys,time
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from models import Base
from collector.models import SportsSchedulerLease
from collector.lock import acquire_scheduler_lock,acquire_write_lock
from collector.worker_shutdown import graceful_shutdown
engine=create_engine('sqlite:///'+sys.argv[1]);Base.metadata.create_all(engine)
with engine.begin() as connection:
    connection.execute(text('create table score_sentinel (id integer primary key, score text)'))
    connection.execute(text("insert into score_sentinel values (1,'confirmed')"))
owner='worker-old'
with Session(engine) as db:
    acquire_scheduler_lock(db,owner=sys.argv[4]);acquire_write_lock(db,owner=sys.argv[3]);db.commit()
try:
    with graceful_shutdown(lambda:Session(engine),owner):
        with Session(engine) as db:
            db.execute(text("update score_sentinel set score='uncommitted' where id=1"))
            Path(sys.argv[2]).write_text('ready')
            time.sleep(60)
finally:
    engine.dispose()
'''

@pytest.mark.parametrize('signum,writer,scheduler',[(signal.SIGTERM,'worker-old','worker-old'),(signal.SIGINT,'worker-old','worker-old'),(signal.SIGTERM,'different-owner','worker-old'),(signal.SIGTERM,'different-owner','different-scheduler')])
def test_real_signal_releases_only_owned_leases_after_rollback(tmp_path,signum,writer,scheduler):
    database=tmp_path/'handoff.db';ready=tmp_path/'ready'
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    child=subprocess.Popen([sys.executable,'-c',SCRIPT,str(database),str(ready),writer,scheduler],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+12
        while not ready.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert ready.exists(),child.communicate(timeout=1)
        started=time.monotonic();child.send_signal(signum);stdout,stderr=child.communicate(timeout=5)
        assert child.returncode==0,(stdout,stderr)
        assert time.monotonic()-started<5
        engine=create_engine('sqlite:///'+str(database))
        from sqlalchemy import text
        with Session(engine) as db:
            assert db.execute(text('select score from score_sentinel where id=1')).scalar()=='confirmed'
            assert lock_status(db)['held'] is (scheduler!='worker-old')
            write=db.get(SportsSchedulerLease,WRITE_LOCK_NAME)
            assert write.owner_id == (None if writer=='worker-old' else writer)
            assert acquire_scheduler_lock(db,owner='worker-successor') is (scheduler=='worker-old')
            db.commit();assert lock_status(db)['owner_id']==('worker-successor' if scheduler=='worker-old' else scheduler)
        engine.dispose()
    finally:
        if child.poll() is None:child.kill();child.communicate(timeout=5)


def test_normal_cycle_does_not_release_leases_or_open_a_cleanup_session():
    calls=[];old=signal.getsignal(signal.SIGTERM)
    with graceful_shutdown(lambda:calls.append(True),'owner'):
        assert signal.getsignal(signal.SIGTERM)!=old
    assert not calls and signal.getsignal(signal.SIGTERM)==old


def test_main_uses_the_same_owner_through_the_shutdown_boundary():
    # Inspect the wiring without executing the production worker / real DB.
    import ast
    path=Path(__file__).resolve().parents[1]/'collector/worker.py'
    root=ast.parse(path.read_text())
    main=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    calls=[n for n in ast.walk(main) if isinstance(n,ast.Call)]
    assert any(isinstance(n.func,ast.Name) and n.func.id=='graceful_shutdown' for n in calls)
    run=next(n for n in calls if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_run_worker')
    assert any(k.arg=='owner' and isinstance(k.value,ast.Name) and k.value.id=='owner' for k in run.keywords)
