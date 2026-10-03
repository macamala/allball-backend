"""Conservative identity of a completed football draw, not a result authority.

Only compare already supplied prose. Two named participants, an explicit draw
report, and at least two independently named scorers must agree. This does not
merge interviews, previews, analysis, changed scores, age groups or competitions.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from .news_football_subjects import literal_country_mentions

_EXCLUSIONS = re.compile(r'\b(?:says?|said|react\w*|praises?|criticis\w*|criticiz\w*|'
    r'manager|coach|fans?|ratings?|analysis|preview|predict\w*|injur\w*|'
    r'appeal\w*|disciplin\w*|sanction\w*|investigat\w*|could|might|may|'
    r'will|would|should|expected|denies|not|no|highlights?|watch|quiz|ticket\w*)\b')
_NAME = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]{1,30}(?:[’'-][A-ZÀ-ÖØ-Þ]?[a-zà-öø-ÿ]+)?"
_NAMES = re.compile(r'(?<![\w])(' + _NAME + r'(?:\s+' + _NAME + r'){0,2})')
_ACTION = re.compile(r"^(?:[’']s\s+goal\b|\s+(?:(?:then|later|also|to|had|has)\s+){0,3}"
    r"(?:scored?\b|scoring\b|equalis(?:ed|ing)\b|equaliz(?:ed|ing)\b|level(?:s|led)?\b|"
    r"restored\s+parity\b|put\b[^.!?,;]{0,35}\bahead\b))", re.I)
_SCORE = re.compile(r'(?<![\w\d-])(\d{1,2})\s*[:–-]\s*(\d{1,2})(?![\w\d-])')

class DrawReport(NamedTuple):
    participants: tuple[str, str]
    category: tuple[str, str]
    scorers: frozenset[str]
    scores: frozenset[tuple[str, str]]
    competition: str | None


def _plain(text):
    value = unicodedata.normalize('NFKD', str(text or '')).casefold()
    return ''.join(c for c in value if not unicodedata.combining(c))


def draw_report_signature(title: str, body: str) -> DrawReport | None:
    """Unknown prose or an ambiguous main event produces no signature."""
    headline = _plain(title)
    if not headline or not body or _EXCLUSIONS.search(headline):
        return None
    if not re.search(r'\b(?:draw|drew|share(?:d)? (?:the )?points|stalemate)\b', headline):
        return None
    participants = literal_country_mentions(title)
    names = {item[2] for item in participants}
    if len(names) != 2 or min(item[0] for item in participants) != 0:
        return None
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', str(body)) if p.strip()]
    if not paragraphs:
        return None
    opening = paragraphs[0]
    # A reaction whose headline omits its speaker remains an interview, not
    # an interchangeable match recap. Secondary quotes can stay separate too.
    if re.search(r'\b(?:said|says|noted|expressed|told|praised|described)\b', _plain(opening)):
        return None
    lead = _plain(title + '\n' + opening)
    if not re.search(r'\b(?:held|ended|drew|draw|shared? (?:the )?points|equalis\w*|equaliz\w*|'
                     r'restored parity|cancelled out|canceled out)\b', lead):
        return None
    if re.search(r'\b(?:futsal|beach soccer|blind football|amputee|deaf football)\b', lead):
        return None
    gender = 'women' if re.search(r"\b(?:women(?:['’]s)?|female|ladies)\b", lead) else 'unmarked'
    ages = set(re.findall(r'\b(?:u\s*|under[ -]?)(\d{1,2})s?\b', lead))
    if len(ages) > 1:
        return None
    age = next(iter(ages)) if ages else 'unmarked'
    copy = '\n\n'.join(paragraphs[:2])[:5000]
    scorers = set()
    for match in _NAMES.finditer(copy):
        if _ACTION.search(copy[match.end():match.end()+90]):
            name = _plain(match[1].split()[-1])
            if name not in names and name not in {'the', 'he', 'she', 'it', 'they'}:
                scorers.add(name)
    if not 2 <= len(scorers) <= 4:
        return None
    scores = frozenset(_SCORE.findall(title + '\n' + opening))
    # Only a single explicitly drawn main score. A leading secondary result
    # makes this too ambiguous to identify automatically.
    if len(scores) > 1 or any(left != right for left, right in scores):
        return None
    from .news_football_sections import _explicit, _norm
    competition = _explicit(_norm(title + '\n' + opening), women=gender=='women', youth=age!='unmarked')
    return DrawReport(tuple(sorted(names)), (gender, age), frozenset(scorers), scores, competition)


def same_draw_report(left: DrawReport | None, right: DrawReport | None,
                     left_time: datetime | None, right_time: datetime | None) -> bool:
    if left is None or right is None or not isinstance(left_time, datetime) or not isinstance(right_time, datetime):
        return False
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if abs(utc(left_time)-utc(right_time)) > timedelta(hours=24):
        return False
    if left.participants != right.participants or left.category != right.category:
        return False
    if left.competition and right.competition and left.competition != right.competition:
        return False
    if left.scores and right.scores and left.scores != right.scores:
        return False
    shared = left.scorers & right.scorers
    return len(shared) >= 2 and len(shared) / max(len(left.scorers), len(right.scorers)) >= 2/3
