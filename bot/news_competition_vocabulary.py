"""Literal native competition phrases observed in source reports, News only.

Spelling evidence establishes only a competition name, never a match fact,
club membership or any permission to skip independent factual validation.
"""
LITERAL_COMPETITION_ALIASES = {
    'brazil-serie-b': (
        'série b do campeonato brasileiro', 'série b do brasileiro',
        'campeonato brasileiro série b', 'brasileirão série b',
        'serie b do campeonato brasileiro', 'serie b do brasileiro', 'campeonato brasileiro serie b',
    ),
    'hungary-nb-1': ('NB I',),
    'hungary-nb-2': ('NB II',),
}


def corrected_qualified_football_league(league, text):
    """Correct an Italian or broad hint only when Brazil is explicit.

    Neither publisher geography nor club membership can supply this correction.
    Ambiguous text naming both competitions leaves the prior hint unchanged.
    """
    if league not in {None, 'football-international', 'football-world', 'italy-serie-a', 'italy-serie-b'}:
        return league
    from .news_football_sections import _explicit, _norm
    explicit = _explicit(_norm(text))
    return explicit if explicit in {'brazil-serie-a', 'brazil-serie-b'} else league


def conflicting_regional_serie_alias(league, source_url, lead):
    """Reject an unqualified Italian default on a reviewed Brazilian club desk.

    A literal 'Serie B' is not an Italian qualifier. The exact regional club
    article path can disprove that default, but cannot identify a replacement
    competition or supply any sporting fact. Current membership or an explicit
    source phrase must still establish the final News menu. An article actually
    naming Italian football retains its normal classification.
    """
    import re
    from urllib.parse import urlsplit
    if league not in {'italy-serie-a', 'italy-serie-b'} or not isinstance(source_url, str):
        return False
    try:
        url = urlsplit(source_url)
        if (url.scheme != 'https' or url.hostname != 'ge.globo.com'
                or url.username or url.password or url.port not in (None, 443)):
            return False
    except ValueError:
        return False
    regional = re.fullmatch(
        r'/(?:ac|al|am|ap|ba|ce|df|es|go|ma|mg|ms|mt|pa|pb|pe|pi|pr|rj|rn|ro|rr|rs|sc|se|sp|to)/'
        r'(?:[a-z0-9-]+/)*futebol/times/[a-z0-9-]+/noticia/20\d{2}/\d{2}/\d{2}/[a-z0-9-]+\.ghtml', url.path)
    if not regional:
        return False
    from .news_football_sections import _norm
    explicit_italian = re.search(r'\b(?:italy|italia|italian[ao]?|italian[ao]s|calcio|serie [ab]kt)\b', _norm(lead))
    return not bool(explicit_italian)
