from collector.cyberscore_dota_asset_backfill import _key, _page_assets


def test_cyberscore_dota_page_assets_extract_tournament_and_team_logos():
    html = """
    <img src="/media/tournament.png" alt="BB Streamers Battle 15 - tournament logo">
    <img data-src="/media/avice.png" alt="Team Avice - team logo">
    <img src="https://cdn.example/gpk.png" alt="Team GPK - team logo">
    """
    assets = _page_assets(html, "https://cyberscore.live/en/tournaments/example/")
    assert assets["tournament_name"] == "BB Streamers Battle 15"
    assert assets["tournament_logo"] == "https://cyberscore.live/media/tournament.png"
    assert assets["teams"][_key("avice Team")]["logo"] == "https://cyberscore.live/media/avice.png"
    assert assets["teams"][_key("gpk Team")]["logo"] == "https://cdn.example/gpk.png"


def test_cyberscore_dota_page_assets_drop_conflicting_team_identity():
    html = """
    <img src="/media/ybn-one.png" alt="YBN Team - team logo">
    <img src="/media/ybn-two.png" alt="Team YBN - team logo">
    """
    assets = _page_assets(html, "https://cyberscore.live/")
    assert _key("YBN Team") == _key("Team YBN") == "ybn"
    assert "ybn" not in assets["teams"]
