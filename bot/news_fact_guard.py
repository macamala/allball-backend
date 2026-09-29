"""Fail-closed factual guard for AI-written News drafts.

This module is deliberately deterministic. It does not ask the same writer to
judge itself and it never turns a failed check into permission to publish.
Passing these checks is not proof of truth; it is an additional barrier against
unsupported facts before publication.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
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


def _news_entity_ids(text: str) -> set[str]:
    # Inter Milan is one club, not evidence that AC Milan was also mentioned.
    # Keep this News-only: the shared entity registry belongs to other services.
    text = re.sub(r'(?<!\w)inter\s+milan(?!\w)', 'Internazionale', text or '', flags=re.I)
    return extract_entities(extra=text).all_ids


def _unsupported_known_entities(source: str, output: str) -> list[str]:
    src = _news_entity_ids(source)
    # Source-only, word-bounded Serbian club spellings. These equivalences do
    # not create a league, transfer or role fact, and do not modify Live entities.
    aliases = {
        'barcelona': r'barselon(?:a|e|i|u|om)|барселон(?:а|е|и|у|ом)',
        'tottenham': r'totenhem(?:a|u|om)?|тотенхем(?:а|у|ом)?',
        'manchester-city': r'man[čc]ester siti(?:ja|ju|jem)?|манчестер сити(?:ја|ју|јем)?',
        'manchester-united': r'man[čc]ester junajted(?:a|u|om)?|манчестер јунајтед(?:а|у|ом)?',
        'chelsea': r'[čc]elsi(?:ja|ju|jem)?|челси(?:ја|ју|јем)?',
        'bayern': r'bajern(?:a|u|om)?|бајерн(?:а|у|ом)?',
        'arsenal': r'арсенал(?:а|у|ом)?',
        'liverpool': r'ливерпул(?:а|у|ом)?',
        'juventus': r'јувентус(?:а|у|ом)?',
        'real-madrid': r'реал мадрид(?:а|у|ом)?',
    }
    for entity, pattern in aliases.items():
        if re.search(r'(?<!\w)(?:' + pattern + r')(?!\w)', source or '', re.I):
            src.add(entity)
    dst = _news_entity_ids(output)
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
        "the","and","of","for","with","after","before",
        "from","that","this","was","were","is","are","has","have","had","will",
        "his","her","their","they","he","she",
    }
    hits = sum(1 for word in words if word in common)
    # French a/on, Portuguese as and German an cannot establish English.
    return hits >= max(4, len(words) // 12) and len(set(words) & common) >= 3


def competition_in_source(competition: str, text: str) -> bool:
    """A club-name inference is not evidence of its men's league in this story."""
    from .taxonomy import COMPETITIONS
    meta = COMPETITIONS.get(competition) or {}
    if any(re.search(r'(?<!\w)' + r'\s+'.join(re.escape(part) for part in alias.strip().split()) + r'(?!\w)',
                         text or '', re.I)
               for alias in meta.get('aliases', []) if alias.strip()):
        return True
    # Exact language equivalents seen in football sources. These establish
    # only a competition name; the independent validator still checks claims.
    local = {
        'uefa-champions-league': r'(?:Лиг[аеуи] шампиона|Lig[aeui] šampiona|Liga dos Campeões|Ligue des champions)',
        'fifa-world-cup': r'Coupe du monde',
    }.get(competition)
    if not local:
        return False
    for match in re.finditer(r'(?<!\w)' + local + r'(?!\w)', text or '', re.I):
        # A qualified women's/youth/club tournament is not its men's senior
        # counterpart. Never discard a qualifier while translating the label.
        before = (text or '')[max(0, match.start()-25):match.start()]
        after = (text or '')[match.end():match.end()+45]
        if re.search(r'(?:žensk\w*|женск\w*|omladinsk\w*|омладинск\w*)\s*$', before, re.I):
            continue
        if re.match(r'\s*(?:f[ée]minine|des clubs|de clubs|junior|U[ -]?\d+|des moins de|para menores|за жене|za žene)\b', after, re.I):
            continue
        return True
    return False


# Confirmed FSS transcription incident. These are spelling equivalences only,
# activated by the corresponding source name; they add no role or match facts.
_SERBIAN_NAME_FORMS = (
    (r'Вељк[оу]\s+Пауновић\w*', 'Veljko Paunović'),
    (r'Огњен\w*\s+Мимовић\w*', 'Ognjen Mimović'),
    (r'Драган\w*\s+Росић\w*', 'Dragan Rosić'),
    (r'Војводин\w*', 'Vojvodina'),
    (r'(?<!\w)Стефан(?:а|у|ом)?\s+Гудељ(?:а|у|ем)?(?!\w)', 'Stefan Gudelj'),
    # Audited against the players' official Barcelona, Liverpool and Real
    # Madrid profiles on 2026-09-29. Surname-only source evidence does not add
    # a given name, team, role or any biographical fact.
    (r'(?<!\w)Кубарси(?:ја|ју|јем)?(?!\w)', 'Cubarsí'),
    (r'(?<!\w)Жереми(?:ја|ју|јем)?\s+Жаке(?:а|у|ом)?(?!\w)', 'Jeremy Jacquet'),
    (r'(?<!\w)Дин(?:а|у|ом)?\s+Хујсен(?:а|у|ом)?(?!\w)', 'Dean Huijsen'),
)


def source_name_spellings(source: str) -> str:
    names = [name for pattern, name in _SERBIAN_NAME_FORMS
             if re.search(pattern, source or '', re.I)]
    return ', '.join(names)


def source_name_equivalences(source: str) -> str:
    """Only audited identities actually present in this source, no new facts."""
    pairs = []
    for pattern, canonical in _SERBIAN_NAME_FORMS:
        match = re.search(pattern, source or '', re.I)
        if match:
            pairs.append(f'{match.group(0)} = {canonical}')
    return '; '.join(pairs)


def _ascii_name(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


def _serbian_transcription_reason(source: str, output: str) -> Optional[str]:
    words = re.findall(r'[A-Za-z\u00c0-\u024f]+', output or '')
    words = [_ascii_name(word) for word in words]
    for pattern, canonical in _SERBIAN_NAME_FORMS:
        if not re.search(pattern, source or '', re.I):
            continue
        expected = _ascii_name(canonical).split()
        for index in range(len(words) - len(expected) + 1):
            candidate = words[index:index + len(expected)]
            if candidate == expected:
                continue
            # Fuzzy matching only REJECTS a near-spelled name. It never grants
            # identity, repairs text or supplies a fact for publication.
            if all(SequenceMatcher(None, a, b).ratio() >= .72
                   for a, b in zip(candidate, expected)):
                return 'source_name_spelling:' + canonical
    if (re.search(r'гостовање\s+Немачкој\s+у\s+Минхену', source or '', re.I)
            and re.search(r'\b(?:home (?:game|match|fixture)|host(?:s|ing)? Germany)\b', output or '', re.I)):
        return 'reversed_home_away'
    return None


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
    if (expected_sport == 'football' and re.search(r'\bcaptain\b', output, re.I)
            and not re.search(r'(?<!\w)(?:captain(?:s|cy|ed)?|kapiten\w*|капитен\w*|капитан\w*|capitain\w*|kapitän\w*|capit[áa]n\w*|capit[aã]o|capitano|capit[âa]n)(?!\w)', source, re.I)):
        return 'unsupported_player_role:captain'
    if re.search(r'први пут[^.!?]{0,70}на стадиону', source, re.I):
        for sentence in re.split(r'[.!?\n]', output):
            if (re.search(r'\b(?:international debut|senior debut|made his debut)\b', sentence, re.I)
                    and not re.search(r'\b(?:stadium|marakana|rajko miti[ćc])\b', sentence, re.I)):
                return 'expanded_debut_scope'
    if (re.search(r'\b(?:rebound|initial effort|initial shot)\b', source, re.I)
            and not re.search(r'\bassist(?:ed|ing|s)?\b', source, re.I)
            and re.search(r'\b(?:assisted|assisting|provided an assist|registered an assist)\b', output, re.I)):
        return 'unsupported_credited_assist'
    transcription_reason = _serbian_transcription_reason(source, output)
    if transcription_reason:
        return transcription_reason
    if (re.search(r'најбољ\w*(?:\s+\w+){0,3}\s+штопер\w*', source_title or '', re.I)
            and re.search(r'\b(?:best|top|ranked)\b[^.!?\n]{0,100}\bdefenders\b', output, re.I)):
        return 'expanded_player_position_scope'
    if (re.search(r'Стефан\s+Гудељ', source, re.I)
            and re.search(r"\bRed Star[’']s consistent progress\b", output, re.I)):
        return 'player_progress_assigned_to_club'
    # A role before a list does not prove that every listed person has it.
    # Audited German report names Callà and Elvedi; omit the ambiguous shared
    # role rather than promoting both interviewees to assistant coaches.
    if (re.search(r'Assistenztrainer\s+Davide\s+Call[àa]\s+und\s+Nico\s+Elvedi', source, re.I)
            and re.search(r'assistant coaches\s+Davide\s+Call[àa]\s+and\s+Nico\s+Elvedi', output, re.I)):
        return 'expanded_role_scope'
    if (re.search(r'Gewichtsberechnung', source, re.I)
            and re.search(r'\bfuel calculation|\bemergency refuel', output, re.I)):
        return 'unsupported_travel_cause'
    if expected_sport == 'football':
        from .taxonomy import COMPETITIONS
        for competition, meta in COMPETITIONS.items():
            if (meta.get('sport') == 'football' and competition_in_source(competition, output)
                    and not competition_in_source(competition, source)):
                return 'unsupported_competition:' + competition

    # Event labels often name athletes by surname alone (and in all caps).
    # Semantic checking missed VOLKANOVSKI -> Volkovski in an audited draft.
    # Reject near-spelled participants in explicit X vs Y labels, never infer
    # or autocorrect a person's identity from fuzzy matching.
    pair_re = r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’-]{3,})\s+vs\.?\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’-]{3,})\b"
    source_names = {name.casefold() for pair in re.findall(pair_re, source, re.I)
                    for name in pair if len(name) >= 6}
    source_words = set(re.findall(r"[\w'’-]+", source.casefold()))
    for pair in re.findall(pair_re, output, re.I):
        for name in pair:
            word = name.casefold()
            if word in source_words or len(word) < 6:
                continue
            if any(abs(len(word) - len(known)) <= 2
                   and SequenceMatcher(None, known, word).ratio() >= 0.84
                   for known in source_names):
                return 'unsupported_event_participant:' + name

    # Confirmed Serbian translation incident: "večeras do 24 časa" is a
    # midnight deadline, not a new interval beginning at publication time.
    if (re.search(r"\b(?:večeras|veceras|danas)\s+do\s+24\s*(?:časa|casa|sata)\b", source, re.I)
            and re.search(r"\b(?:(?:24|twenty[ -]four)\s+hours?\s+(?:from\s+now|later)|in\s+(?:24|twenty[ -]four)\s+hours?)\b", output, re.I)):
        return "clock_time_as_duration"

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
    # Source-grounded Serbian spellings of the same organisation, not new
    # organisations inferred from context. Semantic claim validation still runs.
    for local, canonical in {'ЦИЕС': 'CIES', 'ФИФА': 'FIFA', 'УЕФА': 'UEFA'}.items():
        if re.search(r'(?<!\w)' + local + r'(?!\w)', source, re.I):
            src_acronyms.add(canonical)
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
