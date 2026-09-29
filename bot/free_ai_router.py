"""Fail-closed zero-price AI transport for NinkoSports News.

Only xKiro model IDs ending in ':free' are permitted in this module. There is no
paid alias fallback and no provider rotation to non-free models. Every HTTP
attempt uses the existing shared durable News request ledger.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextvars import ContextVar
from typing import Optional, Tuple

import httpx

from .news_budget import reserve_ai_request

logger = logging.getLogger(__name__)

_XKIRO_ENDPOINT = "https://api.xkiro.com/v1/chat/completions"
_XKIRO_MODELS_ENDPOINT = "https://api.xkiro.com/v1/models"
_XKIRO_USAGE_ENDPOINT = "https://api.xkiro.com/v1/usage"
_MODEL_RE = re.compile(r"^[A-Za-z0-9._/+:-]{3,160}:free$")
_DEFAULT_WRITER = "qwen/qwen3.5-397b-a17b:free"
_DEFAULT_VALIDATOR = "qwen/qwen3.5-397b-a17b:free"

_rate_limited = False
_catalog_cache = {"at": 0.0, "rows": None}
_usage_cache = {"at": 0.0, "remaining": None, "verified": False}
_LAST_WRITER = ContextVar("news_last_free_writer", default=("unknown", "unknown"))
_LAST_JSON = ContextVar("news_last_free_json", default=("unknown", "unknown"))
_LAST_VALIDATION = ContextVar("news_last_validation_feedback", default={})


def _free_model(env_name: str, default: str) -> Optional[str]:
    model = (os.getenv(env_name) or default).strip()
    if not _MODEL_RE.fullmatch(model):
        logger.error("[free_ai] refused non-free or invalid model id for %s", env_name)
        return None
    return model


def _catalog_rows() -> Optional[list]:
    now = time.monotonic()
    cached = _catalog_cache.get("rows")
    if isinstance(cached, list) and now - float(_catalog_cache.get("at") or 0) < 60:
        return cached
    try:
        with httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False) as client:
            response = client.get(_XKIRO_MODELS_ENDPOINT, headers={"Accept": "application/json"})
        if response.status_code != 200:
            return None
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return None
        rows = [row for row in rows if isinstance(row, dict)]
        _catalog_cache["at"] = now
        _catalog_cache["rows"] = rows
        return rows
    except Exception as exc:
        logger.warning("[free_ai] xKiro model catalog unavailable: %s", type(exc).__name__)
        return None


def _free_catalog_model(model: str) -> bool:
    if not _MODEL_RE.fullmatch(model):
        return False
    rows = _catalog_rows()
    if rows is None:
        return False
    row = next((item for item in rows if item.get("id") == model), None)
    if not isinstance(row, dict) or row.get("access_tier") != "free":
        return False
    # Explicit pay-as-you-go routes are never acceptable for News.
    if row.get("pay_as_you_go") is True:
        return False
    return True


def _free_tokens_available() -> bool:
    """Authenticated free-token counter. Cached so batches do not double traffic."""
    now = time.monotonic()
    if _usage_cache.get("verified") and now - float(_usage_cache.get("at") or 0) < 60:
        remaining = _usage_cache.get("remaining")
        return remaining is None or (isinstance(remaining, int) and remaining > 0)
    key = (os.getenv("XKIRO_API_KEY") or "").strip()
    if not key:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False) as client:
            response = client.get(
                _XKIRO_USAGE_ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
        if response.status_code != 200:
            return False
        payload = response.json()
        free = payload.get("free_tokens") if isinstance(payload, dict) else None
        if not isinstance(free, dict) or "remaining" not in free:
            return False
        remaining = free.get("remaining")
        if remaining is not None and (type(remaining) is not int or remaining < 0):
            return False
        _usage_cache.update(at=now, remaining=remaining, verified=True)
        return remaining is None or remaining > 0
    except Exception as exc:
        logger.warning("[free_ai] xKiro usage counter unavailable: %s", type(exc).__name__)
        return False



def _xkiro_available() -> bool:
    writer = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
    validator = _free_model("NEWS_XKIRO_VALIDATOR_MODEL", _DEFAULT_VALIDATOR)
    return bool(
        (os.getenv("XKIRO_API_KEY") or "").strip()
        and writer
        and validator
        and _free_catalog_model(writer)
        and _free_catalog_model(validator)
        and _free_tokens_available()
    )


def free_ai_available() -> bool:
    """A writer is usable only when a different provider can validate it."""
    writers, validators = set(), set()
    try:
        from .news_external_free import configured_identities
        writers = {provider for provider, _model in configured_identities('writer')}
        validators = {provider for provider, _model in configured_identities('validator')}
    except Exception:
        pass
    if any(writer != validator for writer in writers for validator in validators):
        return True
    if not _rate_limited and _xkiro_available():
        writers.add('xkiro')
        validators.add('xkiro')
    return any(writer != validator for writer in writers for validator in validators)


def free_ai_rate_limited() -> bool:
    return not free_ai_available()


def reset_free_ai_rate_limit() -> None:
    global _rate_limited
    _rate_limited = False
    _LAST_WRITER.set(("unknown", "unknown"))
    _LAST_JSON.set(("unknown", "unknown"))
    try:
        from .news_external_free import reset as reset_external
        reset_external()
    except Exception:
        pass


def last_writer_identity() -> tuple[str, str]:
    return _LAST_WRITER.get()


def last_json_identity() -> tuple[str, str]:
    return _LAST_JSON.get()


def last_validation_feedback() -> dict:
    return dict(_LAST_VALIDATION.get())


def _completion(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool = False,
    temperature: float = 0.1,
    timeout_seconds: float = 95.0,
) -> Optional[str]:
    """One actual xKiro request. No retry and no paid fallback."""
    global _rate_limited
    if _rate_limited:
        return None
    key = (os.getenv("XKIRO_API_KEY") or "").strip()
    if not key or not _MODEL_RE.fullmatch(model):
        return None
    if not _free_catalog_model(model):
        logger.error("[free_ai] refused model without live free-tier metadata: %s", model)
        return None
    if not _free_tokens_available():
        logger.warning("[free_ai] free-token allowance unavailable or exhausted")
        return None
    if not reserve_ai_request():
        logger.warning("[free_ai] request budget unavailable or exhausted")
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max(256, min(int(max_tokens), 9000)),
        "reasoning_effort": "none",
        "temperature": max(0.0, min(float(temperature), 1.0)),
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        timeout_seconds = max(15.0, min(float(timeout_seconds), 240.0))
        with httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=8),
            follow_redirects=False,
        ) as client:
            response = client.post(
                _XKIRO_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
        if response.status_code == 429:
            _rate_limited = True
            logger.warning("[free_ai] xKiro rate/quota limited for this run")
            return None
        if response.status_code != 200:
            logger.warning("[free_ai] xKiro HTTP %s", response.status_code)
            return None
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None
        choice = choices[0]
        message = choice.get("message") or {}
        if choice.get("finish_reason") != "stop" or not isinstance(message, dict) or message.get("refusal"):
            return None
        text = message.get("content")
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception as exc:
        logger.warning("[free_ai] xKiro request failed: %s", type(exc).__name__)
        return None


def _external_validator_ready() -> bool:
    try:
        from .news_external_free import configured_identities
        return any(provider != 'xkiro' for provider, _model in configured_identities('validator'))
    except Exception:
        return False


def write_free_story(system_prompt: str, prompt: str) -> Optional[str]:
    # Bounded factual/originality corrections benefit from a different model family
    # than the external first-pass writers. Use the verified xKiro free route
    # first only when another provider can validate it. Otherwise keep xKiro
    # available as validator and send the correction to the external writers.
    corrective_retry = (
        "VALIDATION_FAILURE: direct_quote_requires_review" in prompt
        or "VALIDATION_FAILURE: headline_too_similar_to_source" in prompt
        or "VALIDATION_FAILURE: copied_source_headline" in prompt
        or "VALIDATION_FAILURE: validator-unsupported-claim" in prompt
        or "VALIDATION_FAILURE: validator-changed-name" in prompt
        or "VALIDATION_FAILURE: too-short" in prompt
        or "VALIDATION_FAILURE: unsupported_number" in prompt
    )
    if corrective_retry and _external_validator_ready():
        model = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
        if model:
            value = _completion(
                model=model,
                system=system_prompt,
                user=prompt,
                max_tokens=int(os.getenv("NEWS_XKIRO_WRITER_MAX_TOKENS", "1800") or "1800"),
                json_mode=False,
                temperature=0.25,
            )
            if value:
                _LAST_WRITER.set(("xkiro", model))
                logger.info("[free_ai] corrective writer provider=xkiro model=%s", model)
                return value
    try:
        from .news_external_free import completion as external_completion
        value, identity = external_completion(
            system=system_prompt,
            user=prompt,
            max_tokens=int(os.getenv("NEWS_XKIRO_WRITER_MAX_TOKENS", "1800") or "1800"),
            json_mode=False,
            purpose="writer",
        )
        if value:
            _LAST_WRITER.set(identity)
            logger.info("[free_ai] writer provider=%s model=%s", identity[0], identity[1])
            return value
    except Exception as exc:
        logger.warning("[free_ai] external writer unavailable: %s", type(exc).__name__)

    if not _external_validator_ready():
        logger.info('[free_ai] xKiro writer skipped: no independent external validator')
        return None
    model = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
    if not model:
        return None
    value = _completion(
        model=model,
        system=system_prompt,
        user=prompt,
        max_tokens=int(os.getenv("NEWS_XKIRO_WRITER_MAX_TOKENS", "1800") or "1800"),
        json_mode=False,
        temperature=0.45,
    )
    if value:
        _LAST_WRITER.set(("xkiro", model))
    return value


def free_json_completion(system_prompt: str, prompt: str, *, max_tokens: int = 5000) -> Optional[str]:
    """Shared free-tier JSON lane for translations and bounded JSON work."""
    try:
        from .news_external_free import completion as external_completion
        value, identity = external_completion(
            system=system_prompt,
            user=prompt,
            max_tokens=max_tokens,
            json_mode=True,
            purpose="translation",
        )
        if value:
            _LAST_JSON.set(identity)
            return value
    except Exception as exc:
        logger.warning("[free_ai] external JSON unavailable: %s", type(exc).__name__)

    model = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
    if not model:
        return None
    value = _completion(
        model=model,
        system=system_prompt,
        user=prompt,
        max_tokens=max_tokens,
        json_mode=True,
        temperature=0.15,
        timeout_seconds=180.0,
    )
    if value:
        _LAST_JSON.set(("xkiro", model))
    return value


def selected_free_model_name() -> Optional[str]:
    provider, model = _LAST_JSON.get()
    if provider != "unknown" and model != "unknown":
        return (provider + ":" + model)[:160]
    return _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)


_VALIDATOR_SYSTEM = """You are a strict sports-news editor and fact checker.
Compare the draft ONLY with the supplied source facts.
Check the headline and summary as carefully as the body. Preserve restrictive
qualifiers: a home debut is not an overall debut; a first league win is not a
first win in all competitions; a first medal does not mean the only medal.

Approve every factual claim only when it is explicitly stated by the source or
directly entailed by it. Do NOT require the same wording, paragraph order or
sentence structure.

The draft may omit secondary source facts. Omission alone is NOT an unsupported
claim. Judge only what the draft actually asserts, preserving attribution,
uncertainty and the event each fact belongs to.

Reject any genuinely new event-specific assertion: invented cause, motive,
importance, chronology, atmosphere, crowd reaction, tactics, injury, statistic,
location, table position, relationship, quote, prediction, consequence or
stronger characterization not supported by the source.
Reject any changed or invented proper name.
Compare surname spelling character by character, including single surnames in
event labels such as X vs Y. A similar-looking name is still a changed name.
Check WHO did each action, not just whether the names and action appear somewhere
in the source. Never transfer one person's employment, biography, injury, result
or quotation to another person named in the same article. Resolve pronouns from
their source context. If the actor is uncertain, reject the claim.
Check singular roles before a list: naming an assistant coach and another person
does not establish that both are assistant coaches. Never pluralize a shared role
without explicit source support. Preserve the exact cause of a travel disruption:
a weight calculation problem is not a fuel calculation error, and an unplanned
refuelling stop does not entail an emergency.
Do not use outside knowledge or assumptions.
Reject clock times mistranslated as durations: Serbian "večeras do 24 časa" means by midnight that evening, not 24 hours from now.
The source and draft must describe a concrete current sporting development.
Reject product/service descriptions, evergreen injury or roster trackers,
photo captions expanded with filler, podcasts, highlight lists, quizzes and
retrospective features presented as current news. Reject anonymous fan or
celebrity predictions presented as a substitute for an official decision.
Reject fan polls, fan-voted goal/MVP contests, sweepstakes, prize giveaways,
ticket/shop/app promotions and voting instructions, including their results.
An official club or league publisher does not turn a promotional product into
sporting news. A real sporting award announcement is different from asking
supporters to vote or enter a prize draw.
Reject filler about what the source did not provide and unsupported broad
implications. Every sentence must report a supported fact or attributed statement.
For such a rejection, set approved=false and explain the concrete editorial
problem in unsupported_claims; keep the same JSON schema.
When rejecting factual support, identify only concrete unsupported claims actually
present in the draft. Do not demand that a concise report repeat all source facts.

First explicitly classify the SOURCE product, not just the rewritten headline.
source_type must be one of: news, analysis, fan_poll, promotion, entertainment,
scorecard, tracker, podcast, gallery, retrospective, unknown.
Only news may be approved. Rewriting a poll as an announcement that the club
invited supporters to rank past wins does NOT make it news. A factual report
about new competition events, appointments, injuries, contracts or sporting
decisions is news; instructions for audience participation are not.
Subjective pressure rankings, predictions, listicles and generic claims that a
future tournament matters are analysis, not news. Qualification probability
calculators (including "veja
contas") and TV/streaming guides (including "dónde ver" and "onde assistir")
remain analysis or service products even when their fixtures and numbers are true.
A teaser without identified people, teams or a concrete new event is insufficient. Never approve prose
describing facts that were not supplied, unspecified teams or missing details.

Return JSON only with exactly:
{"source_type": string, "approved": boolean, "unsupported_claims": [string], "changed_names": [string]}
Keep both arrays empty when approved.
"""


def validate_free_story(
    source_title: str,
    source_facts: str,
    draft_title: str,
    draft_summary: str,
    draft_body: str,
) -> Tuple[bool, str]:
    _LAST_VALIDATION.set({})
    model = _free_model("NEWS_XKIRO_VALIDATOR_MODEL", _DEFAULT_VALIDATOR)
    if not model:
        return False, "validator-model-not-free"
    user = (
        "SOURCE HEADLINE:\n" + (source_title or "")[:1000]
        + "\n\nSOURCE FACTS:\n" + (source_facts or "")[:9000]
        + "\n\nDRAFT HEADLINE:\n" + (draft_title or "")[:1000]
        + "\n\nDRAFT SUMMARY:\n" + (draft_summary or "")[:1200]
        + "\n\nDRAFT BODY:\n" + (draft_body or "")[:9000]
    )
    from .news_fact_guard import source_name_equivalences
    names = source_name_equivalences((source_title or '') + '\n' + (source_facts or ''))
    if names:
        user += ('\n\nAUDITED SOURCE NAME SPELLINGS:\n' + names
                 + '\nThese are spelling equivalences for names present in the source, not new facts. '
                   'Accept these equivalent spellings only; still reject different people, misspellings, '
                   'changed roles or unsupported claims. Do not infer a club or biography from a name.')
    raw = None
    writer_provider, _writer_model = _LAST_WRITER.get()
    try:
        from .news_external_free import completion as external_completion
        raw, identity = external_completion(
            system=_VALIDATOR_SYSTEM,
            user=user,
            max_tokens=int(os.getenv("NEWS_XKIRO_VALIDATOR_MAX_TOKENS", "700") or "700"),
            json_mode=True,
            purpose="validator",
            avoid_provider=writer_provider,
        )
        if raw and identity[0] == writer_provider and writer_provider != "unknown":
            raw = None
        if raw:
            _LAST_JSON.set(identity)
    except Exception as exc:
        logger.warning("[free_ai] external validator unavailable: %s", type(exc).__name__)
    if not raw:
        if writer_provider == "xkiro":
            return False, "validator-independent-unavailable"
        raw = _completion(
            model=model,
            system=_VALIDATOR_SYSTEM,
            user=user,
            max_tokens=int(os.getenv("NEWS_XKIRO_VALIDATOR_MAX_TOKENS", "700") or "700"),
            json_mode=True,
            temperature=0.0,
        )
        if raw:
            _LAST_JSON.set(("xkiro", model))
    if not raw:
        return False, "validator-unavailable"
    validator_provider, validator_model = _LAST_JSON.get()
    logger.info("[free_ai] validator provider=%s model=%s writer_provider=%s",
                validator_provider, validator_model, writer_provider)
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        return False, "validator-invalid-json"
    if not isinstance(result, dict):
        return False, "validator-invalid-shape"
    if set(result) != {"source_type", "approved", "unsupported_claims", "changed_names"}:
        return False, "validator-invalid-shape"
    unsupported = result.get("unsupported_claims")
    changed = result.get("changed_names")
    approved = result.get("approved")
    source_type = result.get("source_type")
    if not isinstance(source_type, str) or source_type not in {'news', 'analysis', 'fan_poll', 'promotion', 'entertainment', 'scorecard', 'tracker', 'podcast', 'gallery', 'retrospective', 'unknown'}:
        return False, 'validator-schema-invalid'
    if type(approved) is not bool or not isinstance(unsupported, list) or not isinstance(changed, list):
        return False, "validator-invalid-shape"
    if any(not isinstance(x, str) for x in unsupported + changed):
        return False, "validator-invalid-shape"
    _LAST_VALIDATION.set({
        "unsupported_claims": [x[:320] for x in unsupported[:6]],
        "changed_names": [x[:160] for x in changed[:6]],
    })
    if source_type != 'news':
        _LAST_VALIDATION.set({'unsupported_claims': ['Source product is '+source_type+'; it cannot be converted into news.'], 'changed_names': []})
        return False, 'validator-source-type:' + source_type
    if approved and not unsupported and not changed:
        return True, "ok"
    if changed:
        return False, "validator-changed-name"
    return False, "validator-unsupported-claim"
