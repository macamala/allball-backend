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
    cfg=idx.SITEMAPS[0]
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
      <meta property="article:published_time" content="2026-09-26T12:00:00+00:00">
    </head><body><main><p>{body}</p></main></body></html>'''.encode()
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: html)
    monkeypatch.setattr(idx, 'freshness_reason', lambda stamp, now, **kwargs: None)
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
