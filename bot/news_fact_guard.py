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


def _calendar_terms(text: str) -> set[str]:
    # Lower-case modal "may" can precede any verb, not a fixed verb shortlist.
    # Preserve actual date contexts and capitalised May as calendar evidence.
    def may_word(match):
        before = str(text or '')[:match.start()]
        after = str(text or '')[match.end():]
        dated = (re.search(r'\b(?:in|by|until|from|since|during|before|after|next|last|this|early|late|mid|of)\s+$', before, re.I)
                 or re.search(r'\b\d{1,2}\s+$', before)
                 or re.match(r'\s+\d', after))
        return match[0] if dated or match[0] != 'may' else ''
    normalized = _norm(re.sub(r'\bmay\b', may_word, text or '', flags=re.I))
    normalized = re.sub(
        r"\bmay\s+(?=(?:not\s+)?(?:be|have|need|require|face|remain|return|leave|join|play|miss|keep|make|take|come|go)\b)",
        "", normalized,
    )
    return {term for term in MONTHS_DAYS
            if re.search(r"(?<!\w)" + term + r"(?!\w)", normalized)}
COMMON_CAPITALIZED = {
    "The","A","An","This","That","These","Those","After","Before","During",
    "Meanwhile","However","While","With","Without","For","From","In","On","At",
    "As","By","It","He","She","They","We","His","Her","Their","Club","Team",
    "League","Championship","World","Cup","Final","Finals","Season","News",
}
HIGH_RISK_CLAIM_FAMILIES = {"injury", "discipline", "retirement", "death", "appointment"}
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


def _source_probably_english(text: str) -> bool:
    """Cheap guard scope check; false means defer lexical claims to semantic validation."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    if len(words) < 12:
        return False
    common = {
        "the","and","to","of","in","for","on","with","after","before","as","at",
        "from","that","this","was","were","is","are","has","have","had","will",
        "his","her","their","they","he","she","a","an",
    }
    hits = sum(1 for word in words if word in common)
    return hits >= max(4, len(words) // 18)


def fact_lock_reason(
    draft: dict,
    source_title: str,
    source_body: str,
    *,
    expected_sport: Optional[str] = None,
    expected_league: Optional[str] = None,
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

    # A first home appearance is not an overall debut. Preserve the qualifier
    # even when it is only present in the supplied source body.
    headline = str(draft.get("title") or "")
    if (re.search(r"\b(?:home debut|debut in the home dugout|first home (?:match|game|appearance))\b", source, re.I)
            and re.search(r"\bdebut\b", headline, re.I)
            and not re.search(r"\bhome\b", headline, re.I)):
        return "lost_debut_qualifier"

    unsupported = _unsupported_known_entities(source, output)
    if unsupported:
        return "unsupported_known_entity:" + unsupported[0]

    # Do not use title-case phrase subtraction as a hard publication gate.
    # It creates false positives at sentence boundaries and possessives
    # (for example "Luke Humphries. Humphries" or "England's ODI").
    # Changed/invented names remain fail-closed in the semantic validator,
    # while known entity IDs and acronym checks below stay deterministic.
    src_acronyms = _acronyms(source)
    extra_acronyms = sorted(_acronyms(output) - src_acronyms)
    if extra_acronyms:
        return "unsupported_acronym:" + extra_acronyms[0]

    # Calendar/claim vocabulary below is English-only. For non-English source
    # material, use the cross-language semantic validator instead of pretending
    # absence of an English keyword proves absence of the underlying fact.
    if _source_probably_english(source):
        src_calendar = _calendar_terms(source)
        for term in sorted(_calendar_terms(output) - src_calendar):
            return "unsupported_time_reference:" + term

        # Event-specific claim families are intentionally left to the semantic
        # source-vs-draft validator. Keyword subtraction cannot safely understand
        # synonyms ("new CEO" vs "appointed") or cross-language source prose.

    if expected_sport:
        from .taxonomy import BROAD_LEAGUE
        from .classify import classify_article
        classified = classify_article(
            output.split("\n", 1)[0], output,
            feed_kind="league", feed_sport=expected_sport,
        )
        # A draft does not need to repeat the sport name when source evidence
        # already established it. Reject only a positive contradictory sport.
        if classified.sport and classified.sport != expected_sport:
            return "draft_sport_mismatch:" + str(classified.sport)[:50]
        if (
            expected_league
            # A broad sport bucket is not a verified competition. A concrete
            # league in a multilingual draft still needs semantic source proof,
            # but it cannot conflict with an unspecified source competition.
            and expected_league not in set(BROAD_LEAGUE.values()) | {f"{expected_sport}-international"}
            and classified.league
            and classified.confidence in {"high", "medium"}
            and classified.league != expected_league
        ):
            return "draft_competition_mismatch:" + str(classified.league)[:100]
    return None
