import inspect
from collector.competition_identity import source_native_public_competition_id
from collector.volleyballworld_breadth import (
    _competition_id,
    _stable_event,
    discover_competition_slugs,
)


def test_volleyballworld_sitemap_discovers_competition_slugs():
    xml = """
    <url><loc>https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/schedule/26487/</loc></url>
    <url><loc>https://en.volleyballworld.com/volleyball/competitions/avc-men-nations-cup/news/foo</loc></url>
    <url><loc>https://en.volleyballworld.com/beach-volleyball/competitions/beach-pro-tour/</loc></url>
    """
    slugs = discover_competition_slugs(xml)
    assert slugs[0] == "volleyball-nations-league"
    assert "avc-men-nations-cup" in slugs
    assert "beach-pro-tour" not in slugs


def test_volleyballworld_event_keeps_set_score_and_stable_identity():
    raw = {
        "id": "/volleyball/competitions/volleyball-nations-league/schedule/123/",
        "home": {"name": "Serbia"},
        "away": {"name": "Italy"},
        "status": "finished",
        "score": {"home": 3, "away": 2},
        "start_time": "2026-07-18T18:00:00Z",
        "periods": [
            {"label": "1", "home": 25, "away": 22},
            {"label": "2", "home": 23, "away": 25},
        ],
    }
    cid = _competition_id("volleyball-nations-league")
    event = _stable_event(
        raw,
        competition_id=cid,
        competition_name="Volleyball Nations League 2026",
        slug="volleyball-nations-league",
    )
    assert event["competition_key"] == "volleyball-vw-volleyball-nations-league"
    assert event["source_family"] == "volleyballworld"
    assert event["score"] == {"home": 3, "away": 2}
    assert event["periods"][0]["home"] == 25
    assert event["source_event_ids"]["volleyballworld"]


def test_volleyballworld_source_native_prefix_is_validated():
    accepted = source_native_public_competition_id(
        stored_competition_id="volleyball-vw-avc-men-nations-cup",
        source_competition_name="AVC Men's Cup",
        sport_id="volleyball",
        source_family="volleyballworld",
    )
    rejected = source_native_public_competition_id(
        stored_competition_id="volleyball-random",
        source_competition_name="Random",
        sport_id="volleyball",
        source_family="volleyballworld",
    )
    assert accepted == "volleyball-vw-avc-men-nations-cup"
    assert rejected is None



def test_breadth_does_not_require_year_token_on_landing_page():
    source = inspect.getsource(run_breadth_ingest)
    assert 'if "2026" not in landing.payload' not in source
    assert "eligible_rows = [event for event in rows if _in_window(event, now=now)]" in source
