"""Source-only count spellings observed in Portuguese football reporting.

This recognises an explicitly stated unit, not a new estimate or conversion.
It must not be applied to drafts: the independent factual validator remains
mandatory and still checks who, what, when, units and the surrounding claim.
"""
from __future__ import annotations

import re

# Audited ge.globo.com Sion stadium report, 2026-10-04:
# "21 mil torcedores" and "14 mil torcedores". Keep the numeral atomic;
# never interpret a decimal, score, interval, money amount or season as this
# count. There is intentionally no millions/billions or currency handling.
_PORTUGUESE_PEOPLE = re.compile(
    r'(?<![\w.,:/+\-–£$€])([1-9][0-9]{0,2})\s+mil\s+'
    r'(?:torcedores|espectadores|pessoas|assentos|lugares)(?!\w)', re.I
)


def portuguese_count_equivalents(text: str) -> set[str]:
    """Return only exact decimal spellings of explicit thousand-person counts."""
    values: set[str] = set()
    for match in _PORTUGUESE_PEOPLE.finditer(str(text or '')):
        before = str(text or '')[max(0, match.start() - 20):match.start()]
        # Even malformed currency/percentage/range strings must fail closed.
        if re.search(r'(?:[£$€%:/+\-–]|\d[.,])\s*$', before):
            continue
        count = int(match[1]) * 1000
        values.update((str(count), format(count, ',')))
    return values
