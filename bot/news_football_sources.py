"""Additional football desks verified 2026-10-02. Discovery is not coverage.

All sources use the existing robots-aware transport and publication, original
writing, factual and same-article image gates. No paid API is added here.
"""
HTML_INDEXES = (
    {'id':'ligaportugal-official-news', 'sport':'football', 'publisher':'Liga Portugal',
     'url':'https://www.ligaportugal.pt/noticias', 'host':'www.ligaportugal.pt',
     'paths':('/news/',), 'article_path_re':r'^/news/\d+/[^/]+/?$'},
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
    {'url':'https://www.index.hr/rss/sport-nogomet','kind':'league','sport':'football',
     'publisher':'Index.hr','verified_official':False,'enabled':True,
     'allowed_article_paths':('/sport/clanak/',),'article_path_re':r'^/sport/clanak/[^/]+/\d+\.aspx$',
     'article_body_required':True,
     'note':'Football RSS discovery only. Facts must come from the scoped section.text of the same article; no related cards or RSS teaser fallback.'},
    {'url':'https://nb1.hu/feed/','kind':'league','sport':'football',
     'publisher':'NB1.hu','verified_official':False,'enabled':True,
     'allowed_article_paths':('/hir/',),'article_body_required':True,
     'note':'Hungarian football discovery with verified content-post body and same-post social hero; domestic, national, women and youth remain independently classified.'},
    {'url':'https://www.goal.pl/feed/','kind':'league','sport':'football',
     'publisher':'Goal.pl','verified_official':False,'enabled':True,
     'article_body_required':True,
     'excluded_article_paths':('/typy/', '/bukmacherzy/', '/bonusy/', '/promocje/'),
     'note':'Polish football reporting from entry-content only. Related-post recommendations and a long RSS teaser are not article facts.'},
    {'url':'https://the72.co.uk/feed/','kind':'league','sport':'football',
     'publisher':'The72','verified_official':False,'enabled':True,
     'verified_body_field':'content','verified_body_min_words':150,
     'article_path_re':r'^/20\d{2}/\d{2}/\d{2}/[^/]+/?$',
     'note':'Verified full WordPress post in RSS. No forced Championship label: EFL tiers, domestic clubs and youth references are resolved from the article.'},

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
    'Liga Portugal': ['portugal-primeira-liga','portugal-liga-2'],
    'LALIGA': ['spain-la-liga','spain-la-liga-2'],
    'Lega B': ['italy-serie-b'],
    'Ekstraklasa': ['poland-ekstraklasa'],
    'J.LEAGUE': ['japan-j1-league','japan-j2-league'],
    'Saudi Pro League': ['saudi-pro-league'],
    'K League United': ['south-korea-k-league-1','south-korea-k-league-2'],
    'CONMEBOL': ['conmebol-libertadores','conmebol-sudamericana','football-women'],
    'Liga Profesional': ['argentina-liga-profesional'],
}

# Regional desks are associations for coverage review, not evidence that each
# desk publishes an article about every listed competition on every day.
SOURCE_DESKS.update({
    'Index.hr': ['croatia-hnl','croatia-prva-nl'],
    'NB1.hu': ['hungary-nb-1','hungary-nb-2'],
    'Goal.pl': ['poland-ekstraklasa','poland-first-league'],
    'The72': ['england-championship','england-league-one','england-league-two'],
})

# Reviewed regional desks join the existing RSS intake, never a second writer.
from .news_football_regional_desks import RSS_FEEDS as REGIONAL_RSS, SOURCE_DESKS as REGIONAL_DESKS
RSS_FEEDS = RSS_FEEDS + REGIONAL_RSS
SOURCE_DESKS = {**SOURCE_DESKS, **REGIONAL_DESKS}

from .news_football_source_context import HTML_INDEXES as REGIONAL_HTML_INDEXES
HTML_INDEXES = HTML_INDEXES + REGIONAL_HTML_INDEXES
SOURCE_DESKS.update({'Gazzetta': ['greece-super-league','greece-super-league-2'],
                     'LAOLA1': ['austria-bundesliga','austria-second-league']})

# Native reports are read from their own visible article header, not navicode.
from .news_jleague_native import NATIVE_INDEXES
HTML_INDEXES = HTML_INDEXES + NATIVE_INDEXES
