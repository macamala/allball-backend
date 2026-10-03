r"""Literal source tokens across CJK word boundaries, never inferred facts.

Python's Unicode \w regards ideographs as letters. A word-boundary regexp
therefore misses e.g. 12 in 全治12週間 and splits 2026/27シーズン at the slash.
Only visible decimal digits and explicit width-equivalent punctuation are
normalised. Kanji numbers, circled labels, units and calculations are not.
"""
from __future__ import annotations
import re

_WIDTH = str.maketrans({**{chr(0xFF10+i):str(i) for i in range(10)},
                       **{chr(0xFF21+i):chr(65+i) for i in range(26)},
                       '／':'/', '：':':', '．':'.', '，':',', '％':'%', '－':'-'})
_CJK = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]')
_LEGACY_NUMBERS = re.compile(r'(?<!\w)\d+(?:[.,:/–-]\d+)*(?:%|\b)')
# Match the whole literal first: do not backtrack 2026/27 into two counts.
_NUMBERS = re.compile(r'[0-9]+(?:[.,:/–-][0-9]+)*%?')
_ACRONYMS = re.compile(r'[A-Z]{2,8}')


def _cjk_boundary(text: str, start: int, end: int) -> bool:
    left = text[start-1:start] if start else ''
    right = text[end:end+1]
    if not (_CJK.fullmatch(left) or _CJK.fullmatch(right)):
        return False
    # A Latin identifier remains one identifier, not permission for its suffix.
    return not any(ch and (ch.isalnum() or ch == '_') and not _CJK.fullmatch(ch)
                   for ch in (left, right))


def literal_numeric_tokens(value: str) -> set[str]:
    """Keep existing ASCII behavior, correcting only CJK-adjacent spans.

    The original body is never rewritten; this is a comparison key only.
    Exact number-to-person/event/unit relationships still require validation.
    """
    text = str(value or '')
    normal = text.translate(_WIDTH)  # one code point in, one code point out
    cjk = [m for m in _NUMBERS.finditer(normal) if _cjk_boundary(normal, *m.span())]
    output = {m.group() for m in _LEGACY_NUMBERS.finditer(text)
              if not any(m.start() >= n.start() and m.end() <= n.end() for n in cjk)}
    output.update(m.group() for m in cjk)
    return output


def source_cjk_acronyms(value: str) -> set[str]:
    """Accept FC in 柏エフォートFC, not FC inside FCX or an unrelated club.

    Spelling evidence alone never establishes an entity's identity or role.
    """
    text = str(value or '').translate(_WIDTH)
    return {m.group() for m in _ACRONYMS.finditer(text)
            if _cjk_boundary(text, *m.span())}
