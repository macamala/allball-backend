"""Additional article-bound News desks reviewed on 2026-10-04.

A working feed is not proof of today's coverage. Original source dates, visible
article bodies, actual article photographs, original writing and independent
factual validation remain mandatory. No fixtures/results are read or written.
"""
RSS_FEEDS = (
    {'url': 'https://www.getfootballnewsbene.com/feed/',
     'publisher': 'Get Belgian and Dutch Football News', 'kind': 'league',
     'sport': 'football', 'enabled': True, 'verified_official': False,
     'article_body_required': True, 'article_https_host': 'getfootballnewsbene.com',
     'article_path_re': r'^/[^/]+/?$',
     'excluded_article_paths': ('/category/', '/tag/', '/page/', '/feed/', '/wp-'),
     'excluded_entry_categories': ('Opinion', 'Predictions', 'Betting'),
     'note': 'Verified inner-post-entry entry-content and same-page social photo. Known shared publisher square is rejected; no replacement card image or forced league.'},
    {'url': 'https://www.fkspartak.com/feed/', 'publisher': 'FK Spartak Subotica',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'verified_official': True,
     'article_body_required': True, 'article_https_host': 'fkspartak.com',
     'article_path_re': r'^/[^/]+/?$',
     'excluded_article_paths': ('/category/', '/tag/', '/page/', '/feed/', '/wp-'),
     'note': 'Official club post-content, exact source dates and social photograph verified. Last audited item was September 27: retain freshness limits rather than republish it as new.'},
)

ARTICLE_PROFILES = {
    'getfootballnewsbene.com': {'body_class': 'entry-content'},
    'fkspartak.com': {'body_class': 'post-content'},
}

# Planning associations only. Each actual story still establishes its own
# competition, gender and age group; never label a national-team report as a
# domestic league story merely because this desk also covers that league.
SOURCE_DESKS = {
    'Get Belgian and Dutch Football News': ('netherlands-eredivisie', 'belgium-pro-league'),
    'FK Spartak Subotica': ('serbia-prva-liga',),
}
