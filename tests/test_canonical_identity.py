from datetime import datetime, timedelta
import json

from collector.canonical_collapse import collapse_canonical_events
from collector.models import SportsEvent
from collector.participant_alias import names_equivalent
from collector.util import dump_json
from database import SessionLocal


def _event(**kwargs):
    payload = {
        "event_id": kwargs["event_id"],
        "sport_id": kwargs.get("sport_id", "football"),
        "competition_id": kwargs.get("competition_id", "france-ligue-1"),
        "event_family": "team_match",
        "fingerprint": kwargs["event_id"],
        "start_time": kwargs.get("start_time", datetime(2026, 9, 20, 18, 0, 0)),
        "display_eligible": True,
        "status": kwargs.get("status", "scheduled"),
        "score_json": dump_json(kwargs.get("score", {"home": None, "away": None})),
        "participants_json": dump_json(
            {"home": {"name": kwargs["home"]}, "away": {"name": kwargs["away"]}}
        ),
        "extra_json": dump_json({"display_eligible": True, "source_family": kwargs.get("family", "espn-html")}),
    }
    return SportsEvent(**payload)


def _public(db, competition, day=None):
    db.expire_all()
    query = db.query(SportsEvent).filter_by(competition_id=competition).filter(
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
    )
    if day:
        start = datetime.fromisoformat(day)
        query = query.filter(SportsEvent.start_time >= start, SportsEvent.start_time < start + timedelta(days=1))
    rows = query.all()
    out = []
    for row in rows:
        parts = json.loads(row.participants_json or "{}")
        score = json.loads(row.score_json or "{}")
        out.append(
            {
                "id": row.event_id,
                "status": row.status,
                "score": score,
                "home": parts.get("home") or {},
                "away": parts.get("away") or {},
            }
        )
    return out


def test_name_normalization_equivalents():
    assert names_equivalent("Monaco", "AS Monaco FC")
    assert names_equivalent("Lens", "Racing Club de Lens")
    assert names_equivalent("Monza", "AC Monza")
    assert names_equivalent("Sassuolo", "US Sassuolo Calcio")
    assert names_equivalent("Espanyol", "RCD Espanyol de Barcelona")
    assert names_equivalent("Elche", "Elche CF")
    assert names_equivalent("São Paulo", "Sao Paulo - SP")
    assert names_equivalent("Internacional", "Internacional -")
    assert names_equivalent("FR Monaco", "Monaco")
    assert not names_equivalent("Inter", "Inter Miami")
    assert not names_equivalent("Real Madrid", "Real Sociedad")
    assert not names_equivalent("Manchester United", "Manchester City")


def test_short_vs_official_names_collapse_one_fixture():
    db = SessionLocal()
    try:
        db.add(_event(event_id="ninko-id-mon-a", home="Monaco", away="Lens", competition_id="france-l1-ident", score={"home": 2, "away": 1}, status="finished"))
        db.add(_event(event_id="ninko-id-mon-b", home="AS Monaco FC", away="Racing Club de Lens", competition_id="france-l1-ident", family="sportscore"))
        db.add(_event(event_id="ninko-id-monz-a", home="Monza", away="Sassuolo", competition_id="italy-sa-ident"))
        db.add(
            _event(
                event_id="ninko-id-monz-b",
                home="AC Monza",
                away="US Sassuolo Calcio",
                competition_id="italy-sa-ident",
                family="sportscore",
            )
        )
        db.add(_event(event_id="ninko-id-esp-a", home="Espanyol", away="Elche", competition_id="spain-laliga-ident"))
        db.add(
            _event(
                event_id="ninko-id-esp-b",
                home="RCD Espanyol de Barcelona",
                away="Elche CF",
                competition_id="spain-laliga-ident",
                family="thesportsdb",
            )
        )
        db.commit()
        result = collapse_canonical_events(db)
        assert result["collapsed"] >= 3
        assert len(_public(db, "france-l1-ident")) == 1
        assert len(_public(db, "italy-sa-ident")) == 1
        assert len(_public(db, "spain-laliga-ident")) == 1
        monaco = _public(db, "france-l1-ident")[0]
        assert (monaco.get("score") or {}).get("home") == 2
        assert (monaco.get("score") or {}).get("away") == 1
        assert monaco.get("status") == "finished"
    finally:
        db.close()


def test_finished_observation_hides_scheduled_duplicate():
    db = SessionLocal()
    try:
        db.add(
            _event(
                event_id="ninko-id-ft-a",
                home="Porto",
                away="Benfica",
                competition_id="portugal-liga",
                score={"home": 1, "away": 0},
                status="finished",
                family="bbc-sport",
            )
        )
        db.add(
            _event(
                event_id="ninko-id-ft-b",
                home="FC Porto",
                away="SL Benfica",
                competition_id="portugal-liga",
                family="sportscore",
            )
        )
        db.commit()
        collapse_canonical_events(db)
        public = _public(db, "portugal-liga")
        assert len(public) == 1
        assert public[0]["status"] == "finished"
        assert public[0]["score"]["home"] == 1
        assert public[0]["score"]["away"] == 0
    finally:
        db.close()


def test_similar_names_do_not_merge():
    db = SessionLocal()
    try:
        db.add(_event(event_id="ninko-id-int-a", home="Inter", away="Milan", competition_id="italy-sa-inter"))
        db.add(_event(event_id="ninko-id-int-b", home="Inter Miami", away="Nashville", competition_id="italy-sa-inter"))
        db.commit()
        collapse_canonical_events(db)
        assert len(_public(db, "italy-sa-inter")) == 2
    finally:
        db.close()


def test_same_teams_different_dates_do_not_merge():
    db = SessionLocal()
    try:
        db.add(_event(event_id="ninko-id-dt-a", home="Ajax", away="Feyenoord", competition_id="eredivisie"))
        db.add(
            _event(
                event_id="ninko-id-dt-b",
                home="Ajax",
                away="Feyenoord",
                competition_id="eredivisie",
                start_time=datetime(2026, 9, 21, 18, 0, 0),
            )
        )
        db.commit()
        collapse_canonical_events(db)
        assert len(_public(db, "eredivisie", "2026-09-20")) == 1
        assert len(_public(db, "eredivisie", "2026-09-21")) == 1
    finally:
        db.close()


def test_same_names_different_competitions_do_not_merge():
    db = SessionLocal()
    try:
        db.add(_event(event_id="ninko-id-cp-a", home="Roma", away="Lazio", competition_id="italy-sa-coppa-a"))
        db.add(_event(event_id="ninko-id-cp-b", home="Roma", away="Lazio", competition_id="coppa-italia-ident"))
        db.commit()
        collapse_canonical_events(db)
        assert len(_public(db, "italy-sa-coppa-a")) == 1
        assert len(_public(db, "coppa-italia-ident")) == 1
    finally:
        db.close()


def test_null_scores_are_not_converted_to_zero():
    db = SessionLocal()
    try:
        db.add(_event(event_id="ninko-id-nl-a", home="Nantes", away="Lille", competition_id="france-ligue-1-null"))
        db.add(
            _event(
                event_id="ninko-id-nl-b",
                home="FC Nantes",
                away="Lille",
                competition_id="france-ligue-1-null",
                family="sportscore",
            )
        )
        db.commit()
        collapse_canonical_events(db)
        public = _public(db, "france-ligue-1-null")
        assert len(public) == 1
        assert public[0]["score"]["home"] in (None, "")
        assert public[0]["score"]["away"] in (None, "")
        assert public[0]["score"]["home"] != 0
    finally:
        db.close()
