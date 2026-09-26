"""Verified RSS metadata endpoints, NOT a reuse licence or production coverage.

Enabled only by NEWS_EXPANDED_FEEDS_ENABLED. Stale metadata remains honestly
labelled; the runtime date gate must see a new eligible entry before admission.
"""
_OBSERVED = ('2026-09-26T06:37:05.991572+00:00', '2026-09-26T06:43:20.010289+00:00')
_ROWS = [
    ('football', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/football/rss.xml', 0, True),
    ('tennis', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/tennis/rss.xml', 0, True),
    ('motorsport', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/formula1/rss.xml', 0, True),
    ('rugby', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/rugby-union/rss.xml', 0, True),
    ('rugby-league', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/rugby-league/rss.xml', 0, True),
    ('cricket', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/cricket/rss.xml', 0, True),
    ('volleyball', 'FIVB', 'https://www.fivb.com/feed/', 0, True),
    ('netball', 'World Netball', 'https://netball.sport/feed/', 0, True),
    ('lacrosse', 'World Lacrosse', 'https://worldlacrosse.sport/feed/', 0, False),
    ('snooker', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/snooker/rss.xml', 0, False),
    ('boxing', 'World Boxing', 'https://worldboxing.org/feed/', 0, True),
    ('boxing', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/boxing/rss.xml', 0, True),
    ('horse-racing', 'British Horseracing Authority', 'https://www.britishhorseracing.com/feed/', 0, False),
    ('horse-racing', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/horse-racing/rss.xml', 0, False),
    ('greyhound-racing', 'GBGB', 'https://www.gbgb.org.uk/feed/', 0, True),
    ('golf', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/golf/rss.xml', 0, True),
    ('cycling', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/cycling/rss.xml', 0, True),
    ('athletics', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/athletics/rss.xml', 0, True),
    ('swimming', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/swimming/rss.xml', 0, True),
    ('winter-sports', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/winter-sports/rss.xml', 0, False),
    ('counter-strike', 'Valve', 'https://store.steampowered.com/feeds/news/app/730/?l=english', 0, True),
    ('basketball', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/basketball/rss.xml', 1, True),
    ('american-football', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/american-football/rss.xml', 1, True),
    ('ice-hockey', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/ice-hockey/rss.xml', 1, True),
    ('baseball', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/baseball/rss.xml', 1, True),
    ('mma', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/mixed-martial-arts/rss.xml', 1, True),
    ('darts', 'BBC Sport', 'https://feeds.bbci.co.uk/sport/darts/rss.xml', 1, False),
    ('dota-2', 'Valve', 'https://store.steampowered.com/feeds/news/app/570/?l=english', 1, False),
    ('harness-racing', 'USTA', 'https://ustrottingnews.com/feed/', 1, True),
]
VERIFIED_RSS = [
    {'url': url, 'kind': 'mixed', 'sport': sport, 'enabled': True,
     'publisher': publisher, 'metadata_observed_at': _OBSERVED[group],
     'metadata_state': 'RSS_METADATA_FRESH' if fresh else 'RSS_METADATA_STALE_OR_UNDATED',
     'reuse_rights': 'NOT_VERIFIED'}
    for sport, publisher, url, group, fresh in _ROWS
]
