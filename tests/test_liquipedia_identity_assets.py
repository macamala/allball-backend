from collector.html_parse import parse_liquipedia_html


def test_liquipedia_parser_keeps_team_logos():
    html = """
    <div class="match-info">
      <span class="team-template-team-standard">
        <span class="team-template-image-icon"><img src="/commons/images/a/aa/Alpha.png"></span>
        <span class="team-template-text"><a href="/alpha">Alpha</a></span>
      </span>
      <span class="match-info-header-scoreholder-score">2</span>
      <span class="match-info-header-scoreholder-score">1</span>
      <span class="team-template-team-standard">
        <span class="team-template-image-icon"><img data-src="//liquipedia.net/commons/images/b/bb/Beta.png"></span>
        <span class="team-template-text"><a href="/beta">Beta</a></span>
      </span>
    </div>
    """
    rows = parse_liquipedia_html(html)
    assert len(rows) == 1
    assert rows[0]["home"]["name"] == "Alpha"
    assert rows[0]["away"]["name"] == "Beta"
    assert rows[0]["home"]["logo"] == "https://liquipedia.net/commons/images/a/aa/Alpha.png"
    assert rows[0]["away"]["logo"] == "https://liquipedia.net/commons/images/b/bb/Beta.png"
