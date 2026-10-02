"""News-only protection for ambiguous competition labels; no sports data writes.

An AFC/CAF/CONCACAF label must not provide evidence for UEFA just because both
contain "Champions League". The original article's exact qualifier is retained.
"""
import re
import unicodedata


def _normalized(value):
    value = unicodedata.normalize('NFKD', str(value or '')).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^\w]+', ' ', value).strip()


def conflicting_competition_qualifier(competition, text, start, end):
    """True only when an immediately attached qualifier contradicts the alias.

    This is a rejection rule, never evidence that an alternative competition
    has been identified. It does not use club geography or a publisher name.
    """
    before = _normalized(text[max(0, start-70):start])
    after = _normalized(text[end:end+60])
    label = _normalized(text[start:end])
    if competition.startswith('uefa-'):
        if re.search(r'\b(?:afc|caf|concacaf|ofc|asian|african|oceania)(?: women s| womens)?$', before):
            return True
        if competition == 'uefa-champions-league' and label in {'champions league', 'ucl'}:
            if re.match(r'^(?:elite|two|2|afc|caf|concacaf|ofc)\b', after):
                return True
    # These qualifiers are part of the event identity, not optional words.
    if competition in {'uefa-champions-league','uefa-nations-league','fifa-world-cup'}:
        if re.search(r'\b(?:women s|womens|women|youth|under \d{2}|u ?\d{2})$', before):
            return True
        if re.match(r'^(?:women|womens|women s|under \d{2}|u ?\d{2})\b', after):
            return True
    if competition == 'fifa-world-cup' and re.search(r'\bclub$', before):
        return True
    return False
