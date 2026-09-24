from collector.merge import merge_event_fields
from collector.participant_text import participant_payload


def _event(home=None, away=None, **extra):
    return {
        "sport": "football",
        "status": "scheduled",
        "score": {},
        "home": home or {"name": "Alpha FC"},
        "away": away or {"name": "Beta FC"},
        **extra,
    }


def test_participant_payload_accepts_common_logo_aliases():
    row = participant_payload(
        {"name": "Alpha FC", "teamLogo": "https://cdn.example/alpha.svg"},
        "home",
        sport="football",
    )
    assert row["logo"] == "https://cdn.example/alpha.svg"


def test_higher_priority_source_does_not_erase_existing_team_logo():
    current = _event(home={"name": "Alpha FC", "logo": "https://cdn.example/alpha.svg"})
    incoming = _event(home={"name": "Alpha FC"})
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=True,
        incoming_source_id="new-source",
    )
    assert merged["home"]["logo"] == "https://cdn.example/alpha.svg"


def test_lower_priority_source_can_fill_missing_team_logo():
    current = _event(home={"name": "Alpha FC"})
    incoming = _event(home={"name": "Alpha FC", "crest": "https://cdn.example/alpha.svg"})
    # normalize participant aliases before canonical merge, as the collector does.
    incoming["home"] = participant_payload(incoming["home"], "home", sport="football")
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=False,
        incoming_source_id="asset-source",
    )
    assert merged["home"]["logo"] == "https://cdn.example/alpha.svg"


def test_competition_logo_fills_blank_and_survives_failover():
    current = _event(competition_logo="https://cdn.example/league.svg")
    incoming = _event()
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=True,
        incoming_source_id="score-source",
    )
    assert merged["competition_logo"] == "https://cdn.example/league.svg"

    current_without = _event()
    incoming_with = _event(competition_logo="https://cdn.example/league.svg")
    filled = merge_event_fields(
        current_without,
        incoming_with,
        incoming_is_higher_priority=False,
        incoming_source_id="asset-source",
    )
    assert filled["competition_logo"] == "https://cdn.example/league.svg"
