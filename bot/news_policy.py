"""Deterministic News admission checks. Heuristics, not fact/rights certification."""
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTC = timezone.utc
TRACKING = {'fbclid', 'gclid', 'mc_cid', 'mc_eid'}
_NAME_START_STOP = {'The','This','That','These','Those','After','Before','With','When','While','But','And','For','From','Into','During'}
_PROPER_NAME_RE = re.compile(
    r"\\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,})(?:\\s+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}|de|da|del|di|la|le|van|von)){1,4}\\b"
)


def protected_proper_names(text):
    """Conservative multi-word names that automated copy must preserve exactly."""
    output = []
    seen = set()
    for match in _PROPER_NAME_RE.finditer(text or ''):
        value = match.group(0).strip()
        first = value.split()[0]
        key = value.casefold()
        if first in _NAME_START_STOP or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def canonical_news_url(value):
    if not isinstance(value, str): return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
            return None
        if parts.port not in (None, 80, 443): return None
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in TRACKING]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', urlencode(query), ''))
    except ValueError:
        return None


def publication_time(stamp):
    # Deliberately do not convert timezone-naive metadata to invented UTC.
    if not isinstance(stamp, datetime) or stamp.tzinfo is None: return None
    try: return stamp.astimezone(UTC)
    except (ValueError, OverflowError): return None


def freshness_reason(stamp, now, max_age_hours=72):
    value = publication_time(stamp)
    if value is None: return 'publication_time_unverified'
    if value > now: return 'future_publication'
    if now - value > timedelta(hours=max_age_hours): return 'stale_publication'
    return None


def fair_news_queue(items, classify, *, now=None, max_age_hours=72, sport_order=()):
    """Newest per sport, then round robin; classify evidence before spending AI.

    Rotate starting sport across time slots so a small per-cycle budget does not
    permanently favor alphabetically early sports. No source date is changed.
    """
    now = now or datetime.now(UTC)
    buckets = defaultdict(list)
    rejected = defaultdict(int)
    seen = set()
    for item in items:
        reason = freshness_reason(item.get('published_at'), now, max_age_hours)
        url = canonical_news_url(item.get('url'))
        if reason or not url:
            rejected[reason or 'invalid_source_url'] += 1; continue
        if url in seen:
            rejected['duplicate_source_url'] += 1; continue
        tags = classify(item)
        sport = getattr(tags, 'sport', None)
        if not sport:
            rejected['unknown_sport'] += 1; continue
        seen.add(url)
        # Retain exact source URL for provenance and existing database identity.
        buckets[sport].append(item)
    order = [s for s in sport_order if s in buckets]
    order += sorted(set(buckets) - set(order))
    if order:
        offset = int(now.timestamp() // 600) % len(order)
        order = order[offset:] + order[:offset]
    queues = {s: deque(sorted(buckets[s], key=lambda x: publication_time(x['published_at']), reverse=True)) for s in order}
    output = []
    while any(queues.values()):
        for s in order:
            if queues[s]: output.append(queues[s].popleft())
    return output, dict(rejected)


def original_draft_reason(draft, source_title, source_body):
    """Conservative automated draft gate; passing is NOT editorial verification."""
    if not isinstance(draft, dict): return 'missing_original_draft'
    title, summary, body = (draft.get(k) for k in ('title', 'summary', 'body'))
    if not all(isinstance(x, str) and x.strip() for x in (title, summary, body)):
        return 'missing_original_draft'
    source = f'{source_title}\n{source_body}'
    output = f'{title}\n{summary}\n{body}'
    if re.search(r'https?://|www\.', output, re.I): return 'external_link_in_copy'
    if re.search(r'read (?:the )?(?:full|original) (?:story|article)|appeared first on', output, re.I):
        return 'publisher_redirect_copy'
    if re.search(r'(?im)^\s*(?:source|sources|powered by|originally published)\s*:', output):
        return 'publisher_footer'
    # Do not rewrite a source quote into an invented quote. For this automated
    # path use paraphrase with necessary in-sentence attribution instead.
    if re.search(r'[“\"]([^”\"\n]{8,})[”\"]', output): return 'direct_quote_requires_review'
    numbers = lambda text: set(re.findall(r'(?<!\w)\d+(?:[.,:/–-]\d+)*(?:%|\b)', text))
    if numbers(output) - numbers(source): return 'unsupported_number'
    folded_output = output.casefold()
    for name in protected_proper_names(source):
        if name.casefold() not in folded_output:
            return 'missing_or_changed_proper_name'
    tokens = lambda text: re.findall(r"[\w]+", text.lower())
    src, dst = tokens(source_body), tokens(body)
    if len(dst) < 25: return 'insufficient_original_body'
    if src == dst: return 'copied_source_body'
    n = 8
    grams = {tuple(src[i:i+n]) for i in range(max(0, len(src)-n+1))}
    copied = sum(tuple(dst[i:i+n]) in grams for i in range(max(0, len(dst)-n+1)))
    if copied / max(1, len(dst)-n+1) > 0.20: return 'excessive_source_overlap'
    if len(src) >= 180 and len(dst) < 140: return 'summary_only_rewrite'
    if len(dst) >= 140 and len([p for p in body.split('\n\n') if p.strip()]) < 2:
        return 'missing_paragraph_structure'
    return None
