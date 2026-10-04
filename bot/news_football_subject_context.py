"""Literal primary subjects for News menus, never fixture or factual authority.

A role or match relationship in the headline/lead identifies a national side.
Nationality in a player's biography, country names in club names, and an
incidental national-team debut in the body do not.
"""
from __future__ import annotations
import re
from .news_football_subjects import _plain, literal_country_mentions

_EXTRA_COUNTRIES = ('USA', 'USMNT', 'USWNT', 'Haiti', 'Yemen', 'Burkina Faso', 'Republic of Ireland')
_CLUB_SUFFIX = re.compile(r'^\s+(?:vienna|wien|salzburg|lustenau|klagenfurt|fc|sc|united|city|rovers|athletic)\b')
_ROLE = r'(?:head coach|coach|manager|captain|goalkeeper|national team|national squad|football team|football squad)'


def national_primary_subject(title: str) -> bool:
    """Require literal role/fixture grammar; never infer from a country pair alone."""
    text = _plain(title)
    mentions = list(literal_country_mentions(title))
    for name in _EXTRA_COUNTRIES:
        for match in re.finditer(r'(?<!\w)' + re.escape(_plain(name)) + r'(?!\w)', text):
            mentions.append((match.start(), match.end(), _plain(name)))
    mentions = sorted({m for m in mentions if not any(
        n[0] <= m[0] and n[1] >= m[1] and n[1]-n[0] > m[1]-m[0]
        for n in mentions)})
    mentions = [m for m in mentions if not _CLUB_SUFFIX.match(text[m[1]:])]
    for start, end, name in mentions:
        after = text[end:]
        before = text[max(0, start-80):start]
        if re.match(r"(?:['’]s)?\s+" + _ROLE + r'\b', after):
            return True
        if re.search(r'\b(?:coach|manager|captain|goalkeeper)\s+(?:of|for)\s+$', before):
            return True
        if name in {'usmnt', 'uswnt'}:
            return True
    for index, left in enumerate(mentions):
        for right in mentions[index+1:]:
            if left[2] == right[2] or right[0] - left[1] > 140:
                continue
            between = text[left[1]:right[0]]
            if re.fullmatch(r"\s*(?:v\.?|vs\.?|versus|against)\s+", between):
                return True
            if re.search(r'\b(?:beat|beats|beaten|defeat|defeats|defeated|draw|drew|'
                         r'face|faces|faced|hosts?|plays?|meets?|take on|takes on)\b', between):
                if re.search(r'\b(?:defender|striker|midfielder|forward|club|transfer|signs?|joins?)\b', between):
                    continue
                return True
            if (re.search(r'\b(?:victory|win|loss|defeat|match|friendly|rotation)\b', between)
                    and re.search(r'\b(?:against|over|to|versus|vs|for)\b', between)):
                if not re.search(r'\b(?:immigration|government|trade|war|policy|club)\b', between):
                    return True
            if re.fullmatch(r'\s+and\s+', between) and re.match(
                r'\s+(?:prepare|prepares|preparing|ready|set)\b.{0,55}\b(?:match|friendly|football|soccer)\b', text[right[1]:]):
                return True
    return False


def general_football_governance(title: str, summary: str) -> bool:
    """Explicit club/international governance, not an invented league label."""
    text = _plain(str(title or '') + ' ' + str(summary or ''))
    return bool(re.search(r'\b(?:european clubs?|football clubs?|football federation|fifa|uefa|efc|uc3)\b', text)
                and re.search(r'\b(?:governance|leadership|regulation|regulations|assembly|election)\b', text))
