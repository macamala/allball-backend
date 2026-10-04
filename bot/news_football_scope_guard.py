"""Narrow News-only evidence for observed cross-sport publication incidents.

These guards never modify article prose, dates, results, or fixtures. A public
conflict is held by the existing admission/incident mechanism for review rather
than relabelled or rewritten without source validation.
"""
from __future__ import annotations
import re
import unicodedata
from urllib.parse import urlsplit


def plain(value):
    value = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ''.join(char for char in value if not unicodedata.combining(char))


def other_sport_headline(title):
    text = plain(title)
    # Avoid incidental off-field activities in explicitly football-led stories.
    football = bool(re.search(r'\b(?:football|soccer|fudbal|futebol|fussball)\b', text))
    if not football:
        if re.search(r'\b(?:surfing|surfistas?)\b', text):
            return 'surfing'
        if re.search(r'\b(?:triathlon|triatlo|triatleta)\b', text):
            return 'triathlon'
    # Audited distinct futsal opponents, not a general Barcelona/Benfica alias.
    # Official club source: oparrulofs.es, futsal fixtures, 2026-10-03.
    if (re.search(r'\bo[\s\x27’]+parrulo\b', text)
            and re.search(r'\b(?:vina albali )?valdepenas\b', text)
            and re.search(r'\b(?:draw|drew|hosts?|beat|defeats?|vs|versus)\b', text)):
        return 'futsal'
    return None


def reviewed_other_sport_path(url):
    try:
        parts = urlsplit(str(url or ''))
        if parts.scheme != 'https' or parts.username or parts.password:
            return None
    except ValueError:
        return None
    host = (parts.hostname or '').lower().removeprefix('www.')
    path = parts.path.lower()
    if host == 'record.pt':
        for prefix, sport in (('/modalidades/surf/', 'surfing'),
                              ('/modalidades/triatlo/', 'triathlon')):
            if path.startswith(prefix):
                return sport
    return None


def football_scope_conflict(item, sport):
    if sport != 'football':
        return None
    expected = (other_sport_headline((item or {}).get('title'))
                or reviewed_other_sport_path((item or {}).get('url')))
    return 'taxonomy_football_scope_conflict' if expected else None


def video_game_product_reason(item):
    title = plain((item or {}).get('title'))
    if (re.search(r'\b(?:battlefield studios|battlefield 6|redsec)\b', title)
            and re.search(r'\b(?:unveils?|announces?|reveals?|introduces?)\b', title)
            and re.search(r'\b(?:updates?|features?|season|patch)\b', title)
            and not re.search(r'\b(?:tournament|championship|esports|finals?|qualifier)\b', title)):
        return 'non_article_video_game_product'
    return None
