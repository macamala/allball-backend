from collector.source_family_closeout import (
    REGISTRY_MIGRATIONS,
    ingestion_allowed,
    parse_ttbl_schedule,
    parse_world_aquatics_discipline,
    provider_independence,
)
from collector.verification_ledger import counters_are_derived, legacy_overlay_counts, recompute_ledger


def test_legacy_overlay_is_not_the_ledger():
    legacy = legacy_overlay_counts()
    ledger = recompute_ledger({})
    assert ledger["competition_count"] == 180
    assert ledger["totals"]["production_proven_competitions"] == 0
    assert legacy["production_verified"] != ledger["totals"]["production_proven_competitions"]
    assert counters_are_derived(ledger["totals"], ledger["rows"])


def test_proven_requires_persisted_event_not_a_flag():
    ledger = recompute_ledger(
        {
            "wa-calendar": {
                "event": {
                    "id": "ninko-evt-3d60d0fed4a0089e1ca9",
                    "classification": [{"athlete": "Kenneth BEDNAREK"}] * 8,
                    "coverage": "official_result",
                    "source_event_id": "7212925:10229630",
                },
                "standings_applicable": False,
            }
        }
    )
    row = next(item for item in ledger["rows"] if item["competition_key"] == "wa-calendar")
    assert row["production_event_status"] == "PROVEN"
    assert row["classification_status"] == "FULL"
    assert row["standings_status"] == "NOT_APPLICABLE"
    diff = next(item for item in ledger["legacy_differences"] if item["competition"] == "wa-calendar")
    assert diff["old_status"] == "not_in_legacy_overlay"
    assert diff["proof_canonical_id"] == "ninko-evt-3d60d0fed4a0089e1ca9"


def test_same_origin_and_terms_are_separate_from_proof():
    assert provider_independence("hrnsw-web", "harness.org.au") == "SAME_ORIGIN"
    assert provider_independence("ttbl-web", "openligadb") == "A_B_INDEPENDENT"
    assert ingestion_allowed("kpga-web") is False
    assert ingestion_allowed("click-tt-remix") is False
    assert ingestion_allowed("ttbl-web") is True
    keys = {row["old_key"] for row in REGISTRY_MIGRATIONS}
    assert "futsalplanet-leagues-cups" in keys
    assert "national-and-club" in keys
    assert "title-fights" in keys


def test_wec_prologue_sessions_count_as_official_summaries():
    def session(event_id: str, label: str) -> dict:
        return {
            "id": event_id,
            "home": {"name": f"{label} - Official Prologue - IMOLA"},
            "classification": [
                {"class": "Hypercar", "position": 1, "name": "Driver", "time": "1m30.0s", "time_kind": "absolute"}
            ]
            * 10,
        }

    ledger = recompute_ledger(
        {
            "wec": {
                "event": session("ninko-evt-am", "MORNING SESSION"),
                "summary_events": [
                    session("ninko-evt-am", "MORNING SESSION"),
                    session("ninko-evt-pm", "AFTERNOON SESSION"),
                ],
                "standings_applicable": True,
                "standings": [{"team": "A"}, {"team": "B"}],
            }
        }
    )
    row = next(item for item in ledger["rows"] if item["competition_key"] == "wec")
    assert row["classification_status"] == "OFFICIAL_SUMMARY"
    assert row["classification_status"] != "FULL"
    assert ledger["totals"]["classification_official_summary"] >= 2


def test_title_fights_is_model_scope_not_a_silent_gap():
    ledger = recompute_ledger({})
    row = next(item for item in ledger["rows"] if item["competition_key"] == "title-fights")
    assert row["blocker_code"] == "MODEL_SCOPE"
    assert row["production_event_status"] != "PROVEN"
    assert "sanctioning" in row["blocker_detail"].lower()
    assert "ufc" in row["blocker_detail"].lower()


def test_ttbl_and_world_aquatics_parsers_keep_structure():
    parsed = parse_ttbl_schedule(
        {
            "matches": [
                {
                    "id": "0c9590e2-c913-4572-b526-0ef82d28443d",
                    "timeStamp": 1786896000,
                    "matchState": "Finished",
                    "homeGames": 0,
                    "awayGames": 3,
                    "homeSets": 4,
                    "awaySets": 9,
                    "homeTeam": {"seasonTeam": {"name": "BV Borussia 09 Dortmund"}},
                    "awayTeam": {"seasonTeam": {"name": "1. FC Saarbrücken-TT"}},
                }
            ],
            "tableTeams": [
                {
                    "rank": 1,
                    "matchCount": 2,
                    "matchWins": 2,
                    "matchLosses": 0,
                    "plusPoints": 4,
                    "seasonTeam": {"name": "Borussia Düsseldorf"},
                }
            ],
            "selectedMatch": {
                "id": "0c9590e2-c913-4572-b526-0ef82d28443d",
                "games": [
                    {"index": 1, "homeSets": 2, "awaySets": 3, "set1HomeScore": 11, "set1AwayScore": 5, "winnerSide": "Away"}
                ],
            },
        }
    )
    assert parsed["events"][0]["score"]["home"] == 0
    assert parsed["events"][0]["score"]["away"] == 3
    assert parsed["events"][0]["individual_matches"][0]["sets"] == ["11-5"]
    assert parsed["standings"][0]["team"] == "Borussia Düsseldorf"
    assert parsed["standings"][0]["draws"] is None

    aqua = parse_world_aquatics_discipline(
        {
            "TimingAndScoringPartnerName": "Microplus",
            "Heats": [
                {
                    "PhaseName": "Finals",
                    "Name": "Men's Gold Medal Match",
                    "ResultStatus": "OFFICIAL",
                    "Results": [
                        {
                            "MatchNo": 80,
                            "Date": "2026-04-13T19:30:00",
                            "TeamHomeName": "Montenegro",
                            "TeamAwayName": "Georgia",
                            "FinalScoreHome": 19,
                            "FinalScoreAway": 17,
                            "Q1ScoreHome": 6,
                            "Q2ScoreHome": 2,
                            "Q3ScoreHome": 4,
                            "Q4ScoreHome": 7,
                            "Q1ScoreAway": 4,
                            "Q2ScoreAway": 6,
                            "Q3ScoreAway": 3,
                            "Q4ScoreAway": 4,
                        }
                    ],
                },
                {
                    "PhaseName": "Final Standings",
                    "Results": [
                        {"TeamMembers": [{"Nationality": "Montenegro"}], "Rank": 1, "MatchesPlayed": None},
                        {"TeamMembers": [{"Nationality": "Georgia"}], "Rank": 2},
                    ],
                },
            ],
        }
    )
    assert aqua["events"][0]["quarters"]["home"] == [6, 2, 4, 7]
    assert aqua["events"][0]["source_event_id"] == "wa:5135:80"
    assert aqua["standings"][0]["played"] is None
    assert aqua["standings"][0]["position"] == 1
