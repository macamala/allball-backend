"""Graceful process shutdown; a successor must never steal an active lease."""
from contextlib import contextmanager
from datetime import datetime
import logging
import signal
import threading

logger = logging.getLogger(__name__)


class WorkerShutdown(SystemExit):
    """Unwind processing and its transaction finalizers before lease release."""


@contextmanager
def graceful_shutdown(session_factory, owner):
    """Install signals only in the main thread and restore previous handlers.

    Cleanup uses a NEW transaction after the worker's session has unwound.
    It releases only this process's leases, not a successor's or another writer's.
    SIGKILL / host loss still relies on the existing fail-closed TTL.
    """
    requested = False
    previous = {}

    def stop(signum, frame):
        nonlocal requested
        if requested:
            return  # A second signal cannot interrupt our rollback/release.
        requested = True
        raise WorkerShutdown(0)

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, stop)
    try:
        yield
    except WorkerShutdown:
        logger.info('Results worker stopping; active transaction unwound')
    finally:
        try:
            if requested:
                from collector.lock import LOCK_NAME, WRITE_LOCK_NAME
                from collector.models import SportsSchedulerLease
                db = session_factory()
                try:
                    # Compare ownership in the UPDATE itself, not in a prior SELECT:
                    # a concurrent legitimate successor must remain untouched.
                    now = datetime.utcnow()
                    released = db.query(SportsSchedulerLease).filter(
                        SportsSchedulerLease.lock_name.in_((LOCK_NAME, WRITE_LOCK_NAME)),
                        SportsSchedulerLease.owner_id == owner,
                    ).update({'owner_id': None, 'expires_at': now, 'heartbeat_at': now}, synchronize_session=False)
                    db.commit()
                    logger.info('WORKER_SHUTDOWN_RELEASE owner=%s leases=%s', owner, released)
                except Exception:
                    db.rollback()
                    logger.exception('Shutdown lease release failed; existing TTL remains the guard')
                finally:
                    db.close()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
