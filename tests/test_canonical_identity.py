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
        "extra_json": dump_json({
            "display_eligible": True,
            "source_family": kwargs.get("family", "espn-html"),
            **({"periods": kwargs.get("periods")} if kwargs.get("periods") is not None else {}),
            **({"source_competition_name": kwargs.get("source_competition_name")} if kwargs.get("source_competition_name") else {}),
        }),
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
    assert names_equivalent("Lokomotiv Tashkent", "Lok. Tashkent")
    assert names_equivalent("Neftchi Fergana", "Neftchi Fargona")
    assert names_equivalent("Bologna", "Bologna FC")
    assert names_equivalent("Torino", "Torino FC")
    assert not names_equivalent("Inter", "Inter Miami")
    assert not names_equivalent("Inter", "Internacional")
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


def test_roma_inter_and_fiorentina_napoli_collapse_without_hardcoded_fixtures():
    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 20, 18, 45, 0)
        later = datetime(2026, 9, 20, 19, 0, 0)
        db.add(_event(event_id="ninko-id-ri-a", home="Roma", away="Inter", competition_id="italy-sa-depth", score={"home": 2, "away": 2}, status="finished", start_time=kickoff))
        db.add(_event(event_id="ninko-id-ri-b", home="AS Roma", away="FC Internazionale Milano", competition_id="italy-sa-depth", family="sportscore", start_time=later))
        db.add(_event(event_id="ninko-id-fn-a", home="Fiorentina", away="Napoli", competition_id="italy-sa-depth", score={"home": 0, "away": 1}, status="halftime", start_time=kickoff))
        db.add(_event(event_id="ninko-id-fn-b", home="ACF Fiorentina", away="SSC Napoli", competition_id="italy-sa-depth", family="thesportsdb", start_time=later))
        db.add(_event(event_id="ninko-id-ri-cup", home="Roma", away="Inter", competition_id="coppa-italia-depth", start_time=kickoff))
        db.add(_event(event_id="ninko-id-ri-next", home="Roma", away="Inter", competition_id="italy-sa-depth", start_time=datetime(2026, 9, 21, 18, 45, 0)))
        db.commit()
        collapse_canonical_events(db)
        serie = _public(db, "italy-sa-depth")
        same_day = [row for row in serie if row["id"] != "ninko-id-ri-next"]
        assert len(same_day) == 2
        assert any(row["status"] == "finished" and (row.get("score") or {}).get("home") == 2 for row in same_day)
        assert any((row.get("score") or {}).get("away") == 1 for row in same_day)
        assert len(_public(db, "coppa-italia-depth")) == 1
    finally:
        db.close()


def test_lokomotiv_and_club_particle_aliases_collapse():
    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 20, 15, 0, 0)
        db.add(_event(event_id="ninko-id-lok-a", home="Lokomotiv Tashkent", away="Neftchi Fergana", competition_id="uzbekistan-super-league", score={"home": 0, "away": 1}, status="finished", start_time=kickoff))
        db.add(_event(event_id="ninko-id-lok-b", home="Lok. Tashkent", away="Neftchi Fergana", competition_id="uzbekistan-super-league", family="sportscore", start_time=kickoff))
        db.add(_event(event_id="ninko-id-bo-a", home="Bologna", away="Torino", competition_id="italy-sa-particles", score={"home": 1, "away": 0}, status="finished", start_time=kickoff))
        db.add(_event(event_id="ninko-id-bo-b", home="Bologna FC", away="Torino FC", competition_id="italy-sa-particles", family="thesportsdb", start_time=kickoff))
        db.commit()
        collapse_canonical_events(db)
        assert len(_public(db, "uzbekistan-super-league")) == 1
        uz = _public(db, "uzbekistan-super-league")[0]
        assert uz["score"]["home"] == 0
        assert uz["score"]["away"] == 1
        assert len(_public(db, "italy-sa-particles")) == 1
    finally:
        db.close()


def test_false_merge_protection_youth_women_cup_doubleheader():
    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 20, 18, 0, 0)
        db.add(_event(event_id="ninko-id-yh-a", home="Arsenal", away="Chelsea", competition_id="england-pl-false"))
        db.add(_event(event_id="ninko-id-yh-b", home="Arsenal U21", away="Chelsea U21", competition_id="england-pl-false"))
        db.add(_event(event_id="ninko-id-wm-a", home="Arsenal", away="Chelsea", competition_id="england-wsl-false"))
        db.add(_event(event_id="ninko-id-bb-a", home="Yankees", away="Red Sox", competition_id="mlb-false", sport_id="baseball", start_time=kickoff))
        db.add(_event(event_id="ninko-id-bb-b", home="Yankees", away="Red Sox", competition_id="mlb-false", sport_id="baseball", start_time=datetime(2026, 9, 20, 23, 0, 0)))
        db.commit()
        collapse_canonical_events(db)
        assert len(_public(db, "england-pl-false")) == 2
        assert len(_public(db, "england-wsl-false")) == 1
        assert len(_public(db, "mlb-false")) == 2
    finally:
        db.close()



def test_world_aquatics_duplicate_collapse_keeps_rich_periods():
    """A richer official water-polo result must survive canonical collapse."""
    db = SessionLocal()
    competition = "world-aquatics-events"
    rich_id = "ninko-test-wa-rich"
    basic_id = "ninko-test-wa-basic"
    try:
        db.add(
            _event(
                event_id=rich_id,
                sport_id="water-polo",
                competition_id=competition,
                home="Montenegro",
                away="Georgia",
                start_time=datetime(2026, 7, 19, 18, 0, 0),
                score={"home": 19, "away": 17},
                status="finished",
                family="world-aquatics-api",
                periods=[
                    {"label": "Q1", "home": 6, "away": 2},
                    {"label": "Q2", "home": 4, "away": 6},
                    {"label": "Q3", "home": 4, "away": 3},
                    {"label": "Q4", "home": 5, "away": 6},
                ],
            )
        )
        db.add(
            _event(
                event_id=basic_id,
                sport_id="water-polo",
                competition_id=competition,
                home="Montenegro",
                away="Georgia",
                start_time=datetime(2026, 7, 19, 18, 0, 0),
                score={"home": 19, "away": 17},
                status="finished",
                family="omega-timing",
            )
        )
        db.commit()
        result = collapse_canonical_events(db, competition_ids=[competition])
        assert result["collapsed"] >= 1

        roots = (
            db.query(SportsEvent)
            .filter_by(competition_id=competition)
            .filter(SportsEvent.event_id.in_([rich_id, basic_id]))
            .filter(SportsEvent.canonical_event_id.is_(None))
            .all()
        )
        assert len(roots) == 1

        root = roots[0]
        extra = json.loads(root.extra_json or "{}")
        assert extra.get("periods") == [
            {"label": "Q1", "home": 6, "away": 2},
            {"label": "Q2", "home": 4, "away": 6},
            {"label": "Q3", "home": 4, "away": 3},
            {"label": "Q4", "home": 5, "away": 6},
        ]
    finally:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_([rich_id, basic_id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_fifa_public_payload_keeps_stable_key_and_human_display_name():
    from collector.provider import NinkoCollectedSportsDataProvider

    row = _event(
        event_id="ninko-test-fifa-display",
        sport_id="football",
        competition_id="fifa-connected-competitions",
        home="Spain",
        away="Argentina",
        start_time=datetime(2026, 7, 19, 0, 0, 0),
        score={"home": 1, "away": 0},
        status="finished",
        family="fifa-digital",
        source_competition_name="FIFA World Cup",
    )
    provider = NinkoCollectedSportsDataProvider()
    payload = provider._to_normalized(row, include_detail=True)
    assert payload is not None
    assert payload["competition_key"] == "fifa-connected-competitions"
    assert payload["competition"] == "FIFA World Cup"
    assert payload["competition_name"] == "FIFA World Cup"



def test_fifa_source_native_competitions_are_public_but_contamination_is_rejected():
    from collector.competition_identity import correct_public_competition_id

    assert (
        correct_public_competition_id(
            stored_competition_id="football-npfl",
            source_competition_name="NPFL",
            sport_id="football",
            source_family="fifa-digital",
        )
        == "football-npfl"
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="england-premier-league",
            source_competition_name="Premier League",
            sport_id="football",
            source_family="fifa-digital",
        )
        is None
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="uefa-nations-league",
            source_competition_name="Concacaf Nations League",
            sport_id="football",
            source_family="fifa-digital",
        )
        is None
    )


def test_fifa_dynamic_public_payload_uses_human_source_league_name():
    from collector.provider import NinkoCollectedSportsDataProvider

    row = _event(
        event_id="ninko-test-fifa-npfl",
        sport_id="football",
        competition_id="football-npfl",
        home="Enyimba",
        away="Kano Pillars",
        start_time=datetime(2026, 9, 24, 15, 0, 0),
        family="fifa-digital",
        source_competition_name="NPFL",
    )
    row.display_eligible = False
    provider = NinkoCollectedSportsDataProvider()
    payload = provider._to_normalized(row, list_mode=True)
    assert payload is not None
    assert payload["competition_key"] == "football-npfl"
    assert payload["competition"] == "NPFL"
    assert payload["competition_name"] == "NPFL"
