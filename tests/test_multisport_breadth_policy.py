from datetime import datetime, timedelta, timezone

from collector.models import SportsCollectorJob


def test_sofascore_blocked_job_uses_job_key_schema():
    row = SportsCollectorJob(job_key="sofascore-multisport-breadth-v2")
    row.last_status = "blocked"
    row.last_run_at = datetime.utcnow() - timedelta(hours=2)
    assert row.job_key == "sofascore-multisport-breadth-v2"
    assert row.last_status == "blocked"



def test_breadth_audit_uses_exclusive_local_day_end():
    from collector.breadth_audit import _inclusive_provider_end

    exclusive = datetime(2026, 9, 25, 14, 0, 0, tzinfo=timezone.utc)
    assert _inclusive_provider_end(exclusive) == "2026-09-25T13:59:59.999000Z"
