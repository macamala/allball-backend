"""Fail-closed factual guard for AI-written News drafts.

This module is deliberately deterministic. It does not ask the same writer to
judge itself and it never turns a failed check into permission to publish.
Passing these checks is not proof of truth; it is an additional barrier against
unsupported facts before publication.
"""
from __future__ import annotations

import re
from typing import Optional

from entities import extract_entities
from .news_policy import original_draft_reason

MONTHS_DAYS = {
    "january","february","march","april","may","june","july","august",
    "september","october","november","december",
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
}
COMMON_CAPITALIZED = {
    "The","A","An","This","That","These","Those","After","Before","During",
    "Meanwhile","However","While","With","Without","For","From","In","On","At",
    "As","By","It","He","She","They","We","His","Her","Their","Club","Team",
    "League","Championship","World","Cup","Final","Finals","Season","News",
}
CLAIM_FAMILIES = {
    "transfer": (
        " transfer "," signed "," signing "," contract "," loan "," fee ",
        " release clause "," bid "," move to "," joins "," joined ",
    ),
    "injury": (
        " injury "," injured "," surgery "," hamstring "," ankle "," knee ",
        " concussion "," ruled out "," sidelined ",
    ),
    "discipline": (
        " suspended "," suspension "," banned "," ban "," red card ",
        " sent off "," disciplinary ",
    ),
    "result": (
        " beat "," beats "," defeated "," defeat "," victory "," won ",
        " wins "," draw "," drew "," final score "," finished ",
    ),
    "retirement": (
        " retired "," retirement "," retires ",
    ),
    "death": (
        " died "," death "," dead "," passed away ",
    ),
    "appointment": (
        " appointed "," appointment "," named coach "," named manager ",
        " sacked "," fired "," dismissed ",
    ),
}

PROPER_PHRASE_RE = re.compile(
    r"\b(?:[A-Z][A-Za-zÀ-ÿ0-9'’.-]{2,})(?:\s+[A-Z][A-Za-zÀ-ÿ0-9'’.-]{2,}){1,3}\b"
)
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")


def _norm(text: str) -> str:
    lowered = (text or "").lower().replace("’", "'")
    return " " + " ".join(re.findall(r"[a-z0-9à-ÿ'+.-]+", lowered)) + " "


def _contains_any(blob: str, terms) -> bool:
    return any(term in blob for term in terms)


def _unsupported_known_entities(source: str, output: str) -> list[str]:
    src = extract_entities(extra=source).all_ids
    dst = extract_entities(extra=output).all_ids
    return sorted(dst - src)


def _proper_phrases(text: str) -> set[str]:
    found = set()
    for match in PROPER_PHRASE_RE.finditer(text or ""):
        phrase = match.group(0).strip()
        words = phrase.split()
        if not words or all(word in COMMON_CAPITALIZED for word in words):
            continue
        found.add(_norm(phrase).strip())
    return found


def _acronyms(text: str) -> set[str]:
    ignored = {"USD", "GMT", "UTC", "TV", "AI"}
    return {m.group(0) for m in ACRONYM_RE.finditer(text or "") if m.group(0) not in ignored}


def fact_lock_reason(
    draft: dict,
    source_title: str,
    source_body: str,
    *,
    expected_sport: Optional[str] = None,
) -> Optional[str]:
    """Return a stable reason code when the draft introduces unsupported facts.

    Existing originality/number/quote checks remain authoritative and run first.
    Extra checks cover known entities, multi-word proper names, acronyms,
    calendar words and high-risk claim families.
    """
    base = original_draft_reason(draft, source_title, source_body)
    if base:
        return base
    output = "\n".join(
        str(draft.get(key) or "") for key in ("title", "summary", "body")
    )
    source = f"{source_title or ''}\n{source_body or ''}"

    unsupported = _unsupported_known_entities(source, output)
    if unsupported:
        return "unsupported_known_entity:" + unsupported[0]

    src_phrases = _proper_phrases(source)
    for phrase in sorted(_proper_phrases(output) - src_phrases):
        # A long multi-word proper name is rarely safe to invent during rewrite.
        if len(phrase.split()) >= 2:
            return "unsupported_proper_name:" + phrase[:80]

    src_acronyms = _acronyms(source)
    extra_acronyms = sorted(_acronyms(output) - src_acronyms)
    if extra_acronyms:
        return "unsupported_acronym:" + extra_acronyms[0]

    src_norm = _norm(source)
    out_norm = _norm(output)
    src_calendar = {term for term in MONTHS_DAYS if f" {term} " in src_norm}
    for term in sorted({term for term in MONTHS_DAYS if f" {term} " in out_norm} - src_calendar):
        return "unsupported_time_reference:" + term

    for family, terms in CLAIM_FAMILIES.items():
        if _contains_any(out_norm, terms) and not _contains_any(src_norm, terms):
            return "unsupported_claim_family:" + family

    if expected_sport:
        tags = extract_entities(extra=output)
        _ = tags  # reserved for future sport-specific entity locks
    return None
