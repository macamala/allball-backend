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



def free_ai_available() -> bool:
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


def free_ai_rate_limited() -> bool:
    return _rate_limited


def reset_free_ai_rate_limit() -> None:
    global _rate_limited
    _rate_limited = False


def _completion(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool = False,
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
        "temperature": 0.2,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=8), follow_redirects=False) as client:
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


def write_free_story(system_prompt: str, prompt: str) -> Optional[str]:
    model = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
    if not model:
        return None
    return _completion(
        model=model,
        system=system_prompt,
        user=prompt,
        max_tokens=int(os.getenv("NEWS_XKIRO_WRITER_MAX_TOKENS", "1800") or "1800"),
        json_mode=False,
    )


def free_json_completion(system_prompt: str, prompt: str, *, max_tokens: int = 5000) -> Optional[str]:
    """Shared zero-price JSON lane for translation/validation work."""
    model = _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)
    if not model:
        return None
    return _completion(
        model=model,
        system=system_prompt,
        user=prompt,
        max_tokens=max_tokens,
        json_mode=True,
    )


def selected_free_model_name() -> Optional[str]:
    return _free_model("NEWS_XKIRO_WRITER_MODEL", _DEFAULT_WRITER)


_VALIDATOR_SYSTEM = """You are a strict sports-news fact checker.
Compare a draft only against the supplied source facts.
Approve only when every factual claim in the draft is directly supported.
Treat changed proper names, invented timing/context, implied causes, invented
importance, invented quotes, injuries, tactics, table positions or chronology as
unsupported unless the source explicitly states them.
Do not use outside knowledge.
Return JSON only with exactly:
{"approved": boolean, "unsupported_claims": [string], "changed_names": [string]}
Keep arrays empty when approved.
"""


def validate_free_story(
    source_title: str,
    source_facts: str,
    draft_title: str,
    draft_summary: str,
    draft_body: str,
) -> Tuple[bool, str]:
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
    raw = _completion(
        model=model,
        system=_VALIDATOR_SYSTEM,
        user=user,
        max_tokens=int(os.getenv("NEWS_XKIRO_VALIDATOR_MAX_TOKENS", "700") or "700"),
        json_mode=True,
    )
    if not raw:
        return False, "validator-unavailable"
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        return False, "validator-invalid-json"
    if not isinstance(result, dict):
        return False, "validator-invalid-shape"
    if set(result) != {"approved", "unsupported_claims", "changed_names"}:
        return False, "validator-invalid-shape"
    unsupported = result.get("unsupported_claims")
    changed = result.get("changed_names")
    approved = result.get("approved")
    if type(approved) is not bool or not isinstance(unsupported, list) or not isinstance(changed, list):
        return False, "validator-invalid-shape"
    if any(not isinstance(x, str) for x in unsupported + changed):
        return False, "validator-invalid-shape"
    if approved and not unsupported and not changed:
        return True, "ok"
    if changed:
        return False, "validator-changed-name"
    return False, "validator-unsupported-claim"
