"""Literal headline subject evidence for football News; no membership guesses."""
from __future__ import annotations
import re
import unicodedata

def _plain(text):
    value = unicodedata.normalize('NFKD', str(text or '')).casefold()
    return ''.join(c for c in value if not unicodedata.combining(c))

# Literal participant names, not nationality, membership or fixture inference.
_COUNTRIES = (
    'France', 'Italy', 'England', 'Spain', 'Germany', 'Portugal', 'Serbia',
    'Croatia', 'Belgium', 'Turkey', 'Netherlands', 'Switzerland', 'Sweden',
    'Norway', 'Denmark', 'Finland', 'Poland', 'Austria', 'Hungary', 'Romania',
    'Bulgaria', 'Scotland', 'Wales', 'Ireland', 'Northern Ireland',
    'Czechia', 'Czech Republic', 'Slovakia', 'Slovenia', 'Greece', 'Iceland',
    'Brazil', 'Argentina', 'Uruguay', 'Colombia', 'Chile', 'Ecuador', 'Peru',
    'Mexico', 'Canada', 'United States', 'Japan', 'South Korea', 'Australia',
    'New Zealand', 'China', 'India', 'Saudi Arabia', 'Iran', 'Uzbekistan',
    'Egypt', 'Morocco', 'Algeria', 'Tunisia', 'Nigeria', 'Senegal', 'South Africa',
)
_COUNTRIES += ('Ukraine','Georgia','Armenia','Azerbaijan','Israel','Palestine',
    'Bosnia and Herzegovina','Montenegro','North Macedonia','Kosovo','Belarus',
    'Kazakhstan','Estonia','Latvia','Lithuania','Malta','Cyprus','Luxembourg',
    'Iraq','Qatar','United Arab Emirates','Indonesia','Malaysia','Thailand','Vietnam',
    'Jamaica','Honduras','Costa Rica','Panama','El Salvador','Guatemala','Cuba',
    'Ghana','Cameroon','Mali','Guinea','Gabon','Cape Verde','Cabo Verde','Congo',
    'DR Congo','Democratic Republic of Congo','Zambia','Zimbabwe','Uganda','Kenya')

def literal_country_mentions(title):
    lower = _plain(title)
    matches = []
    for name in _COUNTRIES:
        for match in re.finditer(r'(?<!\w)' + re.escape(_plain(name)) + r'(?!\w)', lower):
            matches.append((match.start(), match.end(), _plain(name)))
    # Northern Ireland cannot also count as Ireland in the same phrase.
    matches = [m for m in matches if not any(n[0] <= m[0] and n[1] >= m[1]
               and n[1]-n[0] > m[1]-m[0] for n in matches)]
    return matches


def headline_national_fixture(title: str) -> bool:
    """An explicit country-v-country headline outranks a player's club bio.

    Starts with the country and a sporting verb/qualifier. 'Austria Vienna'
    and 'Canada Soccer appoints...' are not country-v-country match headlines.
    This is an editorial section hint; no score or fixture is generated.
    """
    text = _plain(title)
    mentions = literal_country_mentions(title)
    if len({m[2] for m in mentions}) != 2:
        return False
    first = min(mentions, key=lambda m: (m[0], -m[1]))
    if first[0] != 0:
        return False
    tail = text[first[1]:].lstrip()
    if not re.match(r"(?:(?:men|women)(?:['’]s)?\s+|u[ -]?\d{1,2}\s+|under[ -]\d{1,2}\s+)?"
                    r"(?:face|faces|faced|host|hosts|visit|visits|play|plays|meet|meets|"
                    r"take|takes|beat|beats|defeat|defeats|draw|drew|held|lose|loses|"
                    r"seek|seeks|aim|aims|prepare|prepares|ready|set|look|looks|"
                    r"win|wins|fall|falls|share|shares|secure|secures|and|v|vs|versus)\b",tail):
        return False
    # Merely comparing two nations in a policy story is not a match.
    return bool(re.search(r'\b(?:against|versus|vs|face|faces|faced|host|hosts|visit|visits|'
                          r'beat|beats|defeat|defeats|meet|meets|draw|drew|stalemate|share(?:d)? points)\b',tail))
