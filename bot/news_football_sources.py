"""Additional football desks verified 2026-10-02. Discovery is not coverage.

All sources use the existing robots-aware transport and publication, original
writing, factual and same-article image gates. No paid API is added here.
"""
HTML_INDEXES = (
    {'id':'laliga-official-news', 'sport':'football', 'publisher':'LALIGA',
     'url':'https://www.laliga.com/noticias', 'host':'www.laliga.com',
     'paths':('/noticias/',), 'article_path_re':r'^/noticias/[^/]+/?$',
     'exclude_article_fragments':('sorteo-entradas','concurso-','participa-y-')},
    {'id':'legab-official-news', 'sport':'football', 'publisher':'Lega B',
     'url':'https://www.legab.it/news/', 'host':'www.legab.it',
     'paths':('/news/',), 'article_path_re':r'^/news/[^/]+/?$'},
    {'id':'ekstraklasa-official-news', 'sport':'football', 'publisher':'Ekstraklasa',
     'url':'https://www.ekstraklasa.org/aktualnosci', 'host':'www.ekstraklasa.org',
     'paths':('/aktualnosci/',), 'article_path_re':r'^/aktualnosci/[^/]+/?$',
     'exclude_article_fragments':('konkurs','wygraj','fantasy')},
    {'id':'jleague-j1-english-news', 'sport':'football', 'publisher':'J.LEAGUE',
     'url':'https://www.jleague.jp/en/j1/news/', 'host':'www.jleague.jp',
     'paths':('/en/news/article/',), 'article_path_re':r'^/en/news/article/\d+/?$'},
    {'id':'jleague-j2-english-news', 'sport':'football', 'publisher':'J.LEAGUE',
     'url':'https://www.jleague.jp/en/j2/news/', 'host':'www.jleague.jp',
     'paths':('/en/news/article/',), 'article_path_re':r'^/en/news/article/\d+/?$'},
    {'id':'saudi-pro-league-news', 'sport':'football', 'publisher':'Saudi Pro League',
     'url':'https://www.spl.com.sa/en/news', 'host':'www.spl.com.sa',
     'paths':('/en/news/',), 'article_path_re':r'^/en/news/[^/]+/?$',
     'exclude_article_fragments':('win-tickets','fantasy','vote-for-')},
)

RSS_FEEDS = (
    {'url':'https://www.kleagueunited.com/feeds/posts/default?alt=rss',
     'kind':'league','sport':'football','publisher':'K League United','verified_official':False,
     'enabled':True,'verified_body_field':'summary','verified_body_min_words':150,
     'article_path_re':r'^/20\d{2}/\d{2}/[^/]+\.html$',
     'note':'English publisher full RSS body, exact offset date and same-post images verified. Never substitute blocked page content or a league stamp.'},
    {'url':'https://www.soccernews.com/feed/', 'kind':'league','sport':'football',
     'publisher':'SoccerNews','verified_official':False,'enabled':True,
     'verified_body_field':'content','verified_body_min_words':120,
     'article_path_re':r'^/[^/]+/\d+/?$',
     'excluded_article_paths':('/betting-', '/prediction-', '/free-bets'),
     'note':'Use the verified full WordPress content field, not the page betting footer. Independent competition and image admission remain mandatory.'},
    {'url':'https://www.conmebol.com/feed/','kind':'mixed','publisher':'CONMEBOL',
     'verified_official':True,'enabled':True,'verified_body_field':'summary','verified_body_min_words':150,
     'allowed_article_paths':('/noticias/',),'excluded_article_paths':('/noticias/licitacion',),
     'note':'Verified full RSS descriptions, explicit UTC dates and article photos. Mixed includes futsal: never stamp football or a continental competition.'},
    {'url':'https://www.ligaprofesional.ar/feed/','kind':'league','sport':'football',
     'publisher':'Liga Profesional','verified_official':True,'enabled':True,
     'verified_body_field':'content','verified_body_min_words':120,
     'allowed_article_paths':('/notas/primera/',),
     'note':'Only first-team articles from the verified full WordPress post, not related-card prose. Reserve/juvenile score grids are excluded. Quiet or stale periods remain empty.'},
)

# This is only a source-association map for monitoring gaps, not evidence that
# any source has written a current article for every associated competition.
SOURCE_DESKS = {
    'LALIGA': ['spain-la-liga','spain-la-liga-2'],
    'Lega B': ['italy-serie-b'],
    'Ekstraklasa': ['poland-ekstraklasa'],
    'J.LEAGUE': ['japan-j1-league','japan-j2-league'],
    'Saudi Pro League': ['saudi-pro-league'],
    'K League United': ['south-korea-k-league-1','south-korea-k-league-2'],
    'CONMEBOL': ['conmebol-libertadores','conmebol-sudamericana','football-women'],
    'Liga Profesional': ['argentina-liga-profesional'],
}
