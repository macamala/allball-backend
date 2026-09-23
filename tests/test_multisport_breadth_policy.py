from datetime import datetime, timedelta

from collector.models import SportsCollectorJob


def test_sofascore_blocked_job_uses_job_key_schema():
    row = SportsCollectorJob(job_key="sofascore-multisport-breadth-v2")
    row.last_status = "blocked"
    row.last_run_at = datetime.utcnow() - timedelta(hours=2)
    assert row.job_key == "sofascore-multisport-breadth-v2"
    assert row.last_status == "blocked"
