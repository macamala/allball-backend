from types import SimpleNamespace

from collector.dirty import event_unchanged, observation_signature
from collector.breadth_audit import _visible_identity_requirement
from collector.opendota_asset_backfill import _fill_side as fill_opendota_side, _parse_catalog as parse_opendota_catalog
from collector.adapters_opendota import _event as opendota_event
from collector.verified_participant_assets import verified_competition_logo
from collector.merge import merge_event_fields
from collector.participant_text import participant_payload
from collector.util import dump_json


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



def test_unchanged_event_is_reopened_for_missing_identity_assets():
    incoming = _event(
        home={"name": "Alpha FC", "logo": "https://cdn.example/alpha.svg"},
        competition_logo="https://cdn.example/league.svg",
        start_time="2026-09-24T10:00:00Z",
    )
    existing = SimpleNamespace(
        extra_json=dump_json({"obs_signature": observation_signature(incoming)}),
        participants_json=dump_json({
            "home": {"name": "Alpha FC"},
            "away": {"name": "Beta FC"},
            "participant_a": {"name": "Alpha FC"},
            "participant_b": {"name": "Beta FC"},
        }),
        start_time=object(),
    )
    assert event_unchanged(existing, incoming) is False



def test_visible_asset_audit_requires_logos_only_for_team_style_events():
    assert _visible_identity_requirement({"event_family": "team_match", "sport": "football"}) == "logo"
    assert _visible_identity_requirement({"event_family": "esports_match", "sport": "dota-2"}) == "logo"
    assert _visible_identity_requirement(
        {"event_family": "team_match", "sport": "volleyball", "competition_key": "cev-eurovolley-men"}
    ) == "country_or_logo"


def test_visible_asset_audit_uses_country_for_individual_head_to_head():
    assert _visible_identity_requirement({"event_family": "individual_match", "sport": "tennis"}) == "country"
    assert _visible_identity_requirement({"event_family": "combat", "sport": "mma"}) == "country"


def test_visible_asset_audit_does_not_invent_team_logo_gaps_for_meta_events():
    assert _visible_identity_requirement({"event_family": "racing", "sport": "greyhound-racing"}) == "none"
    assert _visible_identity_requirement({"event_family": "tournament", "sport": "golf"}) == "none"
    assert _visible_identity_requirement({"event_family": "motorsport_race", "sport": "motorsport"}) == "none"



def test_opendota_catalog_uses_exact_team_ids_and_logo_urls():
    catalog = parse_opendota_catalog([
        {
            "team_id": 8261500,
            "name": "Xtreme Gaming",
            "tag": "XG",
            "logo_url": "https://cdn.example/xg.png",
        },
        {
            "team_id": 0,
            "name": "Unknown",
            "logo_url": "",
        },
    ])
    assert catalog["8261500"]["name"] == "Xtreme Gaming"
    assert catalog["8261500"]["logo"] == "https://cdn.example/xg.png"
    assert "0" not in catalog


def test_opendota_logo_fill_never_overwrites_or_name_matches():
    asset = {
        "id": "8261500",
        "name": "Xtreme Gaming",
        "logo": "https://cdn.example/xg.png",
    }
    filled, changed = fill_opendota_side({"id": "8261500", "name": "Xtreme Gaming"}, asset)
    assert changed is True
    assert filled["logo"] == asset["logo"]

    existing, changed = fill_opendota_side(
        {"id": "8261500", "name": "Xtreme Gaming", "logo": "https://cdn.example/original.png"},
        asset,
    )
    assert changed is False
    assert existing["logo"] == "https://cdn.example/original.png"

    wrong_id, changed = fill_opendota_side({"id": "123", "name": "Xtreme Gaming"}, asset)
    assert changed is False
    assert not wrong_id.get("logo")



def test_verified_wta_competition_artwork_is_available_without_affecting_football_map():
    logo = verified_competition_logo("tennis", "wta-tour", {})
    assert logo and "wtatennis.com" in logo
    assert verified_competition_logo("tennis", "unknown-tour", {}) is None


def test_verified_hrnsw_competition_artwork_uses_official_host():
    logo = verified_competition_logo("harness-racing", "nsw-hrnsw-meetings", {})
    assert logo and "hrnsw.com.au" in logo


def test_opendota_event_preserves_real_league_name_on_stable_professional_key():
    event = opendota_event(
        {
            "match_id": 123,
            "radiant_team_id": 1,
            "radiant_name": "Alpha",
            "dire_team_id": 2,
            "dire_name": "Beta",
            "leagueid": 999,
            "league_name": "BetBoom Streamers Battle 15",
            "start_time": 1790265600,
            "duration": 1800,
        },
        "professional",
    )
    assert event["competition_key"] == "professional"
    assert event["competition"] == "Dota 2 Professional"
    assert event["source_competition_name"] == "BetBoom Streamers Battle 15"
    assert event["source_competition_id"] == "999"
    assert event["extra"]["source_competition_name"] == "BetBoom Streamers Battle 15"
