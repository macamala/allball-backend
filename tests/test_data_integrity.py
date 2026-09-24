from collector.adapters_bbc import extract_bbc_events
from collector.competition_identity import (
    correct_public_competition_id,
    event_accepted_for_mapping,
    label_matches_competition,
)
from collector.display import sanitize_participant_name
from collector.enrichment import is_display_eligible, quality_flags_for_name
from collector.html_parse import parse_tables
from collector.identity import identity_confidence, should_merge_enrichment
from collector.participant_text import clean_participant_name, fold_for_identity, repair_mojibake


BBC_HUB = {
    "eventGroups": [
        {"displayLabel": "Premier League", "secondaryGroups": [{"events": [{"home": {"fullName": "Arsenal"}, "away": {"fullName": "Chelsea"}}]}]},
        {"displayLabel": "Australian A-League", "secondaryGroups": [{"events": [{"home": {"fullName": "Sydney FC"}, "away": {"fullName": "Melbourne Victory"}}]}]},
        {"displayLabel": "Brazilian Serie A", "secondaryGroups": [{"events": [{"home": {"fullName": "Flamengo"}, "away": {"fullName": "Palmeiras"}}]}]},
        {"displayLabel": "Eliteserien", "secondaryGroups": [{"events": [{"home": {"fullName": "Kristiansund"}, "away": {"fullName": "Rosenborg"}}]}]},
        {"displayLabel": "Italian Serie A", "secondaryGroups": [{"events": [{"home": {"fullName": "Roma"}, "away": {"fullName": "Inter Milan"}}]}]},
        {"displayLabel": "League Two", "secondaryGroups": [{"events": [{"home": {"fullName": "Salford City"}, "away": {"fullName": "Swindon Town"}}]}]},
        {"displayLabel": "Scottish League Two", "secondaryGroups": [{"events": [{"home": {"fullName": "Elgin City"}, "away": {"fullName": "Stranraer"}}]}]},
    ]
}


def test_bbc_does_not_assign_norway_to_brasileirao():
    assert extract_bbc_events({"data": BBC_HUB}, "brazil-serie-a")[0]["home"]["name"] == "Flamengo"
    nor = extract_bbc_events({"data": BBC_HUB}, "norway-eliteserien")
    assert nor and nor[0]["home"]["name"] == "Kristiansund"
    assert not any(row["home"]["name"] == "Kristiansund" for row in extract_bbc_events({"data": BBC_HUB}, "brazil-serie-a"))


def test_bbc_does_not_assign_italy_to_brasileirao():
    events = extract_bbc_events({"data": BBC_HUB}, "brazil-serie-a")
    assert all(row["home"]["name"] != "Roma" for row in events)


def test_bbc_does_not_assign_uk_clubs_to_a_league():
    events = extract_bbc_events({"data": BBC_HUB}, "australia-a-league")
    names = {row["home"]["name"] for row in events}
    assert names == {"Sydney FC"}
    assert "Elgin City" not in names
    assert "Salford City" not in names


def test_label_match_requires_all_tokens_by_default():
    assert not label_matches_competition("Premier League", "australia-a-league")
    assert label_matches_competition("Australian A-League", "australia-a-league")
    assert not label_matches_competition("Italian Serie A", "brazil-serie-a")


def test_serbian_name_variants_fold_together():
    a = fold_for_identity("RS Železničar Pančevo")
    b = fold_for_identity("Zeleznicar Pancevo")
    assert a.split()[-1] == b.split()[-1] or "zeleznicar" in a and "zeleznicar" in b
    left = {
        "sport": "football",
        "event_family": "team_match",
        "competition_key": "serbia-superliga",
        "home": {"name": "Železničar Pančevo"},
        "away": {"name": "Crvena Zvezda"},
        "start_time": "2026-09-19T18:00:00Z",
        "source_event_ids": {"openligadb": "x"},
    }
    right = {
        **left,
        "home": {"name": "Zeleznicar Pancevo"},
        "away": {"name": "Crvena zvezda"},
        "source_event_ids": {"openligadb": "x"},
    }
    assert should_merge_enrichment(left, right) is True


def test_montevideo_variants_merge_with_ids():
    a = {
        "sport": "football",
        "event_family": "team_match",
        "competition_key": "copa-sudamericana",
        "home": {"name": "Montevideo City (Uru)"},
        "away": {"name": "Cienciano (Per)"},
        "start_time": "2026-09-19T00:30:00Z",
        "source_event_ids": {"tsdb": "1"},
    }
    b = {**a, "home": {"name": "Montevideo City Torque"}, "away": {"name": "Cienciano"}, "source_event_ids": {"tsdb": "1"}}
    assert identity_confidence(a, b) == 100


def test_date_cannot_be_a_participant_from_tables():
    html = "<table><tr><td>18.09.2026</td><td>19-30</td><td>SCR SK Rapid</td></tr></table>"
    events = parse_tables(html)
    assert not any((row.get("home") or {}).get("name") == "18.09.2026" for row in events)
    timed = parse_tables("<table><tr><td>Molde Aalesund</td><td>19.09. 2026 18:00</td></tr></table>")
    assert not any("19.09" in ((row.get("away") or {}).get("name") or "") for row in timed)
    assert "name_is_date" in quality_flags_for_name("19.09. 2026 16:00")
    assert is_display_eligible({"home": {"name": "Molde"}, "away": {"name": "19.09. 2026 16:00"}, "sport": "football"}) is False


def test_country_code_not_part_of_display_name():
    assert clean_participant_name("GB AFC Wimbledon") == "AFC Wimbledon"
    assert clean_participant_name("Milton Keynes DonsGB") == "Milton Keynes Dons"
    assert clean_participant_name("BR Independiente del Valle") == "Independiente del Valle"
    assert clean_participant_name("AS Monaco") == "AS Monaco"
    assert clean_participant_name("AC Milan") == "AC Milan"
    assert clean_participant_name("US Sassuolo") == "US Sassuolo"
    assert clean_participant_name("US Chicago White Sox", sport="baseball") == "Chicago White Sox"
    assert clean_participant_name("US Sassuolo", sport="football") == "US Sassuolo"
    assert clean_participant_name("US Colorado Springs", competition_country="US") == "Colorado Springs"
    assert clean_participant_name("US Sassuolo", competition_country="IT") == "US Sassuolo"
    assert clean_participant_name("IT Roma") == "Roma"
    assert clean_participant_name("BE Oud-Heverlee Leuven") == "Oud-Heverlee Leuven"
    assert clean_participant_name("SK Rapid") == "SK Rapid"
    assert sanitize_participant_name("1. FC Kaiserslautern") == "1. FC Kaiserslautern"
    from collector.participant_alias import canonical_display_name, names_equivalent, prefer_display

    assert canonical_display_name("IT AS Roma") == "AS Roma"
    assert canonical_display_name("FC Internazionale Milano") == "Inter"
    assert canonical_display_name("ACF Fiorentina") == "Fiorentina"
    assert canonical_display_name("SSC Napoli") == "Napoli"
    assert canonical_display_name("FC Barcelona") == "FC Barcelona"
    assert canonical_display_name("AC Milan") == "AC Milan"
    assert names_equivalent("Roma", "AS Roma")
    assert names_equivalent("Inter", "FC Internazionale Milano")
    assert names_equivalent("Fiorentina", "ACF Fiorentina")
    assert names_equivalent("Napoli", "SSC Napoli")
    assert not names_equivalent("Inter", "Inter Miami")
    assert prefer_display("Roma", "AS Roma") == "AS Roma"
    assert prefer_display("Inter", "FC Internazionale Milano") == "Inter"


def test_mojibake_repaired_but_unicode_kept():
    assert "è" in repair_mojibake("RAAL La LouviÃ¨re")
    assert repair_mojibake("Železničar") == "Železničar"
    assert repair_mojibake("Plzeň") == "Plzeň"
    assert "é" in repair_mojibake("AtlÃ©tico") or "Atl" in repair_mojibake("Atlético")


def test_premier_league_label_does_not_absorb_other_countries():
    assert label_matches_competition("Premier League", "england-premier-league")
    assert label_matches_competition("English Premier League", "england-premier-league")
    assert not label_matches_competition("Nigerian Premier League", "england-premier-league")
    assert not label_matches_competition("Ukraine Premier League", "england-premier-league")
    assert label_matches_competition("Ukraine Premier League", "ukraine-premier-league")
    ok_ng, resolved_ng = event_accepted_for_mapping(
        {
            "source_competition_name": "Nigerian Premier League",
            "source_family": "sportscore",
            "sport": "football",
        },
        "england-premier-league",
    )
    assert ok_ng is False
    assert resolved_ng["resolution_method"] in {
        "rejected_label_mismatch",
        "rejected_label_other_competition",
    }
    ok_epl, _ = event_accepted_for_mapping(
        {"source_competition_name": "Premier League", "source_family": "bbc-sport", "sport": "football"},
        "england-premier-league",
    )
    assert ok_epl is True
    assert correct_public_competition_id(
        stored_competition_id="england-premier-league",
        source_competition_name="Nigerian Premier League",
        sport_id="football",
    ) is None
    assert (
        correct_public_competition_id(
            stored_competition_id="england-premier-league",
            source_competition_name="Ukraine Premier League",
            sport_id="football",
        )
        == "ukraine-premier-league"
    )


def test_hub_event_rejected_for_wrong_mapping():
    raw = {"competition": "Premier League", "source_family": "bbc-sport", "home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}}
    ok, resolved = event_accepted_for_mapping(raw, "brazil-serie-a")
    assert ok is False
    assert resolved["resolution_method"] in {
        "rejected_label_mismatch",
        "rejected_label_other_competition",
    }


def test_backfill_quarantines_cross_competition_clone():
    from datetime import datetime

    from collector.integrity import apply_backfill, plan_backfill
    from collector.models import SportsEvent
    from collector.util import dump_json, load_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 19, 18, 0, 0)
        participants = dump_json(
            {
                "home": {"name": "Kristiansund"},
                "away": {"name": "Rosenborg"},
            }
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-integrity-keep",
                sport_id="football",
                competition_id="norway-eliteserien",
                event_family="team_match",
                fingerprint="fp-integrity-keep",
                start_time=kickoff,
                participants_json=participants,
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "openfootball",
                        "source_competition_name": "Eliteserien",
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-integrity-leak",
                sport_id="football",
                competition_id="brazil-serie-a",
                event_family="team_match",
                fingerprint="fp-integrity-leak",
                start_time=kickoff,
                participants_json=participants,
                extra_json=dump_json({"display_eligible": True, "source_family": "bbc-sport"}),
            )
        )
        db.commit()
        plan = plan_backfill(db)
        assert "ninko-evt-integrity-leak" in plan["quarantine"]
        assert "ninko-evt-integrity-keep" not in plan["quarantine"]
        apply_backfill(db, plan)
        leak = db.query(SportsEvent).filter_by(event_id="ninko-evt-integrity-leak").one()
        extra = load_json(leak.extra_json, {}) or {}
        assert extra.get("display_eligible") is False
        assert leak.display_eligible is False
    finally:
        db.close()


def test_parenthetical_country_extracted_not_generic_parens():
    from collector.participant_text import clean_participant_name, extract_parenthetical_country

    cleaned, country = extract_parenthetical_country("Montevideo City (Uru)")
    assert cleaned == "Montevideo City"
    assert country == "UY"
    assert clean_participant_name("Cienciano (Per)") == "Cienciano"
    assert clean_participant_name("Sporting (CP)") == "Sporting (CP)"
    assert clean_participant_name("1. FC Kaiserslautern") == "1. FC Kaiserslautern"


def test_contextual_alias_collapses_one_public_event():
    from datetime import datetime

    from collector.canonical_collapse import collapse_canonical_events
    from collector.models import SportsEvent, SportsEventObservation
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 18, 0, 30, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-alias-a",
                sport_id="football",
                competition_id="copa-sudamericana",
                event_family="team_match",
                fingerprint="fp-alias-a",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 3, "away": 0}),
                participants_json=dump_json(
                    {"home": {"name": "River Plate City (Uru)"}, "away": {"name": "Andes Club (Per)"}}
                ),
                extra_json=dump_json({"display_eligible": True, "source_family": "openfootball"}),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-alias-b",
                sport_id="football",
                competition_id="copa-sudamericana",
                event_family="team_match",
                fingerprint="fp-alias-b",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 3, "away": 0}),
                participants_json=dump_json(
                    {"home": {"name": "River Plate City Torque"}, "away": {"name": "Andes Club"}}
                ),
                extra_json=dump_json({"display_eligible": True, "source_family": "thesportsdb"}),
            )
        )
        db.add(
            SportsEventObservation(
                event_id="ninko-evt-alias-b",
                source_id="thesportsdb",
                source_event_id="tsdb-1",
            )
        )
        db.commit()
        result = collapse_canonical_events(db)
        assert result["collapsed"] >= 1
        public = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            competition="copa-sudamericana",
            date_from="2026-09-18T00:00:00Z",
            date_to="2026-09-18T23:59:59Z",
        )
        names = {((row.get("home") or {}).get("name"), (row.get("away") or {}).get("name")) for row in public}
        assert len(names) == 1
        home, away = next(iter(names))
        assert "(Uru)" not in (home or "") and "(Per)" not in (away or "")
        keeper = next(iter(public))
        assert (keeper.get("home") or {}).get("country_id") == "UY"
        assert (keeper.get("away") or {}).get("country_id") == "PE"
        obs = db.query(SportsEventObservation).filter_by(source_event_id="tsdb-1").one()
        assert obs.event_id in {row["id"] for row in public} or db.query(SportsEvent).filter_by(
            event_id=obs.event_id
        ).one().canonical_event_id is None
        hidden = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.isnot(None)).count()
        assert hidden == 1
    finally:
        db.close()


def test_abbrev_with_context_collapses_utd_united():
    from datetime import datetime

    from collector.canonical_collapse import collapse_canonical_events
    from collector.models import SportsEvent
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 18, 12, 0, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-utd-a",
                sport_id="football",
                competition_id="thai-league-1",
                event_family="team_match",
                fingerprint="fp-utd-a",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 1, "away": 2}),
                participants_json=dump_json(
                    {"home": {"name": "Chao Phraya Utd"}, "away": {"name": "Northern Thani"}}
                ),
                extra_json=dump_json({"display_eligible": True}),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-utd-b",
                sport_id="football",
                competition_id="thai-league-1",
                event_family="team_match",
                fingerprint="fp-utd-b",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 1, "away": 2}),
                participants_json=dump_json(
                    {"home": {"name": "Chao Phraya United"}, "away": {"name": "Northern Thani"}}
                ),
                extra_json=dump_json({"display_eligible": True}),
            )
        )
        db.commit()
        collapse_canonical_events(db)
        public = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            competition="thai-league-1",
            date_from="2026-09-18T00:00:00Z",
            date_to="2026-09-18T23:59:59Z",
        )
        assert len(public) == 1
    finally:
        db.close()


def test_leading_club_tokens_collapse_with_context():
    from datetime import datetime

    from collector.canonical_collapse import collapse_canonical_events
    from collector.models import SportsEvent
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 19, 11, 0, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-lead-a",
                sport_id="football",
                competition_id="germany-2-bundesliga",
                event_family="team_match",
                fingerprint="fp-lead-a",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 1, "away": 1}),
                participants_json=dump_json(
                    {"home": {"name": "SpVgg Alpine Furth"}, "away": {"name": "Magdeburg"}}
                ),
                extra_json=dump_json({"display_eligible": True}),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-lead-b",
                sport_id="football",
                competition_id="germany-2-bundesliga",
                event_family="team_match",
                fingerprint="fp-lead-b",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 1, "away": 1}),
                participants_json=dump_json(
                    {"home": {"name": "Alpine Furth"}, "away": {"name": "1. FC Magdeburg"}}
                ),
                extra_json=dump_json({"display_eligible": True}),
            )
        )
        db.commit()
        collapse_canonical_events(db)
        public = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            competition="germany-2-bundesliga",
            date_from="2026-09-19T00:00:00Z",
            date_to="2026-09-19T23:59:59Z",
        )
        assert len(public) == 1
    finally:
        db.close()


def test_date_only_not_exact_midnight_and_genuine_midnight_kept():
    from collector.timezones import DATE_ONLY, EXACT_TIME, resolve_event_time

    dated = resolve_event_time("2026-09-20", competition_id="albania-superliga", provider="openfootball")
    assert dated.precision == DATE_ONLY
    genuine = resolve_event_time("2026-09-20T00:00:00Z", competition_id="england-premier-league", provider="openligadb")
    assert genuine.precision == EXACT_TIME


def test_normalize_keeps_parenthetical_country_metadata():
    from collector.normalize import normalize_event

    event = normalize_event(
        {
            "home": {"name": "Coastal Club (Uru)"},
            "away": {"name": "Andes Club (Per)"},
            "start_time": "2026-09-18T00:30:00Z",
        },
        sport_id="football",
        competition_id="copa-sudamericana",
    )
    assert event["home"]["name"] == "Coastal Club"
    assert event["home"]["country_id"] == "UY"
    assert event["away"]["name"] == "Andes Club"
    assert event["away"]["country_id"] == "PE"


def test_bundesliga_labels_do_not_cross_division():
    assert label_matches_competition("2. Bundesliga", "germany-2-bundesliga")
    assert not label_matches_competition("2. Bundesliga", "germany-bundesliga")
    assert label_matches_competition("German Bundesliga", "germany-bundesliga")
    assert not label_matches_competition("German Bundesliga", "germany-2-bundesliga")
    assert not label_matches_competition("Bundesliga", "germany-2-bundesliga")


def test_mapping_rejects_independent_source_league_id():
    raw = {
        "source_family": "openligadb",
        "source_competition_id": "bl1",
        "competition": "1. Bundesliga",
        "sport": "football",
        "home": {"name": "Nordstern FC"},
        "away": {"name": "Rheinstadt"},
    }
    ok, resolved = event_accepted_for_mapping(raw, "germany-2-bundesliga")
    assert ok is False
    assert resolved["suggested_competition_id"] == "germany-bundesliga"
    unlabeled = {
        "source_family": "openligadb",
        "sport": "football",
        "home": {"name": "Nordstern FC"},
        "away": {"name": "Rheinstadt"},
    }
    ok_unlabeled, _ = event_accepted_for_mapping(unlabeled, "germany-2-bundesliga")
    assert ok_unlabeled is True


def test_thesportsdb_str_league_not_trusted_against_sibling_mapping():
    raw = {
        "source_family": "thesportsdb",
        "source_competition_id": "4331",
        "competition": "German Bundesliga",
        "sport": "football",
    }
    ok, resolved = event_accepted_for_mapping(raw, "germany-2-bundesliga")
    assert ok is False
    assert resolved["suggested_competition_id"] == "germany-bundesliga"
    ok_right, _ = event_accepted_for_mapping(raw, "germany-bundesliga")
    assert ok_right is True


def test_attribution_corrects_or_quarantines_from_source_evidence():
    from datetime import datetime

    from collector.integrity import apply_competition_attribution
    from collector.models import SportsEvent
    from collector.util import dump_json, load_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 18, 16, 30, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-attr-correct",
                sport_id="football",
                competition_id="germany-2-bundesliga",
                event_family="team_match",
                fingerprint="fp-attr-correct",
                start_time=kickoff,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Nordstern FC"}, "away": {"name": "Rheinstadt"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "openligadb",
                        "source_competition_id": "bl1",
                        "source_competition_name": "1. Bundesliga",
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-attr-keep",
                sport_id="football",
                competition_id="germany-2-bundesliga",
                event_family="team_match",
                fingerprint="fp-attr-keep",
                start_time=kickoff,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Alpine Furth"}, "away": {"name": "Hafenstadt"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "openligadb",
                        "source_competition_name": "2. Bundesliga",
                        "source_competition_id": "bl2",
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-attr-q",
                sport_id="football",
                competition_id="england-premier-league",
                event_family="team_match",
                fingerprint="fp-attr-q",
                start_time=kickoff,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Harbour Town"}, "away": {"name": "Valley United"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "openfootball",
                        "source_competition_name": "KNVB Beker",
                    }
                ),
            )
        )
        db.commit()
        result = apply_competition_attribution(db, live_index={}, fetch_live=False)
        assert result["corrected"] == 1
        assert result["quarantined"] == 1
        corrected = db.query(SportsEvent).filter_by(event_id="ninko-evt-attr-correct").one()
        assert corrected.competition_id == "germany-bundesliga"
        assert corrected.display_eligible is True
        kept = db.query(SportsEvent).filter_by(event_id="ninko-evt-attr-keep").one()
        assert kept.competition_id == "germany-2-bundesliga"
        assert kept.display_eligible is True
        hidden = db.query(SportsEvent).filter_by(event_id="ninko-evt-attr-q").one()
        extra = load_json(hidden.extra_json, {}) or {}
        assert hidden.display_eligible is False
        assert extra.get("competition_attribution") == "quarantined_unproven"
    finally:
        db.close()


def test_owned_family_hidden_cricket_is_recovered():
    from datetime import datetime

    from collector.integrity import apply_competition_attribution
    from collector.models import SportsEvent
    from collector.util import dump_json, load_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        db.query(SportsEvent).filter_by(event_id="ninko-evt-cricsheet-hidden").delete()
        db.commit()
        row = SportsEvent(
            event_id="ninko-evt-cricsheet-hidden",
            sport_id="cricket",
            competition_id="t20-internationals",
            event_family="team_match",
            fingerprint="fp-cricsheet-hidden",
            start_time=datetime(2026, 9, 16, 0, 0, 0),
            display_eligible=False,
            participants_json=dump_json({"home": {"name": "India"}, "away": {"name": "Pakistan"}}),
            extra_json=dump_json(
                {
                    "display_eligible": False,
                    "source_family": "thesportsdb",
                    "source_event_ids": {"cricsheet": "1482210"},
                    "source_competition_name": "ICC Men's T20 World Cup",
                    "innings": [{"label": "India", "runs": 120, "wickets": 4, "overs": 20}],
                }
            ),
        )
        db.add(row)
        db.commit()
        result = apply_competition_attribution(db, live_index={}, fetch_live=False)
        recovered = db.query(SportsEvent).filter_by(event_id="ninko-evt-cricsheet-hidden").one()
        extra = load_json(recovered.extra_json, {}) or {}
        assert result["recovered"] >= 1
        assert recovered.display_eligible is True
        assert extra.get("display_eligible") is True
        assert extra.get("competition_attribution") == "recovered_mapping_owned"
        assert extra["innings"][0]["runs"] == 120
    finally:
        db.query(SportsEvent).filter_by(event_id="ninko-evt-cricsheet-hidden").delete()
        db.commit()
        db.close()



def test_orphan_duplicate_guard_restores_one_trusted_source_native_fixture():
    from datetime import datetime

    from collector.integrity import restore_orphaned_duplicate_football
    from collector.models import SportsEvent
    from collector.util import dump_json, load_json
    from database import SessionLocal

    db = SessionLocal()
    ids = ["ninko-evt-orphan-guard-fotmob", "ninko-evt-orphan-guard-noise"]
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        participants = dump_json({
            "home": {"name": "Guard FAR Rabat"},
            "away": {"name": "Guard Raja Casablanca"},
        })
        db.add(SportsEvent(
            event_id=ids[0],
            sport_id="football",
            competition_id="morocco-botola",
            event_family="team_match",
            fingerprint="fp-orphan-guard-fotmob",
            start_time=datetime(2026, 9, 25, 1, 0, 0),
            display_eligible=False,
            participants_json=participants,
            extra_json=dump_json({
                "display_eligible": False,
                "source_family": "fotmob",
                "source_event_id": "guard-530-1",
                "source_competition_id": "530",
                "resolution_method": "mapping_request_trusted",
                "quality_flags": ["duplicate_or_contaminated"],
            }),
        ))
        db.add(SportsEvent(
            event_id=ids[1],
            sport_id="football",
            competition_id="wrong-clone",
            event_family="team_match",
            fingerprint="fp-orphan-guard-noise",
            start_time=datetime(2026, 9, 25, 1, 0, 0),
            display_eligible=False,
            participants_json=participants,
            extra_json=dump_json({
                "display_eligible": False,
                "source_family": "unknown",
                "quality_flags": ["duplicate_or_contaminated"],
            }),
        ))
        db.commit()

        result = restore_orphaned_duplicate_football(db)
        restored = db.query(SportsEvent).filter_by(event_id=ids[0]).one()
        extra = load_json(restored.extra_json, {}) or {}

        assert result["restored"] >= 1
        assert restored.display_eligible is True
        assert restored.canonical_event_id is None
        assert extra["display_eligible"] is True
        assert "duplicate_or_contaminated" not in (extra.get("quality_flags") or [])
        assert extra["quarantine_disposition"] == "RESTORED_ORPHAN_DUPLICATE"
    finally:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_orphan_duplicate_guard_keeps_real_canonical_loser_hidden():
    from datetime import datetime

    from collector.integrity import restore_orphaned_duplicate_football
    from collector.models import SportsEvent
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    keeper_id = "ninko-evt-orphan-guard-keeper"
    loser_id = "ninko-evt-orphan-guard-loser"
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_([keeper_id, loser_id])).delete(synchronize_session=False)
        participants = dump_json({
            "home": {"name": "Guard Public Home"},
            "away": {"name": "Guard Public Away"},
        })
        db.add(SportsEvent(
            event_id=keeper_id,
            sport_id="football",
            competition_id="morocco-botola",
            event_family="team_match",
            fingerprint="fp-orphan-guard-keeper",
            start_time=datetime(2026, 9, 25, 2, 0, 0),
            display_eligible=True,
            participants_json=participants,
            extra_json=dump_json({"display_eligible": True, "source_family": "fotmob"}),
        ))
        db.add(SportsEvent(
            event_id=loser_id,
            sport_id="football",
            competition_id="morocco-botola",
            event_family="team_match",
            fingerprint="fp-orphan-guard-loser",
            start_time=datetime(2026, 9, 25, 2, 0, 0),
            display_eligible=False,
            canonical_event_id=keeper_id,
            participants_json=participants,
            extra_json=dump_json({
                "display_eligible": False,
                "canonical_event_id": keeper_id,
                "source_family": "fotmob",
                "source_event_id": "guard-loser",
                "source_competition_id": "530",
                "resolution_method": "mapping_request_trusted",
                "quality_flags": ["duplicate_or_contaminated"],
            }),
        ))
        db.commit()

        result = restore_orphaned_duplicate_football(db)
        loser = db.query(SportsEvent).filter_by(event_id=loser_id).one()

        assert result["restored"] == 0
        assert loser.display_eligible is False
        assert loser.canonical_event_id == keeper_id
    finally:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_([keeper_id, loser_id])).delete(synchronize_session=False)
        db.commit()
        db.close()



def test_backfill_duplicate_cluster_always_keeps_one_public_candidate():
    from datetime import datetime

    from collector.integrity import plan_backfill
    from collector.models import SportsEvent
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    ids = ["ninko-evt-never-zero-a", "ninko-evt-never-zero-b"]
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        participants = dump_json({
            "home": {"name": "Never Zero Home"},
            "away": {"name": "Never Zero Away"},
        })
        db.add(SportsEvent(
            event_id=ids[0],
            sport_id="football",
            competition_id="never-zero-comp-a",
            event_family="team_match",
            fingerprint="fp-never-zero-a",
            start_time=datetime(2026, 9, 25, 3, 0, 0),
            display_eligible=True,
            participants_json=participants,
            extra_json=dump_json({
                "display_eligible": True,
                "source_family": "fotmob",
                "source_event_id": "nz-a",
                "source_competition_id": "530",
            }),
        ))
        db.add(SportsEvent(
            event_id=ids[1],
            sport_id="football",
            competition_id="never-zero-comp-b",
            event_family="team_match",
            fingerprint="fp-never-zero-b",
            start_time=datetime(2026, 9, 25, 3, 0, 0),
            display_eligible=True,
            participants_json=participants,
            extra_json=dump_json({
                "display_eligible": True,
                "source_family": "unknown",
            }),
        ))
        db.commit()

        plan = plan_backfill(db)
        quarantined = set(plan["quarantine"]) & set(ids)

        assert len(quarantined) == 1
        assert ids[0] not in quarantined
    finally:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()
