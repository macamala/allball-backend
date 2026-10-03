"""News menu assignment after an article has passed football/public admission.

This does not identify the sport, write prose, or admit a held article. A club
section is an editorial association backed by a dated membership catalogue;
it must never be used as evidence for a factual claim in a generated story.
"""
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from editorial import sanitize_body, sanitize_summary, sanitize_title
from .taxonomy import COMPETITIONS
from .news_football_memberships import memberships_for_news
from .news_competition_scope import conflicting_competition_qualifier

_ROOT = Path(__file__).parent
_CATALOG = json.loads((_ROOT / 'news_football_leagues.json').read_text())
_CLUBS = json.loads((_ROOT / 'news_football_clubs.json').read_text())
_WOMEN_KEYS = {r['league'] for r in _CATALOG if 'women' in r['league']} | {'usa-nwsl'}
_YOUTH_KEYS = {'uefa-under-21-euro', 'football-youth'}
_TOPICS = {'football-international', 'football-youth', 'football-women', 'football-national-teams'}


def _norm(value):
    value = unicodedata.normalize('NFKD', value or '').casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^\w]+', ' ', value).strip()


def _has(text, phrase):
    return f' {phrase} ' in f' {text} '


_ALIASES = {}
for _row in _CATALOG:
    _key = _row['league']
    _ALIASES[_key] = {_norm(a) for a in [*_row['aliases'],
        *COMPETITIONS.get(_key, {}).get('aliases', [])] if a.strip()}

_WOMEN = re.compile(r'\b(?:women|womens|woman|wsl|uwcl|uswnt|lionesses|keira walsh|alexia putellas|frauen|damen|feminin|feminine|feminines|femenina|femeninas|femenino|femeninos|feminino|feminina|femminile|femminili|zenski|zenska|zenske)\b')
_YOUTH = re.compile(r'\b(?:u\s?(?:16|17|18|19|20|21|23)s?|under (?:16|17|18|19|20|21|23)s?|u twenty one|youth team)\b')
_NATIONAL = re.compile(r'\b(?:national (?:football )?(?:team|squad)|usmnt|uswnt|international (?:football fixtures|friendly|friendlies|goal)|reprezentacij\w*)\b')
_COUNTRIES = ('england', 'spain', 'croatia', 'italy', 'france', 'serbia', 'portugal',
              'germany', 'czech republic', 'czechia', 'bulgaria', 'netherlands', 'honduras',
              'wales', 'ireland', 'scotland', 'switzerland', 'hungary', 'brazil', 'australia',
              'belgium', 'turkey', 'turkiye', 'kosovo')


def _club_section(title, summary, article, women, today):
    stamp = getattr(article, 'published_at', None) or getattr(article, 'created_at', None)
    if isinstance(stamp, str):
        try:
            stamp = date.fromisoformat(stamp[:10])
        except ValueError:
            return None
    elif hasattr(stamp, 'date'):
        stamp = stamp.date()
    stamp = stamp or today
    static_current = (_CLUBS['valid_from'] <= stamp.isoformat() <= _CLUBS['valid_until']
                      and today.isoformat() <= _CLUBS['valid_until'])
    live = memberships_for_news()
    catalogue = dict(_CLUBS['leagues']) if static_current else {}
    for league, entry in live.items():
        if entry['valid_from'] <= stamp.isoformat() <= entry['valid_until']:
            # Keep a short static alias only when it unambiguously belongs to
            # one of the current verified full names; never keep relegated clubs.
            clubs = list(entry['clubs'])
            names = [_norm(name) for name in clubs]
            for alias in catalogue.get(league, {}).get('clubs', []):
                normalized = _norm(alias)
                if sum(_has(name, normalized) or _has(normalized, name) for name in names) == 1:
                    clubs.append(alias)
            catalogue[league] = {**entry, 'clubs': clubs}
    past_title = bool(re.search(r'\b(?:rules out|rejects|former|international goal|international match)\b', title))
    for text in (title, summary):
        if text == title and past_title:
            continue
        candidates = []
        for league, entry in catalogue.items():
            if (league in _WOMEN_KEYS) != women:
                continue
            if entry.get('valid_until', _CLUBS['valid_until']) < today.isoformat():
                continue
            for club in entry['clubs']:
                alias = _norm(club)
                if _has(text, alias):
                    # Summary-only association requires current club ownership
                    # or a club role, not a historical/opponent name in passing.
                    if text == summary and not re.search(r'(?<!\w)' + re.escape(alias) +
                        r' (?:s |(?:football )?(?:club|defender|midfielder|striker|goalkeeper|forward)|confirmed|announced)', text):
                        continue
                    candidates.append((text.index(alias), -len(alias), league))
        if candidates:
            return min(candidates)[2]
    return None


def _explicit(text, women=False, youth=False):
    hits = []
    for key, aliases in _ALIASES.items():
        if key in _TOPICS:
            continue
        if key == 'uefa-nations-league' and 'concacaf' in text:
            continue
        if women and key not in _WOMEN_KEYS:
            continue
        if youth and key not in _YOUTH_KEYS:
            continue
        for alias in aliases:
            for match in re.finditer(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text):
                if conflicting_competition_qualifier(key, text, match.start(), match.end()):
                    continue
                before = text[max(0, match.start()-65):match.start()]
                after = text[match.end():match.end()+35]
                # Incidental history and promotion ambitions are not today's
                # competition. Never route a current friendly by its opponent's
                # former World Cup trophy, or Bari by a hoped-for Serie B return.
                if re.search(r'(?:return(?:ing)? to|back to|promot\w* to|relegated from|former|defending)\s+(?:the\s+)?$', before):
                    continue
                if key == 'fifa-world-cup' and re.match(r'\s+(?:champion|roster|squad)', after):
                    continue
                hits.append((key, alias, match.start(), match.end()))
    # Women's CL / La Liga 2 / Brazilian Serie B must win over a shorter
    # competition name embedded in that very same phrase.
    hits = [h for h in hits if not any(h[0] != other[0] and
        other[2] <= h[2] and other[3] >= h[3] and len(other[1]) > len(h[1]) for other in hits)]
    keys = {h[0] for h in hits}
    return next(iter(keys)) if len(keys) == 1 else None


def football_news_section(article, *, today=None):
    """Return a supported News section; None means insufficient evidence.

    Call only for an independently admitted football article. The headline and
    lead establish the event. The full body may identify women's/youth context,
    but incidental body mentions never select a men's domestic league.
    """
    # Audited 2026-09-30 against this exact club article's visible introduction:
    # Copenhagen, 22 October, round two of Лиге конференције. The published
    # English lead only says "this European competition"; club membership
    # must not turn that fixture into a Serbian Superliga story. Menu only.
    try:
        source = urlsplit(getattr(article, 'source_url', None) or getattr(article, 'external_id', '') or '')
    except ValueError:
        source = None
    if (source and source.scheme in {'http', 'https'}
            and (source.hostname or '').removeprefix('www.') == 'crvenazvezdafk.com'
            and source.path.rstrip('/') == '/vesti/boaci-protiv-kopenhagena-ocekujem-pravu-zvezdasku-atmosferu'):
        return 'uefa-conference-league'
    # Legacy card 22217 contains this same verified interview. Bound the
    # audited correction to both ID and headline regardless of source spelling.
    if (getattr(article, 'id', None) == 22217 and getattr(article, 'title', '') ==
            'Red Star Belgrade prepares for its first match at home in this European competition'):
        return 'uefa-conference-league'
    title = _norm(sanitize_title(getattr(article, 'title', '') or ''))
    summary = _norm(sanitize_summary(getattr(article, 'summary', '') or ''))
    body = _norm(sanitize_body(getattr(article, 'ai_content', None) or
                              getattr(article, 'content', '') or ''))[:2200]
    lead = title + ' ' + summary
    # A passing mention of a women's competition in a mixed season-launch
    # article cannot turn Manchester City's financial case into WSL news.
    women = bool(_WOMEN.search(lead) or _explicit(body[:350], women=True))
    youth = bool(_YOUTH.search(lead) or re.search(r'\bacademy\b', title))
    today = today or date.today()
    # Disability tournaments have their own formats; do not confuse a blind
    # football European Championship with the senior UEFA competition.
    if re.search(r'\b(?:blind football|amputee football|deaf football|futsal|beach soccer)\b', lead):
        return None

    # A headline/lead identifying a regional national-team event must not
    # inherit an incidental World Cup/club competition from biography.
    # This is menu association only: no sporting fact or date is added.
    regional_national_event = re.search(
        r'\b(?:asian games|asiad|olympic games|olympic football|olympic soccer|'
        r'africa cup of nations|african cup of nations|afcon|concacaf gold cup|'
        r'copa america|afc asian cup|asian cup)\b', lead)
    if regional_national_event:
        return 'football-women' if women else 'football-youth' if youth else 'football-national-teams'

    if women:
        national_women = bool(_NATIONAL.search(lead))
        key = _explicit(title, women=True) or _explicit(summary, women=True)
        if national_women and key not in {'fifa-womens-world-cup', 'uefa-womens-nations-league'}:
            key = None
        if not key:
            # When the headline already establishes women, an unqualified
            # tournament name is safe to disambiguate to the women's event.
            for plain, qualified in [('uefa-champions-league', 'uefa-womens-champions-league'),
                                     ('uefa-nations-league', 'uefa-womens-nations-league'),
                                     ('fifa-world-cup', 'fifa-womens-world-cup')]:
                if _explicit(title) == plain:
                    key = qualified
                    break
        if not key and not national_women:
            # Body evidence is usable only for a specifically women's event.
            key = _explicit(body, women=True)
        if not key and not national_women:
            key = _club_section(title, summary, article, True, today)
        return key or 'football-women'
    if youth:
        if re.search(r'\b(?:u ?21|under 21|u twenty one)', lead) and re.search(r'\b(?:euro|european championship)\b', lead):
            return 'uefa-under-21-euro'
        return 'football-youth'

    key = _explicit(title) or _explicit(summary)
    if key:
        return key
    headline_club = _club_section(title, '', article, False, today)
    national = (bool(_NATIONAL.search(title)) or
                (bool(_NATIONAL.search(summary)) and not headline_club)) or (
        any(_has(lead, country) for country in _COUNTRIES)
        and (re.search(r'\b(?:national anthem|senior .{0,25}debut|(?:serbia|italy|england|france|netherlands|dutch) (?:a )?(?:squad|team|debut))\b', lead)
             or (any(title.startswith(country + ' ') for country in _COUNTRIES)
                 and re.search(r'\b(?:beat|beats|win|wins|defeat|defeats|coach|squad|team|draw|lose|loses|loss|fall|make|secure)\b', title))))
    # A player/coach headline can omit the national team while the lead/body
    # clearly identifies its current Nations League match.
    if not national and not _club_section(title, summary, article, False, today):
        national = bool(_NATIONAL.search(body[:650]) or re.search(r'\bnations league (?:match|fixture)\b', body))
    if national:
        # Match reports sometimes mention the competition only in the body.
        # Domestic club affiliations in that body cannot steal national news.
        body_key = _explicit(body)
        if body_key == 'uefa-nations-league':
            return body_key
        if body_key in {'fifa-world-cup', 'uefa-euro'} and re.search(
                r'\b(?:world cup|european championship|uefa euro) (?:qualifier|qualifying)\b', body):
            return body_key
        return 'football-national-teams'
    if re.search(r'\b(?:fifa|uefa|european club association|world football clubs)\b', lead) and re.search(
            r'\b(?:president|leadership|assembly|election|governance|rules|syndicate|association)\b', lead):
        return 'football-international'
    # An uncovered cup cannot be silently relabelled as a domestic league.
    if re.search(r'\b(?:cup|pokal|coppa|copa del rey)\b', title):
        return None
    return _club_section(title, summary, article, False, today)


def assign_public_football_section(article, tax):
    """Update only the menu fields of an already-public AI football story."""
    if not (article.ai_generated and tax.public_ok and tax.resolved_sport == 'football'):
        return False
    key = football_news_section(article)
    if not key or key == tax.resolved_competition:
        return False
    tax.resolved_competition = key
    tax.competition_confidence = '0.950'
    article.league = key
    article.country = COMPETITIONS[key]['country']
    return True
