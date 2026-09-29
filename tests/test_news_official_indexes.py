import bot.news_official_indexes as idx


def test_same_host_and_locale_normalization():
    valorant=next(row for row in idx.HTML_INDEXES if row['id']=='valorant-esports')
    assert idx._same_host_url(
        valorant['url'], '/news/champions-test', valorant['host'], valorant
    ) == 'https://valorantesports.com/en-US/news/champions-test'
    assert idx._same_host_url(
        valorant['url'], 'https://evil.example/news/champions-test', valorant['host'], valorant
    ) is None

    rocket=next(row for row in idx.HTML_INDEXES if row['id']=='rocket-league-competitive')
    assert idx._same_host_url(
        rocket['url'], '/news/tag/competitive', rocket['host'], rocket
    ) is None


def test_anchor_candidates_are_bounded_and_keyword_filtered(monkeypatch):
    html=b'''<html><body>
      <a href="/en-us/news/24246297/owcs-2026-season/">OWCS 2026 Season Details</a>
      <a href="/en-us/news/patch-notes/">Retail Patch Notes</a>
      <a href="https://evil.example/en-us/news/x">OWCS external</a>
    </body></html>'''
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: html)
    cfg=next(row for row in idx.HTML_INDEXES if row['id']=='overwatch-esports')
    rows=idx._anchor_candidates(cfg)
    assert rows == [(
        'https://overwatch.blizzard.com/en-us/news/24246297/owcs-2026-season/',
        'OWCS 2026 Season Details',
    )]


def test_uefa_sitemap_selects_only_futsal(monkeypatch):
    xml=b'''<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url><loc>https://www.uefa.com/uefafutsalchampionsleague/news/example/</loc>
        <news:news><news:title>UEFA Futsal Champions League main round</news:title></news:news></url>
      <url><loc>https://www.uefa.com/uefachampionsleague/news/football/</loc>
        <news:news><news:title>Champions League football story</news:title></news:news></url>
    </urlset>'''
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: xml)
    cfg=next(row for row in idx.SITEMAPS if row['id']=='uefa-futsal')
    rows=idx._sitemap_candidates(cfg)
    assert len(rows)==1
    assert 'uefafutsalchampionsleague' in rows[0][0]
    assert 'Futsal' in rows[0][1]


def test_hydrate_requires_explicit_timestamp_and_article_prose(monkeypatch):
    cfg={
        'id':'fixture','sport':'handball','publisher':'IHF','url':'https://www.ihf.info/media-center/news',
        'host':'www.ihf.info','paths':('/media-center/news/',),
    }
    body=' '.join(['Handball teams prepared for the international championship with confirmed event details.']*12)
    html=f'''<html><head>
      <meta property="og:title" content="International handball championship update">
      <meta property="og:image" content="https://www.ihf.info/photo.jpg">
      <meta property="article:published_time" content="2026-09-26T12:00:00+00:00">
    </head><body><main><p>{body}</p></main></body></html>'''.encode()
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: html)
    monkeypatch.setattr(idx, 'news_freshness_reason', lambda stamp, now: None)
    item=idx._hydrate(cfg, 'https://www.ihf.info/media-center/news/test-story', 'fallback')
    assert item
    assert item['feed']['sport']=='handball'
    assert item['published_at'].tzinfo is not None
    assert 'international championship' in item['_extracted']

    no_date=html.replace(
        b'<meta property="article:published_time" content="2026-09-26T12:00:00+00:00">', b''
    )
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: no_date)
    assert idx._hydrate(cfg, 'https://www.ihf.info/media-center/news/test-story-2', 'fallback') is None


def test_official_index_catalog_covers_target_free_sources():
    sports={row['sport'] for row in idx.HTML_INDEXES} | {row['sport'] for row in idx.SITEMAPS}
    assert {
        'handball','futsal','valorant','league-of-legends','call-of-duty',
        'overwatch','rocket-league','athletics','counter-strike','netball',
        'table-tennis','water-polo','field-hockey','snooker'
    } <= sports


def test_embedded_app_state_links_are_discovered(monkeypatch):
    html=b'''<html><script>
      window.__STATE__={"url":"/en-us/news/24246297/owcs-2026-season/"};
    </script></html>'''
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: html)
    cfg=next(row for row in idx.HTML_INDEXES if row['id']=='overwatch-esports')
    rows=idx._anchor_candidates(cfg)
    assert rows == [(
        'https://overwatch.blizzard.com/en-us/news/24246297/owcs-2026-season/',
        '',
    )]


def test_hydrate_only_keyword_source_allows_generic_anchor_then_filters_body(monkeypatch):
    cfg=next(row for row in idx.HTML_INDEXES if row['id']=='world-aquatics-water-polo')
    index_html=b'<a href="/news/4580591/pathway-to-la28">Pathway to LA28 revealed</a>'
    monkeypatch.setattr(idx,'read_news_feed',lambda url:index_html)
    assert idx._anchor_candidates(cfg)==[(
        'https://www.worldaquatics.com/news/4580591/pathway-to-la28',
        'Pathway to LA28 revealed',
    )]


def test_new_gap_sources_are_article_path_scoped():
    by_id={row['id']:row for row in idx.HTML_INDEXES}
    assert by_id['ittf-table-tennis-news']['paths']==('/2026/',)
    assert by_id['world-aquatics-water-polo']['paths']==('/news/',)
    assert by_id['fih-field-hockey-news']['paths']==('/news/',)
    assert by_id['wst-snooker-news']['paths']==('/news/',)


def test_unusable_primary_indexes_have_active_fallbacks():
    by_id={row['id']:row for row in idx.HTML_INDEXES}
    assert by_id['rocket-league-competitive'].get('enabled') is False
    assert by_id['ittf-table-tennis-news'].get('enabled') is False
    assert by_id['fih-field-hockey-news'].get('enabled') is False
    assert by_id['fifa-futsal-news'].get('enabled') is False

    assert by_id['rocket-league-blast-partner'].get('enabled', True) is True
    assert by_id['rocket-league-blast-partner']['max_age_hours'] == 168
    assert by_id['hockey-australia-news'].get('enabled', True) is True
    assert by_id['hockey-australia-news']['sport'] == 'field-hockey'


def test_disabled_html_indexes_are_not_fetched(monkeypatch):
    calls=[]
    monkeypatch.setattr(idx, '_anchor_candidates', lambda cfg: calls.append(cfg['id']) or [])
    monkeypatch.setattr(idx, '_sitemap_candidates', lambda cfg, **kwargs: [])
    idx.fetch_official_index_entries(1)
    assert 'rocket-league-competitive' not in calls
    assert 'ittf-table-tennis-news' not in calls
    assert 'fih-field-hockey-news' not in calls
    assert 'fifa-futsal-news' not in calls
    assert 'rocket-league-blast-partner' in calls
    assert 'hockey-australia-news' in calls


def test_ihf_uses_direct_news_index():
    from bot.news_official_indexes import HTML_INDEXES
    ihf=next(row for row in HTML_INDEXES if row["id"]=="ihf-handball")
    assert ihf["url"]=="https://www.ihf.info/media-center/news"
    assert ihf["paths"]==("/media-center/news/",)


def test_ihf_explicit_timestamp_and_relative_image_are_hydrated(monkeypatch):
    cfg=next(row for row in idx.HTML_INDEXES if row["id"]=="ihf-handball")
    body=" ".join([
        "Barcelona and Zamalek played at the IHF Men's Club World Championship with confirmed match details."
    ]*12)
    html=f'''<html><head>
      <meta property="og:title" content="Barcelona secure finals berth">
      <meta property="article:published_time" content="2026-09-27T00:00:00Z">
      <meta property="og:image" content="/sites/default/files/handball-photo.jpg">
    </head><body><div>27 Sep. 2026</div><main><p>{body}</p></main></body></html>'''.encode()
    monkeypatch.setattr(idx, "read_news_feed", lambda url: html)
    monkeypatch.setattr(idx, "news_freshness_reason", lambda stamp, now: None)
    item=idx._hydrate(
        cfg,
        "https://www.ihf.info/media-center/news/seventh-barcelona",
        "fallback",
    )
    assert item is not None
    assert item["published_at"].isoformat().startswith("2026-09-27T00:00:00")
    assert item["image"]=="https://www.ihf.info/sites/default/files/handball-photo.jpg"
    assert item["image_candidates"][0]["url"]==item["image"]


def test_first_party_baseball_darts_mma_indexes_are_enabled():
    by_id={row["id"]:row for row in idx.HTML_INDEXES}
    assert by_id["mlb-baseball-news"]["sport"]=="baseball"
    assert by_id["mlb-baseball-news"]["url"]=="https://www.mlb.com/news"
    assert by_id["pdc-darts-news"]["sport"]=="darts"
    assert by_id["ufc-mma-news"]["sport"]=="mma"
    assert all(by_id[name].get("enabled",True) for name in (
        "mlb-baseball-news","pdc-darts-news","ufc-mma-news"
    ))


def test_olympics_global_source_is_mixed_and_never_stamps_sport():
    row=next(x for x in idx.HTML_INDEXES if x["id"]=="olympics-global-sports-news")
    assert row["kind"]=="mixed"
    assert row["sport"] is None
    assert row["host"]=="www.olympics.com"
    assert row["enabled"] is False


def test_major_north_american_league_indexes_are_first_party():
    by_id={row["id"]:row for row in idx.HTML_INDEXES}
    assert by_id["nba-basketball-news"]["sport"]=="basketball"
    assert by_id["nfl-american-football-news"]["sport"]=="american-football"
    assert by_id["nhl-ice-hockey-news"]["sport"]=="ice-hockey"
    assert by_id["nba-basketball-news"]["host"]=="www.nba.com"
    assert by_id["nfl-american-football-news"]["host"]=="www.nfl.com"
    assert by_id["nhl-ice-hockey-news"]["host"]=="www.nhl.com"


def test_official_source_hydration_helper_is_bounded(monkeypatch):
    cfg={"id":"fixture","sport":"football"}
    monkeypatch.setattr(
        idx,
        "_anchor_candidates",
        lambda row:[("https://example.test/a","A"),("https://example.test/b","B")],
    )
    monkeypatch.setattr(
        idx,
        "_hydrate",
        lambda row,url,title,**kwargs:{"title":title,"url":url},
    )
    rows=idx._hydrate_source(cfg,1)
    assert rows==[{"title":"A","url":"https://example.test/a"}]


def test_nrl_first_party_rugby_league_index_is_enabled():
    row=next(x for x in idx.HTML_INDEXES if x["id"]=="nrl-rugby-league-news")
    assert row["sport"]=="rugby-league"
    assert row["host"]=="www.nrl.com"
    assert row.get("enabled",True) is True


def test_chinese_olympic_source_is_taxonomy_neutral():
    row=next(x for x in idx.HTML_INDEXES if x["id"]=="chinese-olympic-sports-news")
    assert row["kind"]=="mixed"
    assert row["sport"] is None
    assert row["host"]=="en.olympic.cn"
    assert row["visible_date"] is True


def test_visible_iso_minute_date_uses_source_timezone():
    stamp=idx._visible_published_date(
        "<div>2026-09-28 09:25 Xinhua</div>",
        "Asia/Shanghai",
    )
    assert stamp.isoformat()=="2026-09-28T01:25:00+00:00"


def test_chinese_olympic_source_declares_shanghai_timezone():
    row=next(x for x in idx.HTML_INDEXES if x["id"]=="chinese-olympic-sports-news")
    assert row["visible_date_timezone"]=="Asia/Shanghai"
