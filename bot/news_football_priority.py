"""News-only editorial order. Priority is never taxonomy or admission evidence."""
import re
from collections import defaultdict, deque
from types import SimpleNamespace
from urllib.parse import urlsplit

PRIMARY_COMPETITIONS = frozenset({
    'england-premier-league', 'spain-la-liga', 'italy-serie-a',
    'germany-bundesliga', 'france-ligue-1', 'uefa-champions-league',
    'uefa-europa-league', 'uefa-conference-league', 'uefa-nations-league',
    'fifa-world-cup', 'fifa-club-world-cup', 'uefa-euro',
})


def candidate_football_section(item, tags, *, today=None):
    """Scheduling hint from source evidence, never a published league claim."""
    if getattr(tags, 'sport', None) != 'football':
        return None
    from .news_football_sections import football_news_section
    body = item.get('_classification_text') or item.get('_extracted') or ''
    source = SimpleNamespace(title=item.get('title') or '',
        summary=item.get('summary') or str(body)[:500], content=body,
        published_at=item.get('published_at'))
    return football_news_section(source, today=today) or getattr(tags, 'league', None)


def spread_football_leagues(items, inventory, *, section, priority):
    """Keep Zvezda first, then balance known leagues with a protected other lane.

    Three major slots alternate with one other-league slot. Within each lane,
    the smallest public inventory wins; projected slots prevent one empty
    league from consuming the cycle. Preserve the existing publisher order
    inside each league. Unknown sections receive no invented coverage debt.
    """
    output, lanes = [], {1: {}, 0: {}}
    for item in items:
        tier = priority(item)
        if tier >= 2:
            output.append(item)
            continue
        key = section(item)
        lanes[1 if tier else 0].setdefault(key, deque()).append(item)
    scheduled = defaultdict(int)
    slot = 0
    while lanes[1] or lanes[0]:
        tier = 0 if slot % 4 == 3 else 1
        if not lanes[tier]:
            tier = 1 - tier
        pending = lanes[tier]
        key = min(pending, key=lambda k: (
            max(0, int(inventory.get(k, 0) or 0)) + scheduled[k] if k else 2 + scheduled[k],
        ))
        output.append(pending[key].popleft())
        scheduled[key] += 1
        if not pending[key]:
            del pending[key]
        slot += 1
    return output


def football_editorial_priority(item, tags=None):
    """Zvezda and major European/international reporting precede other soccer.

    Call only after sport classification; mixed-feed basketball stories about
    the same club never receive a football lane. No fields are changed here.
    """
    feed = item.get('feed') or {}
    sport = getattr(tags, 'sport', None) if tags is not None else feed.get('sport')
    if sport != 'football':
        return 0
    try:
        parts = urlsplit(item.get('url') or '')
        host, path = (parts.hostname or '').removeprefix('www.'), parts.path.casefold()
    except ValueError:
        host, path = '', ''
    title = str(item.get('title') or '').casefold()
    summary = str(item.get('summary') or '').casefold()
    text = title + ' ' + summary
    zvezda_pattern = r'\b(?:crven(?:a|e|oj|u|om)\s+zvezd(?:a|e|i|u|om)|црвен(?:а|е|ој|у|ом)\s+звезд(?:а|е|и|у|ом)|red star belgrade)\b'
    # Some RSS descriptions contain the entire article. An incidental former
    # club or reserve affiliate must not displace major-league reporting.
    lead = summary[:280]
    lead_match = re.search(zvezda_pattern, lead)
    current_club_lead = bool(lead_match and not re.search(
        r'\b(?:bivš\w*|bivs\w*|nekadašnj\w*|nekadasnj\w*|former|ex|filijal\w*)\b',
        lead[max(0, lead_match.start()-90):lead_match.start()]))
    if (host == 'crvenazvezdafk.com'
            or re.search(zvezda_pattern, title) or current_club_lead
            or re.search(r'(?:^|/)crvena-zvezda(?:/|$)', path)):
        return 2
    league = getattr(tags, 'league', None) if tags is not None else feed.get('league')
    if league in PRIMARY_COMPETITIONS:
        return 1
    if host in {'uefa.com', 'fifa.com', 'inside.fifa.com', 'fss.rs',
                'premierleague.com', 'ligue1.com', 'liverpoolfc.com', 'chelseafc.com',
                'football-italia.net'}:
        return 1
    if re.search(r'\b(?:premier league|la liga|laliga|serie a|bundesliga|ligue 1|'
                 r'champions league|europa league|conference league|nations league|'
                 r'world cup|european championship|liga nacija|liga šampiona|'
                 r'ligue des nations|équipe de france|équipe d[’\'](?:espagne|angleterre)|'
                 r'lige šampiona|lig[ae] sampiona|лиг[ае] нација|лиг[ае] шампиона|'
                 r'reprezentacij\w*|репрезентациј\w*)\b', text):
        return 1
    if re.search(r'/(?:premier-league|primera-division|bundesliga|serie-a|ligue-1|'
                 r'nations-league|nationsleague|seleccion|european-qualifiers|ligue-des-nations|equipe-france|equipe-espagne)/', path):
        return 1
    # Club paths give useful editorial scope when a local headline names only
    # the player. This does not assert current league membership in an article.
    if host == 'marca.com' and re.search(r'/futbol/(?:real-madrid|barcelona|'
            r'atletico|real-sociedad|athletic|betis|sevilla|valencia|villarreal|'
            r'osasuna|celta|espanyol|girona|getafe|rayo|mallorca)/', path):
        return 1
    return 0
