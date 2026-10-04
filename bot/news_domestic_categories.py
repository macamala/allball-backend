"""Explicit domestic News listings verified 2026-10-03.

Use the existing RSS/index hydration, article-body, date, photo and writer gates.
A listing is discovery, never a substitute for the actual article's subject.
"""
RSS_FEEDS = (
    {'url':'https://nb1.hu/category/nb2/feed/', 'publisher':'NB1.hu',
     'kind':'league','sport':'football','verified_official':False,'enabled':True,
     'allowed_article_paths':('/hir/',),'article_body_required':True,
     'note':'Autodiscovered NB2 feed. Mixed-tier friendlies retain primary subject; do not stamp NB II on every article.'},
)
HTML_INDEXES = (
    {'id':'sweden-allsvenskan-category','publisher':'FotbollDirekt','sport':'football','verified_official':False,
     'url':'https://fotbolldirekt.se/allsvenskan/','host':'fotbolldirekt.se',
     # Observed live 2026-10-04: navigation consumed three of eight News slots.
     # Exact directory slugs only; actual reporting about the table survives.
     'exclude_articles':('alla-lag','spelschema','tabell'),
     'paths':('/allsvenskan/',),'article_path_re':r'^/allsvenskan/[^/]+/?$'},
    {'id':'sweden-superettan-category','publisher':'FotbollDirekt','sport':'football','verified_official':False,
     'url':'https://fotbolldirekt.se/superettan/','host':'fotbolldirekt.se',
     'paths':('/superettan/',),'article_path_re':r'^/superettan/[^/]+/?$'},
    {'id':'brazil-serie-b-category','publisher':'ge','sport':'football','verified_official':False,
     'url':'https://ge.globo.com/futebol/brasileirao-serie-b/','host':'ge.globo.com',
     'paths':('/',),'article_path_re':r'^/.*/futebol/.*?/noticia/20\d{2}/\d{2}/\d{2}/[^/]+\.ghtml$'},
    {'id':'croatia-hnl-category','publisher':'Index.hr','sport':'football','verified_official':False,
     'url':'https://www.index.hr/sport/rubrika/shnl/5204.aspx','host':'www.index.hr',
     'paths':('/sport/clanak/',),'article_path_re':r'^/sport/clanak/[^/]+/\d+\.aspx$'},
)
SOURCE_DESKS = {
    'NB1.hu': ('hungary-nb-1','hungary-nb-2'),
    'FotbollDirekt': ('sweden-allsvenskan','sweden-superettan'),
    'ge': ('brazil-serie-a','brazil-serie-b'),
    'Index.hr': ('croatia-hnl','croatia-prva-nl'),
}
