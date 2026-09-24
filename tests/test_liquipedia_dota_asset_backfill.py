from collector.liquipedia_dota_asset_backfill import _catalog_from_html, _key


def test_liquipedia_dota_catalog_keeps_exact_team_artwork():
    html = """
    <div class="match-info">
      <span class="team-template-team-standard">
        <span class="team-template-image-icon"><img src="/commons/images/a/aa/Avice.png"></span>
        <span class="team-template-text"><a href="/dota2/Avice_Team">avice Team</a></span>
      </span>
      <span class="match-info-header-scoreholder-score">2</span>
      <span class="match-info-header-scoreholder-score">1</span>
      <span class="team-template-team-standard">
        <span class="team-template-image-icon"><img data-src="//liquipedia.net/commons/images/b/bb/Gpk.png"></span>
        <span class="team-template-text"><a href="/dota2/Gpk_Team">gpk Team</a></span>
      </span>
    </div>
    """
    catalog = _catalog_from_html(html)
    assert _key("Team avice") == _key("avice Team") == "avice"
    assert _key("Team GPK") == _key("gpk Team") == "gpk"
    assert catalog["avice"]["logo"] == "https://liquipedia.net/commons/images/a/aa/Avice.png"
    assert catalog["gpk"]["logo"] == "https://liquipedia.net/commons/images/b/bb/Gpk.png"


def test_liquipedia_dota_catalog_drops_conflicting_same_identity():
    html = """
    <div class="match-info">
      <span class="team-template-image-icon"><img src="/commons/images/a/aa/Ybn1.png"></span>
      <span class="team-template-text"><a>YBN Team</a></span>
      <span class="team-template-image-icon"><img src="/commons/images/a/aa/Opponent.png"></span>
      <span class="team-template-text"><a>Opponent Team</a></span>
    </div>
    <div class="match-info">
      <span class="team-template-image-icon"><img src="/commons/images/b/bb/Ybn2.png"></span>
      <span class="team-template-text"><a>Team YBN</a></span>
      <span class="team-template-image-icon"><img src="/commons/images/b/bb/Other.png"></span>
      <span class="team-template-text"><a>Other Team</a></span>
    </div>
    """
    catalog = _catalog_from_html(html)
    assert "ybn" not in catalog
