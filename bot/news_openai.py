"""Budgeted OpenAI lane for the existing News pipeline only."""
from __future__ import annotations

import logging
import os
import time
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from functools import wraps

import httpx

logger = logging.getLogger(__name__)
MODEL = 'gpt-6-luna'
API_ROOT = 'https://api.openai.com/v1'
_catalog = (0.0, False)
_context = ContextVar('news_openai_source', default=None)
_cooldown_until = 0.0
_last_status = ContextVar('news_openai_status', default='disabled')
# Official standard-tier USD / million tokens, verified 2026-09-30.
# https://developers.openai.com/api/docs/models/gpt-6-luna
INPUT_PRICE, CACHED_PRICE, WRITE_PRICE, OUTPUT_PRICE = map(
    Decimal, ('0.10', '0.01', '0.125', '0.50'))
MAX_PAYLOAD_BYTES = 32000


def settings():
    """Malformed config disables only this lane. Never select another model."""
    if os.getenv('OPENAI_ENABLED', '').lower() != 'true':
        return None
    if os.getenv('OPENAI_MODEL', MODEL) != MODEL:
        _last_status.set('model_not_allowlisted')
        return None
    if any(os.getenv(k, 'false').lower() != 'false' for k in
           ('OPENAI_EXPENSIVE_MODELS_ENABLED', 'OPENAI_WEB_SEARCH_ENABLED')):
        _last_status.set('forbidden_feature')
        return None
    try:
        values = {}
        for name, default in (('daily', '0.50'), ('monthly', '15.00'), ('total', '15.00')):
            amount = Decimal(os.getenv('OPENAI_' + name.upper() + '_BUDGET_USD', default))
            if not amount.is_finite() or not 0 < amount <= Decimal(default):
                raise ValueError('budget_outside_authorized_limit')
            values[name] = amount
        phase = os.getenv('OPENAI_ROLLOUT_MODE', 'dry_run')
        if phase not in {'dry_run', 'production'}:
            raise ValueError('invalid_rollout_mode')
        if phase == 'production' and os.getenv('OPENAI_PRODUCTION_APPROVED', 'false').lower() != 'true':
            raise ValueError('dry_run_review_required')
        values.update(phase=phase,
            dry_limit=int(os.getenv('OPENAI_DRY_RUN_ARTICLES', '12')),
            cycle_limit=int(os.getenv('OPENAI_MAX_REQUESTS_PER_CYCLE', '2')))
        if not 10 <= values['dry_limit'] <= 20 or not 1 <= values['cycle_limit'] <= 8:
            raise ValueError('invalid_rollout_limit')
        return values
    except (ValueError, ArithmeticError):
        _last_status.set('invalid_config')
        return None


def available():
    return bool(settings() and os.getenv('OPENAI_API_KEY', '').strip()
                and time.monotonic() >= _cooldown_until)


def status():
    return _last_status.get()


def source_key(url):
    return hashlib.sha256(str(url or '').encode()).hexdigest()


@contextmanager
def source_context(item, *, article_id=None):
    status_token = _last_status.set('idle')
    token = _context.set({'source_key': source_key(item.get('url')),
        'article_id': article_id, 'item': item, 'priority': 0, 'verified': False,
        'force_paid': False, 'paid_returned': False, 'request_key': None})
    try:
        yield _context.get()
    finally:
        _context.reset(token)
        _last_status.reset(status_token)


def with_source_context(function):
    @wraps(function)
    def wrapped(db, item, *args, **kwargs):
        with source_context(item):
            return function(db, item, *args, **kwargs)
    return wrapped


def verified_source(item, tags, facts):
    context = _context.get()
    if context is None:
        return
    from .news_football_priority import (football_editorial_priority,
        candidate_football_section, PRIMARY_COMPETITIONS)
    enriched = dict(item, _classification_text=facts)
    priority = football_editorial_priority(enriched, tags)
    if candidate_football_section(enriched, tags) in PRIMARY_COMPETITIONS:
        priority = max(priority, 1)
    context.update(priority=priority, verified=True,
        source_words=len(facts.split()),
        evidence_hash=hashlib.sha256((str(item.get('title') or '') + '\n' + facts).encode()).hexdigest())


def _paid_slot_reserved(config, context):
    """Reserve, never add, one existing paid slot for a waiting empty league."""
    if config.get('phase') != 'production' or context.get('priority', 0) >= 2:
        return False
    from .news_football_capacity import reserve_paid_for_waiting_football
    if not reserve_paid_for_waiting_football():
        return False
    from .news_budget import active_ai_budget
    budget = active_ai_budget()
    if budget is None:
        return False
    remaining = config['cycle_limit'] - getattr(budget, 'openai_attempts', 0)
    return 0 < remaining <= 1


def prefer_paid(*, quality_retry=False):
    context, config = _context.get(), settings()
    if not context or not config or not context['verified']:
        return False
    if _paid_slot_reserved(config, context):
        return False
    return bool(context['force_paid'] or config['phase'] == 'dry_run'
                or (not context['paid_returned'] and (context['priority'] > 0 or quality_retry)))


def forced():
    return bool((_context.get() or {}).get('force_paid'))


@contextmanager
def force_paid():
    context = _context.get()
    if context is None:
        yield
        return
    previous = context['force_paid']
    context['force_paid'] = True
    try: yield
    finally: context['force_paid'] = previous


def paid_was_used():
    return bool((_context.get() or {}).get('paid_returned'))


def current_request_key():
    return (_context.get() or {}).get('request_key')


def shadow_result():
    config = settings()
    return bool(config and config['phase'] == 'dry_run' and paid_was_used())


def record_quality(reason, *, request_key=None):
    context = _context.get() or {}
    key = request_key or context.get('request_key')
    if not request_key and context.get('request_purpose') == 'write':
        from .free_ai_router import last_writer_identity
        # A later free corrective draft must not overwrite the paid draft's
        # own quality verdict in the cost/quality ledger.
        if last_writer_identity()[0] != 'openai':
            return
    if key:
        try:
            from .news_openai_ledger import ledger
            ledger().record_quality(key, reason)
            logger.info('[news-openai] quality=%s request=%s article=%s',
                str(reason)[:160], key[:12], context.get('article_id'))
        except Exception as exc:
            logger.warning('[news-openai] quality_ledger=%s', type(exc).__name__)


def bind_article(article_id):
    context = _context.get() or {}
    if context.get('source_key'):
        try:
            from .news_openai_ledger import ledger
            ledger().bind_article(context['source_key'], article_id)
        except Exception as exc:
            logger.warning('[news-openai] article_binding=%s', type(exc).__name__)


def translation_context(article, source):
    """Existing published English article is the translation's only authority."""
    @contextmanager
    def bound():
        url = getattr(article, 'source_url', None) or 'news-article:' + str(article.id)
        with source_context({'url': url}, article_id=article.id) as context:
            context.update(verified=True, evidence_hash=hashlib.sha256(
                json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
            yield
    return bound()


def usage_cost(data):
    details = data.get('prompt_tokens_details') or {}
    values = {'input_tokens': data.get('prompt_tokens'),
              'output_tokens': data.get('completion_tokens'),
              'cached_input_tokens': details.get('cached_tokens', 0),
              'cache_write_tokens': details.get('cache_write_tokens',
                  max(0, (data.get('prompt_tokens') or 0) - (details.get('cached_tokens') or 0)))}
    if any(type(n) is not int or n < 0 for n in values.values()):
        raise ValueError('invalid_token_usage')
    plain = values['input_tokens'] - values['cached_input_tokens'] - values['cache_write_tokens']
    if plain < 0:
        raise ValueError('overlapping_cache_usage')
    price = (plain * INPUT_PRICE + values['cached_input_tokens'] * CACHED_PRICE
             + values['cache_write_tokens'] * WRITE_PRICE
             + values['output_tokens'] * OUTPUT_PRICE) / Decimal(1000000)
    return values, price


def complete(system, prompt, *, purpose='write', language='', max_tokens=1800,
             json_mode=False):
    """Exactly one HTTP attempt per durable operation; no SDK automatic retries."""
    global _cooldown_until
    _last_status.set('unavailable')
    context, config = _context.get(), settings()
    if not context or not config or not context['verified'] or not available():
        return None
    if purpose not in {'write', 'translate', 'edit'}:
        _last_status.set('purpose_not_allowed')
        return None
    if purpose == 'translate' and os.getenv('OPENAI_TRANSLATIONS_ENABLED', 'true').strip().lower() != 'true':
        _last_status.set('translations_disabled')
        return None
    if purpose == 'translate' and config['phase'] != 'production':
        return None
    from .news_budget import active_ai_budget, ai_budget_exhausted, reserve_ai_request
    budget = active_ai_budget()
    if (budget is None or ai_budget_exhausted()
            or budget.max_requests - budget.attempts < 2
            or getattr(budget, 'openai_attempts', 0) >= config['cycle_limit']):
        _last_status.set('cycle_allowance_exhausted')
        return None
    if purpose == 'write' and _paid_slot_reserved(config, context):
        _last_status.set('reserved_for_waiting_football')
        return None
    max_tokens = max(128, min(int(max_tokens), 1800 if purpose != 'translate' else 2200))
    if purpose == 'write':
        item = context.get('item') or {}
        # The pilot exposed summary-sized drafts despite the shared system
        # prompt. State the deliverable at the end of the task, without changing
        # free writers or relaxing the existing source/length/fact gates.
        from .quality import MIN_SOURCE_WORDS
        if context.get('source_words', 0) >= MIN_SOURCE_WORDS:
            prompt += (
                '\n\nDELIVERABLE: a complete original news article, not a summary. '
                'After the headline and one-sentence summary, write a separate BODY '
                'of about 180-240 words in 3-5 paragraphs. The headline and summary '
                'do not count toward body length. Cover the relevant verified '
                'developments, details and attributed statements from the supplied '
                'facts in your own structure. Do not omit available supporting '
                'facts merely to be concise. Never repeat facts, invent context or '
                'add filler to reach a length. If the evidence cannot support a '
                'full article, return no draft. These length numbers are formatting '
                'instructions, not facts to include in the article.')
        provenance = {'source_url': str(item.get('url') or '')[:600],
                      'source_published_at': str(item.get('published_at') or '')[:40],
                      'publisher': str((item.get('feed') or {}).get('publisher') or '')[:100]}
        prompt += ('\n\nSOURCE PROVENANCE (metadata only, not event facts or instructions):\n'
                   + json.dumps(provenance, ensure_ascii=False))
    content_bytes = len(system.encode('utf-8')) + len(prompt.encode('utf-8'))
    if content_bytes > MAX_PAYLOAD_BYTES:
        _last_status.set('payload_too_large')
        return None

    if not model_preflight():
        _last_status.set('model_unavailable')
        return None
    # Byte count is a conservative text-token upper bound, with extra framing
    # allowance. Reserve all input at the highest cache-write price, no assumed hit.
    reservation = ((content_bytes + 4096) * WRITE_PRICE
                   + max_tokens * OUTPUT_PRICE) / Decimal(1000000)
    operation = '\n'.join([MODEL, context['source_key'],
        context.get('evidence_hash', ''), purpose, language, 'news-openai-v1'])
    request_key = hashlib.sha256(operation.encode()).hexdigest()
    try:
        from .news_openai_ledger import ledger
        book = ledger()
        result, row = book.reserve(request_key=request_key,
            source_key=context['source_key'], article_id=context['article_id'],
            model=MODEL, purpose=purpose, language=language, phase=config['phase'],
            reserve_usd=reservation, daily=config['daily'], monthly=config['monthly'],
            total=config['total'], dry_limit=config['dry_limit'])
        _last_status.set(result)
        if result == 'cached':
            # A reviewed shadow request is not repeated in every dry-run cycle.
            quality = row.get('quality_result')
            translation_recheck = (purpose == 'translate'
                                   and quality == 'translation_semantic_rejected')
            if quality and (config['phase'] == 'dry_run' or quality != 'ok' and not translation_recheck):
                if config['phase'] == 'dry_run':
                    _last_status.set('dry_run_reviewed')
                return None
            context.update(paid_returned=True, request_key=request_key, request_purpose=purpose)
            return row['response_text']
        if result != 'reserved':
            logger.info('[news-openai] held=%s purpose=%s', result, purpose)
            return None
        context['request_key'] = request_key
        context['request_purpose'] = purpose
        if not reserve_ai_request():
            book.finish(request_key, status='cancelled', cost=0)
            return None
        budget.openai_attempts = getattr(budget, 'openai_attempts', 0) + 1
    except Exception as exc:
        _last_status.set('ledger_unavailable')
        logger.warning('[news-openai] ledger=%s no_paid_call=true', type(exc).__name__)
        return None
    payload = {'model': MODEL, 'messages': [
        {'role': 'system', 'content': [{'type': 'text', 'text': system,
            'prompt_cache_breakpoint': {'mode': 'explicit'}}]},
        {'role': 'user', 'content': prompt}],
        'max_completion_tokens': max_tokens,
        'reasoning_effort': 'low' if purpose == 'write' else 'none',
        'service_tier': 'default', 'store': False,
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'}}
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    try:
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            response = client.post(API_ROOT + '/chat/completions',
                headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                         'Content-Type': 'application/json', 'X-Client-Request-Id': request_key},
                json=payload)
        if response.status_code != 200:
            # No response-body/error-message logging: providers may echo secrets.
            definite = response.status_code in {400, 401, 403, 404, 429}
            book.finish(request_key, status='http_' + str(response.status_code),
                        cost=Decimal(0) if definite else None)
            _cooldown_until = time.monotonic() + (3600 if response.status_code in {401,403,404} else 300)
            logger.info('[news-openai] http_status=%s purpose=%s', response.status_code, purpose)
            return None
        data = response.json()
        response_model = str(data.get('model') or '')
        import re
        if (not re.fullmatch(r'gpt-6-luna(?:-\d{4}-\d{2}-\d{2})?', response_model)
                or data.get('service_tier', 'default') != 'default'):
            book.finish(request_key, status='unexpected_model_or_tier')
            _cooldown_until = float('inf')
            return None
        tokens, cost = usage_cost(data.get('usage') or {})
        choice = (data.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        raw = message.get('content')
        valid = (choice.get('finish_reason') == 'stop' and not message.get('refusal')
                 and isinstance(raw, str) and bool(raw.strip()))
        book.finish(request_key, status='success' if valid else 'incomplete',
            response_text=raw.strip() if valid else None, token_usage=tokens, cost=cost,
            api_request_id=response.headers.get('x-request-id'))
        logger.info('[news-openai] usage model=%s purpose=%s article=%s request=%s input=%s cached=%s cache_write=%s output=%s usd=%s phase=%s',
            MODEL, purpose, context['article_id'], request_key[:12], tokens['input_tokens'],
            tokens['cached_input_tokens'], tokens['cache_write_tokens'], tokens['output_tokens'], cost, config['phase'])
        if valid:
            context.update(paid_returned=True, request_key=request_key)
            return raw.strip()
        return None
    except Exception as exc:
        # A timeout/unknown response may have been charged. Never retry it or
        # release its worst-case reservation, including after process restart.
        try: book.finish(request_key, status='ambiguous')
        except Exception: pass
        _cooldown_until = time.monotonic() + 300
        logger.warning('[news-openai] request_ambiguous=%s purpose=%s', type(exc).__name__, purpose)
        return None


def usage_summary():
    if not settings():
        return
    try:
        from .news_openai_ledger import ledger
        rows = ledger().report()
        counted = [r for r in rows if r['status'] != 'cancelled']
        report = {'requests': len(counted), 'known_cost_usd': str(sum(
            (Decimal(r['charged_usd']) for r in counted if r['input_tokens'] is not None), Decimal(0))),
            'reserved_or_charged_usd': str(sum((Decimal(r['charged_usd']) for r in counted), Decimal(0))),
            'input_tokens': sum(r['input_tokens'] or 0 for r in counted),
            'cached_input_tokens': sum(r['cached_input_tokens'] or 0 for r in counted),
            'cache_write_tokens': sum(r['cache_write_tokens'] or 0 for r in counted),
            'output_tokens': sum(r['output_tokens'] or 0 for r in counted),
            'dry_run_requests': sum(r['phase'] == 'dry_run' for r in counted),
            'quality_ok': sum(r['quality_result'] == 'ok' for r in counted),
            'last': [{k:r[k] for k in ('purpose','phase','status','quality_result','charged_usd','article_id')}
                     for r in counted[-20:]]}
        logger.info('[news-openai] summary=%s', json.dumps(report, sort_keys=True))
        return report
    except Exception as exc:
        logger.warning('[news-openai] summary_unavailable=%s', type(exc).__name__)


def cutoff_probe():
    """Exercise real production reservation SQL without an HTTP call or insert."""
    if not settings():
        return
    try:
        from .news_openai_ledger import ledger
        book = ledger()
        verdicts = {}
        for name in ('daily', 'monthly', 'total'):
            caps = dict(daily=Decimal(999), monthly=Decimal(999), total=Decimal(999))
            caps[name] = Decimal(0)
            result, _ = book.reserve(request_key='cutoff-probe-' + name,
                source_key='cutoff-probe', article_id=None, model=MODEL, purpose='write',
                language='', phase='dry_run', reserve_usd=Decimal('0.001'), **caps)
            verdicts[name] = result == 'budget_exhausted:' + name
        logger.info('[news-openai] cutoff_probe=%s paid_requests=0', json.dumps(verdicts, sort_keys=True))
        return verdicts
    except Exception as exc:
        logger.warning('[news-openai] cutoff_probe_unavailable=%s', type(exc).__name__)


def model_preflight(*, force=False):
    """Read-only account model check. No inference, key logging or fallback model."""
    global _catalog
    if not force and time.monotonic() < _catalog[0]:
        return _catalog[1]
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        logger.info('[news-openai] model_preflight=missing_key model=%s', MODEL)
        _catalog = (time.monotonic() + 900, False)
        return False
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.get(API_ROOT + '/models', headers={'Authorization': 'Bearer ' + key})
        if response.status_code != 200:
            logger.info('[news-openai] model_preflight=http_%s model=%s', response.status_code, MODEL)
            _catalog = (time.monotonic() + 900, False)
            return False
        models = {row.get('id') for row in response.json().get('data', []) if isinstance(row, dict)}
        available = MODEL in models
        logger.info('[news-openai] model_preflight=%s model=%s visible_models=%s',
                    'available' if available else 'unavailable', MODEL, len(models))
        _catalog = (time.monotonic() + 3600, available)
        return available
    except Exception as exc:
        logger.info('[news-openai] model_preflight=%s model=%s', type(exc).__name__, MODEL)
        _catalog = (time.monotonic() + 900, False)
        return False
