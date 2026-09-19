"""Sports Registry foundation: stable IDs, compatibility, honest empty data."""

from fastapi.testclient import TestClient

from app import app
from sports_registry.compatibility import can_competition_belong_to_sport, compatible_competition
from sports_registry.competitions import resolve_competition_alias
from sports_registry.event_models import event_family_for_sport
from sports_registry.geography import get_geo, region_for_country
from sports_registry.providers import list_providers
from sports_registry.router import get_sports_data_provider, select_provider
from sports_registry.schema import EVENT_MODELS, REGISTRY_VERSION
from sports_registry.sports import (
    SPORTS,
    get_sport,
    prediction_market,
    validate_catalog,
)
from sports_provider import normalize_legacy_match
from collector.provider import NinkoCollectedSportsDataProvider


REQUIRED_SPORTS = {
    "football",
    "basketball",
    "tennis",
    "motorsport",
    "american-football",
    "ice-hockey",
    "baseball",
    "rugby",
    "rugby-league",
    "cricket",
    "volleyball",
    "handball",
    "golf",
    "boxing",
    "mma",
    "cycling",
    "snooker",
    "darts",
    "table-tennis",
    "badminton",
    "futsal",
    "water-polo",
    "field-hockey",
    "athletics",
    "swimming",
    "winter-sports",
    "australian-rules",
    "netball",
    "lacrosse",
    "horse-racing",
    "greyhound-racing",
    "harness-racing",
    "esports",
    "ea-sports-fc",
    "counter-strike",
    "league-of-legends",
    "dota-2",
    "valorant",
    "call-of-duty",
    "overwatch",
    "rocket-league",
}


def test_registry_ids_and_slugs_are_stable_and_unique():
    assert validate_catalog() == []
    slugs = [row["slug"] for row in SPORTS]
    ids = [row["id"] for row in SPORTS]
    assert len(slugs) == len(set(slugs))
    assert len(ids) == len(set(ids))
    assert REQUIRED_SPORTS.issubset(set(slugs))
    football = get_sport("football")
    assert football["id"] == "football"
    assert football["slug"] == "football"
    assert get_sport("rugby-union")["id"] == "rugby"
    assert football["path"] == "/football"
    assert get_sport("horse-racing")["path"] == "/sports/horse-racing"
    assert get_sport("golf")["path"] == "/golf"


def test_event_models_are_valid():
    for row in SPORTS:
        assert row["event_model"] in EVENT_MODELS
    assert event_family_for_sport("football") == "team_match"
    assert event_family_for_sport("tennis") == "individual_match"
    assert event_family_for_sport("boxing") == "combat"
    assert event_family_for_sport("motorsport") == "motorsport_race"
    assert event_family_for_sport("horse-racing") == "racing"
    assert event_family_for_sport("golf") == "tournament"
    assert event_family_for_sport("counter-strike") == "esports_match"


def test_countries_and_regions_resolve():
    serbia = get_geo("serbia")
    assert serbia is not None
    assert region_for_country("serbia") == "europe"
    assert get_geo("europe")["kind"] == "region"
    assert get_geo("world")["id"] == "world"
    assert get_geo("USA")["iso_code"] == "US"
    assert get_geo("international")["kind"] == "region"


def test_competitions_cannot_belong_to_incompatible_sports():
    assert compatible_competition("football", "uefa-champions-league") == "uefa-champions-league"
    assert compatible_competition("tennis", "uefa-champions-league") is None
    assert compatible_competition("football", "nba") is None
    assert compatible_competition("motorsport", "formula-2") == "formula-2"
    assert compatible_competition("football", "formula-2") is None
    assert can_competition_belong_to_sport("wimbledon", "tennis") is True
    assert can_competition_belong_to_sport("wimbledon", "football") is False


def test_aliases_resolve_to_canonical_competition():
    assert resolve_competition_alias("UCL") == "uefa-champions-league"
    assert resolve_competition_alias("Champions League") == "uefa-champions-league"
    assert resolve_competition_alias("French Open") == "roland-garros"
    assert resolve_competition_alias("Roland Garros") == "roland-garros"
    assert resolve_competition_alias("Wimbledon", sport_id="tennis") == "wimbledon"
    assert resolve_competition_alias("Wimbledon", sport_id="football") is None
    assert resolve_competition_alias("Australian Open", sport_id="golf") is None
    assert resolve_competition_alias("Australian Open", sport_id="tennis") == "australian-open"


def test_predictions_disabled_for_unsupported_sports():
    assert prediction_market("football") == "1x2"
    assert prediction_market("basketball") == "winner"
    assert prediction_market("tennis") == "winner"
    assert prediction_market("motorsport") is None
    assert prediction_market("horse-racing") is None
    assert prediction_market("mma") is None
    assert get_sport("horse-racing")["supports_predictions"] is False
    assert get_sport("esports")["supports_predictions"] is False


def test_no_provider_returns_honest_empty_registry_and_sports_data():
    assert list_providers() == []
    assert select_provider("live_scores") is None
    provider = get_sports_data_provider()
    assert isinstance(provider, NinkoCollectedSportsDataProvider)
    assert provider.status()["connected"] is False
    assert provider.get_events() == []
    with TestClient(app) as client:
        registry = client.get("/registry/sports").json()
        assert registry["version"] == REGISTRY_VERSION
        slugs = {row["slug"] for row in registry["sports"]}
        assert "golf" in slugs
        assert "horse-racing" in slugs
        assert "esports" in slugs
        assert registry["provider"]["connected"] is False
        geo = client.get("/registry/geography").json()
        assert any(item["id"] == "europe" for item in geo["places"])
        comps = client.get("/registry/competitions?sport=football").json()
        assert any(item["competition_id"] == "uefa-champions-league" for item in comps["competitions"])
        ucl = next(item for item in comps["competitions"] if item["competition_id"] == "uefa-champions-league")
        assert ucl["region_id"] in {"europe", "international"}
        assert ucl["country_id"] in {None, ""}
        serbia = next(item for item in comps["competitions"] if item["competition_id"] == "serbia-superliga")
        assert serbia["country_id"] in {"rs", "serbia"}
        assert serbia["region_id"] == "europe"
        providers = client.get("/registry/providers").json()
        assert providers["connected"] is False
        assert "Powered by" not in str(providers)
        taxonomy = client.get("/meta/taxonomy").json()
        tax_slugs = {row["sport"] for row in taxonomy["sports"]}
        assert "golf" in tax_slugs
        assert "horse-racing" in tax_slugs
        scores = client.get("/sports-data/scores").json()
        assert scores["connected"] is False
        assert scores["events"] == []
        preds = client.get("/predictions?sport=horse-racing").json()
        assert preds["items"] == []
        assert preds.get("market") in {None, ""}
        sitemap = client.get("/sitemap.xml").text
        assert "/sports/horse-racing" in sitemap
        assert "/golf" in sitemap
        assert "/football" in sitemap
