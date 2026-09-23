from datetime import datetime

from collector.adapters import FetchResult
from collector.fifa_identity_reconcile import reconcile_current_fifa_identity
from collector.models import SportsEvent
from collector.provider import NinkoCollectedSportsDataProvider
from collector.util import dump_json, load_json
from database import SessionLocal


def _row(event_id, competition_id, source_id, home, away, source_name):
    return SportsEvent(
        event_id=event_id,
        sport_id="football",
        competition_id=competition_id,
        event_family="team_match",
        fingerprint=event_id,
        start_time=datetime(2026, 9, 24, 0, 0, 0),
        status="scheduled",
        display_eligible=False,
        primary_source_id="fifa",
        participants_json=dump_json(
            {
                "home": {"name": home},
                "away": {"name": away},
            }
        ),
        score_json=dump_json({"home": None, "away": None}),
        extra_json=dump_json(
            {
                "source_family": "fifa-digital",
                "source_event_id": source_id,
                "source_event_ids": {"fifa-digital": source_id},
                "source_competition_name": source_name,
                "display_eligible": False,
            }
        ),
    )


def test_reconcile_promotes_country_qualified_fifa_identity(monkeypatch):
    db = SessionLocal()
    event_id = "ninko-test-fifa-tun-reconcile"
    try:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.add(_row(event_id, "football-ligue-1", "fifa-tun-1", "Marsa", "CS Hammam Lif", "Ligue 1"))
        db.commit()

        def fake_fetch(_self, _request):
            return FetchResult(
                ok=True,
                http_status=200,
                events=[
                    {
                        "source_event_id": "fifa-tun-1",
                        "competition_key": "football-tun-ligue-1",
                        "source_competition_id": "f4jc2cc5nq7flaoptpi5ua4k4",
                        "source_competition_name": "Ligue 1",
                        "competition": "Ligue 1",
                        "country_id": "TUN",
                    }
                ],
            )

        monkeypatch.setattr("collector.fifa_identity_reconcile.FifaFootballAdapter.fetch", fake_fetch)
        stats = reconcile_current_fifa_identity(db, days_back=500, days_forward=500)
        db.commit()

        row = db.get(SportsEvent, event_id)
        extra = load_json(row.extra_json, {}) or {}
        assert stats["matched"] == 1
        assert extra["public_competition_key"] == "football-tun-ligue-1"
        assert extra["source_competition_id"] == "f4jc2cc5nq7flaoptpi5ua4k4"
        assert row.country_id == "TUN"

        payload = NinkoCollectedSportsDataProvider()._to_normalized(row, list_mode=True)
        assert payload is not None
        assert payload["competition_key"] == "football-tun-ligue-1"
        assert payload["competition_name"] == "Ligue 1"
    finally:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_reconciled_concacaf_identity_cannot_publish_as_uefa(monkeypatch):
    db = SessionLocal()
    event_id = "ninko-test-fifa-concacaf-reconcile"
    try:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.add(
            _row(
                event_id,
                "uefa-nations-league",
                "fifa-concacaf-1",
                "Bahamas",
                "Saint Martin",
                "Concacaf Nations League",
            )
        )
        db.commit()

        def fake_fetch(_self, _request):
            return FetchResult(
                ok=True,
                http_status=200,
                events=[
                    {
                        "source_event_id": "fifa-concacaf-1",
                        "competition_key": "football-concacaf-nations-league",
                        "source_competition_id": "cu0rmpyff5692eo06ltddjo8a",
                        "source_competition_name": "Concacaf Nations League",
                        "competition": "Concacaf Nations League",
                    }
                ],
            )

        monkeypatch.setattr("collector.fifa_identity_reconcile.FifaFootballAdapter.fetch", fake_fetch)
        stats = reconcile_current_fifa_identity(db, days_back=500, days_forward=500)
        db.commit()

        row = db.get(SportsEvent, event_id)
        payload = NinkoCollectedSportsDataProvider()._to_normalized(row, list_mode=True)
        assert stats["matched"] == 1
        assert payload is not None
        assert payload["competition_key"] == "football-concacaf-nations-league"
        assert payload["competition_key"] != "uefa-nations-league"
        assert payload["competition_name"] == "Concacaf Nations League"
    finally:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.commit()
        db.close()
