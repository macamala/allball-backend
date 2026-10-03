"""Conservative News-only handling of ambiguous club names.

An ordinary word is not evidence of a club. This rejection rule supplies no
alternative league, membership or sporting fact and performs no I/O.
"""
import re

_COMO = re.compile(
    r'\b(?:como (?:1907|fc|calcio)|(?:fc|club|calcio) como|'
    r'como s (?:coach|manager|goalkeeper|defender|midfielder|striker|forward|squad)|'
    r'como (?:signs?|signed|appoints?|appointed|confirms?|confirmed|announces?|announced|'
    r'beats?|defeats?|hosts?|faces?|wins?|lost|lose|draws?)\b)'
)

def ambiguous_club_has_evidence(alias, normalized_text):
    """Require club-specific context for Como, also a common Portuguese word."""
    return alias != 'como' or bool(_COMO.search(normalized_text or ''))
