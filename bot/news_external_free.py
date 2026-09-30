"""Explicit free-tier external writer/validator pool for NinkoSports News.

This module never reads or calls OpenAI. It is enabled only by
NEWS_EXTERNAL_FREE_WRITERS_ENABLED=1 and uses configured Groq and
Cloudflare credentials. Mistral and Gemini require an explicit Free-account
opt-in; Routeway requires an explicitly free model and current zero-price
catalog evidence. Z.ai is limited to the explicitly free GLM-4.7-Flash writer. An API key
alone never enables either route. Every HTTP attempt is reserved in the same
durable News request ledger. Provider output is never publication authority:
downstream deterministic, semantic, taxonomy, dedupe and image gates decide.
"""
from __future__ import annotations

import logging
import json
import os
import re
import time
from threading import Lock
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from typing import Optional

import httpx

from .news_budget import reserve_ai_request

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
_ZAI_ENDPOINT = "https://api.z.ai/api/paas/v4/chat/completions"
_ZAI_FREE_MODEL = "glm-4.7-flash"
_GEMINI_FREE_MODEL = "gemini-3.1-flash-lite"
_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/" + _GEMINI_FREE_MODEL + ":generateContent"
_ROUTEWAY_ENDPOINT = "https://api.routeway.ai/v1/chat/completions"
_ROUTEWAY_MODELS_ENDPOINT = "https://api.routeway.ai/v1/models"
_ROUTEWAY_FREE_MODEL = "muse-glimmer-30b:free"
_ROUTEWAY_VERIFIED_UNTIL = 0.0
_ROUTEWAY_LOCK = Lock()
_PROVIDERS = ("groq", "cloudflare", "gemini", "routeway", "mistral", "zai")
_CF_MODEL_RE = re.compile(r"^@[A-Za-z0-9._/-]{3,160}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._/+:-]{3,160}$")
_PURPOSES = ("writer", "validator", "translation")
_UNAVAILABLE = {name: set() for name in _PURPOSES}
_CURSOR = {name: 0 for name in _PURPOSES}
_COOLDOWN_UNTIL = {}
_UNKNOWN_QUOTA_STREAK = {}
# Explicitly supported production model in Groq's Free Plan on 2026-09-29.
# Writer-only: the existing independent validator remains the publication gate.
_GROQ_FREE_WRITER_FALLBACKS = frozenset({'openai/gpt-oss-20b'})


def _route_key(provider: str, model: str) -> str:
    return provider + ':' + model


def _provider_ready(provider: str, model: str = '') -> bool:
    now = time.monotonic()
    return (now >= _COOLDOWN_UNTIL.get(provider, 0.0)
            and (not model or now >= _COOLDOWN_UNTIL.get(_route_key(provider, model), 0.0)))


def _retry_seconds(value) -> Optional[float]:
    text = str(value or "").strip()
    try:
        seconds = float(text)
        return seconds if 0 < seconds <= 7 * 86400 else None
    except ValueError:
        pass
    if re.fullmatch(r"(?:\d+(?:\.\d+)?[hms])+", text):
        seconds = sum(float(n) * {"h": 3600, "m": 60, "s": 1}[unit]
                      for n, unit in re.findall(r"(\d+(?:\.\d+)?)([hms])", text))
        return seconds if 0 < seconds <= 7 * 86400 else None
    try:
        stamp = parsedate_to_datetime(text)
        if stamp.tzinfo is not None:
            seconds = max(1.0, (stamp - datetime.now(timezone.utc)).total_seconds())
            return seconds if seconds <= 7 * 86400 else None
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _http_failure(provider: str, response, *, model: str = '') -> None:
    """Share provider quota/auth failures across purposes; never log response bodies."""
    status = response.status_code
    if status not in {401, 403, 429} and not (provider == 'routeway' and status == 402):
        return
    headers = getattr(response, "headers", {}) or {}
    seconds = _retry_seconds(headers.get("retry-after"))
    dimension = "unknown"
    error_codes = []
    model_scope = False
    if status == 429:
        try:
            payload = response.json()
            payload = payload if isinstance(payload, dict) else {}
            error = payload.get("error")
            message = str(error.get("message") if isinstance(error, dict) else error or "").lower()
            if provider == 'routeway':
                # Official free limits are account-wide: never rotate models
                # or keys after quota exhaustion. Daily reset is UTC midnight.
                if headers.get('x-ratelimit-remaining-day') == '0' or re.search(r'per[ -]day|daily|\brpd\b', message):
                    dimension = 'daily_free_requests'
                    now = datetime.now(timezone.utc)
                    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    seconds = max(seconds or 0, _retry_seconds(headers.get('x-ratelimit-reset-day')) or 0,
                                  (reset - now).total_seconds() + 60)
                elif re.search(r'per[ -]minute|\brpm\b', message):
                    dimension = 'minute_requests'
                    seconds = max(seconds or 0, _retry_seconds(headers.get('x-ratelimit-reset-minute')) or 60)
            if provider == 'gemini' and isinstance(error, dict):
                # Google's structured quota dimensions, never the response text.
                for detail in error.get('details', []):
                    if not isinstance(detail, dict):
                        continue
                    if seconds is None:
                        seconds = _retry_seconds(detail.get('retryDelay'))
                    for violation in detail.get('violations', []):
                        if not isinstance(violation, dict):
                            continue
                        quota = str(violation.get('quotaId') or '') + str(violation.get('quotaMetric') or '')
                        if re.search(r'per.?day', quota, re.I):
                            dimension = 'daily_free_requests'
                            now = datetime.now(ZoneInfo('America/Los_Angeles'))
                            reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                            seconds = max(seconds or 0, reset.timestamp() - now.timestamp() + 60)
                        elif dimension == 'unknown' and re.search(r'per.?minute', quota, re.I):
                            dimension = 'minute_requests_or_tokens'
            # Mistral errors use top-level message/code, unlike Groq's nested
            # error. Inspect only for classification; never log response text.
            if provider == 'mistral':
                message += ' ' + str(payload.get('message') or '').lower()
                code = payload.get('code')
                if str(code).isdigit() and len(str(code)) <= 6:
                    error_codes.append(int(code))
                if 'service tier capacity exceeded' in message:
                    dimension = 'service_tier_capacity'
            # Workers AI uses an errors array. Code 3036 explicitly means the
            # daily free neuron allowance is exhausted, not a minute limit.
            errors = payload.get('errors') if isinstance(payload, dict) else None
            if isinstance(errors, list):
                error_codes = [int(row['code']) for row in errors[:8]
                               if isinstance(row, dict) and str(row.get('code', '')).isdigit()]
                message += ' ' + ' '.join(str(row.get('message') or '').lower()
                                          for row in errors[:8] if isinstance(row, dict))
            if provider == 'cloudflare' and (3036 in error_codes or (
                'daily free allocation' in message and 'neurons' in message
            )):
                dimension = 'daily_free_neurons'
                now = datetime.now(timezone.utc)
                reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds = max(seconds or 0, (reset - now).total_seconds() + 60)
            for marker, code in (("tokens per day", "tpd"), ("requests per day", "rpd"),
                                 ("tokens per month", "tokens_per_month"),
                                 ("tokens per minute", "tpm"), ("requests per minute", "rpm")):
                if marker in message or re.search(r"\b" + code + r"\b", message):
                    dimension = code
                    break
            # Only an explicit model-specific Groq quota scopes the hold to one
            # route. Auth, billing, unknown limits and Cloudflare's account-wide
            # daily allowance always hold the entire provider. No key rotation.
            # A help URL such as /settings/billing is not itself a billing
            # failure. Keep every actual billing word in the surrounding text.
            quota_message = re.sub(r'https?://\S+', '', message)
            model_scope = bool(provider == 'groq' and model
                and dimension in {'tpd', 'rpd', 'tpm', 'rpm'}
                and not re.search(r'\b(billing|payment|credit|balance|spend)\b', quota_message)
                and re.search(r'\brate limit (?:reached|exceeded) for model\s+[`\"\x27]?' + re.escape(model.lower())
                              + r'[`\"\x27]?(?=\s|[,.;])', message))
        except (ValueError, TypeError, AttributeError):
            pass
        if seconds is None:
            reset_key = "x-ratelimit-reset-requests" if dimension == "rpd" else "x-ratelimit-reset-tokens"
            seconds = _retry_seconds(headers.get(reset_key)) if dimension in {"rpd", "tpm"} else None
    scope = _route_key(provider, model) if model_scope else provider
    if status == 429 and seconds is None and dimension == 'unknown':
        # Repeated unknown 429s must not consume one request every News cycle.
        # Preserve explicit reset/Retry-After evidence, and periodically probe
        # this route again without changing providers, keys or billing tiers.
        streak = min(4, (_UNKNOWN_QUOTA_STREAK.get(scope, 0) if scope in _COOLDOWN_UNTIL else 0) + 1)
        _UNKNOWN_QUOTA_STREAK[scope] = streak
        seconds = min(3600, 600 * 2 ** (streak - 1))
    seconds = seconds or (3600 if status in {401, 403} else 600)
    _COOLDOWN_UNTIL[scope] = max(_COOLDOWN_UNTIL.get(scope, 0), time.monotonic() + seconds)
    for unavailable in _UNAVAILABLE.values():
        unavailable.add(scope)
    logger.warning("[external_free] provider=%s status=%s cooldown_seconds=%s limit_dimension=%s error_codes=%s model_scope=%s",
                   provider, status, int(seconds), dimension, error_codes, model if model_scope else 'all')


def enabled() -> bool:
    return os.getenv("NEWS_EXTERNAL_FREE_WRITERS_ENABLED") == "1"


def _config(provider: str) -> Optional[dict]:
    if not enabled():
        return None
    if provider == "routeway":
        key = (os.getenv("ROUTEWAY_API_KEY") or "").strip()
        if os.getenv("NEWS_ROUTEWAY_FREE_ENABLED") != "1" or not key:
            return None
        return {"provider": "routeway", "model": _ROUTEWAY_FREE_MODEL, "key": key}
    if provider == "gemini":
        # Operator's Free-project opt-in; never enable billing, Search grounding,
        # Pro models, paid fallbacks or model rotation after quota exhaustion.
        if os.getenv("NEWS_GEMINI_FREE_ENABLED") != "1":
            return None
        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            return None
        return {"provider": "gemini", "model": _GEMINI_FREE_MODEL, "key": key}
    if provider == "zai":
        # Official pricing lists this exact model as free input and output.
        # No configurable alias, paid FlashX fallback, tools or coding endpoint.
        if os.getenv("NEWS_ZAI_FREE_WRITER_ENABLED") != "1":
            return None
        key = (os.getenv("ZAI_API_KEY") or "").strip()
        if not key:
            return None
        return {"provider": "zai", "model": _ZAI_FREE_MODEL, "key": key}
    if provider == "mistral":
        # Mistral keys do not encode billing mode. The operator must confirm a
        # Free account before opting in; never infer free usage from a model name.
        if os.getenv("NEWS_MISTRAL_FREE_ENABLED") != "1":
            return None
        key = (os.getenv("MISTRAL_API_KEY") or "").strip()
        model = (os.getenv("NEWS_MISTRAL_MODEL") or "mistral-small-latest").strip()
        if not key or not _MODEL_RE.fullmatch(model):
            return None
        return {"provider": "mistral", "model": model, "key": key}
    if provider == "groq":
        key = (os.getenv("GROQ_API_KEY") or "").strip()
        model = (os.getenv("NEWS_GROQ_MODEL") or "openai/gpt-oss-120b").strip()
        if not key or not _MODEL_RE.fullmatch(model):
            return None
        return {"provider": "groq", "model": model, "key": key}
    if provider == "cloudflare":
        key = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
        account = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        model = (
            os.getenv("NEWS_CLOUDFLARE_MODEL")
            or "@cf/qwen/qwen3-30b-a3b-fp8"
        ).strip()
        if (
            not key
            or not re.fullmatch(r"[A-Fa-f0-9]{32}", account)
            or not _CF_MODEL_RE.fullmatch(model)
        ):
            return None
        return {
            "provider": "cloudflare",
            "model": model,
            "key": key,
            "account": account,
        }
    return None


def _configs(purpose: str) -> list[dict]:
    rows = []
    for provider in _PROVIDERS:
        if provider == 'zai' and purpose != 'writer':
            continue
        cfg = _config(provider)
        if not cfg:
            continue
        if provider == 'groq' and purpose == 'writer':
            preferred = os.getenv('NEWS_GROQ_WRITER_MODEL', '').strip()
            if preferred in _GROQ_FREE_WRITER_FALLBACKS:
                # Reserve the primary 120B allowance for validation when the
                # operator selects the separately approved free writer model.
                cfg = {**cfg, 'model': preferred}
        rows.append(cfg)
        if provider == 'groq' and purpose == 'writer':
            requested = os.getenv('NEWS_GROQ_WRITER_FALLBACK_MODELS', '').split(',')
            for model in dict.fromkeys(value.strip() for value in requested):
                if model in _GROQ_FREE_WRITER_FALLBACKS and model != cfg['model']:
                    rows.append({**cfg, 'model': model})
    return rows


def _route_ready(cfg: dict, purpose: str) -> bool:
    provider, model = cfg['provider'], cfg['model']
    return (provider not in _UNAVAILABLE[purpose]
            and _route_key(provider, model) not in _UNAVAILABLE[purpose]
            and _provider_ready(provider, model))


def configured_identities(purpose: str = "writer") -> tuple[tuple[str, str], ...]:
    purpose = purpose if purpose in _UNAVAILABLE else "writer"
    rows = []
    for cfg in _configs(purpose):
        if _route_ready(cfg, purpose):
            rows.append((cfg['provider'], cfg["model"]))
    return tuple(rows)


def available(purpose: str = "writer") -> bool:
    return bool(configured_identities(purpose))


def reset() -> None:
    # A new News cycle does not reset the upstream provider's quota window.
    for values in _UNAVAILABLE.values():
        values.clear()
    for key in _CURSOR:
        _CURSOR[key] = 0


def _ordered_configs(purpose: str, avoid_provider: Optional[str] = None) -> list[dict]:
    purpose = purpose if purpose in _UNAVAILABLE else "writer"
    rows = [cfg for cfg in _configs(purpose) if _route_ready(cfg, purpose)]
    if not rows:
        return []
    offset = _CURSOR[purpose] % len(rows)
    _CURSOR[purpose] += 1
    rows = rows[offset:] + rows[:offset]
    if avoid_provider and purpose == "validator":
        # Validation independence is a requirement, including quota fallback.
        # A single surviving writer provider cannot approve its own drafts.
        rows = [row for row in rows if row["provider"] != avoid_provider]
    elif avoid_provider and len(rows) > 1:
        rows.sort(key=lambda row: row["provider"] == avoid_provider)
    return rows


def _choice_text(data: dict) -> Optional[str]:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    choice = choices[0]
    message = choice.get("message") or {}
    if (
        choice.get("finish_reason") != "stop"
        or not isinstance(message, dict)
        or message.get("refusal")
    ):
        return None
    value = message.get("content")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _groq(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    if not reserve_ai_request():
        return None
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1 if json_mode else 0.35,
        "max_completion_tokens": (
            # A complete multi-language article can exceed the old 2200 JSON
            # ceiling. Honor the caller's bounded translation allowance.
            max(700, min(int(max_tokens), 9000))
            if json_mode
            else max(4096, min(int(max_tokens), 9000))
        ),
        "reasoning_effort": "low",
        "stream": False,
    }
    if json_mode:
        # Some Groq free models reject response_format even though they can emit
        # strict JSON when directly instructed.
        payload["messages"][0]["content"] += (
            "\nReturn one valid JSON object only, with no markdown fences or prose."
        )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(95, connect=8), follow_redirects=False
        ) as client:
            response = client.post(
                _GROQ_ENDPOINT,
                headers={
                    "Authorization": "Bearer " + cfg["key"],
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
        if response.status_code != 200:
            _http_failure("groq", response, model=cfg['model'])
            logger.warning("[external_free] groq http_status=%s", response.status_code)
            return None
        return _choice_text(response.json())
    except Exception as exc:
        logger.warning("[external_free] groq request_failed=%s", type(exc).__name__)
        return None


def _gemini(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    if cfg.get('model') != _GEMINI_FREE_MODEL or not reserve_ai_request():
        return None
    generation = {
        "temperature": 0.1 if json_mode else 0.35,
        "maxOutputTokens": max(2048, min(int(max_tokens), 9000)),
        "thinkingConfig": {"thinkingLevel": "minimal"},
    }
    if json_mode:
        generation['responseMimeType'] = 'application/json'
    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=8), follow_redirects=False) as client:
            response = client.post(_GEMINI_ENDPOINT,
                headers={"x-goog-api-key": cfg['key'], "Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": generation,
                })
        if response.status_code != 200:
            _http_failure('gemini', response)
            logger.warning('[external_free] gemini http_status=%s', response.status_code)
            return None
        data = response.json()
        candidates = data.get('candidates') if isinstance(data, dict) else None
        if not isinstance(candidates, list) or len(candidates) != 1:
            return None
        choice = candidates[0]
        if not isinstance(choice, dict) or choice.get('finishReason') != 'STOP':
            return None
        content = choice.get('content')
        parts = content.get('parts') if isinstance(content, dict) else None
        if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
            return None
        if any('functionCall' in part for part in parts):
            return None
        value = ''.join(part['text'] for part in parts
                        if isinstance(part.get('text'), str) and not part.get('thought'))
        return value.strip() or None
    except Exception as exc:
        logger.warning('[external_free] gemini request_failed=%s', type(exc).__name__)
        return None


def _routeway(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    global _ROUTEWAY_VERIFIED_UNTIL
    if cfg.get('model') != _ROUTEWAY_FREE_MODEL or not _ROUTEWAY_LOCK.acquire(blocking=False):
        return None
    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=8), follow_redirects=False) as client:
            if time.monotonic() >= _ROUTEWAY_VERIFIED_UNTIL:
                catalog = client.get(_ROUTEWAY_MODELS_ENDPOINT, headers={'Accept': 'application/json'})
                if catalog.status_code != 200:
                    _http_failure('routeway', catalog)
                    return None
                rows = catalog.json().get('data', [])
                match = next((row for row in rows if isinstance(row, dict) and row.get('id') == _ROUTEWAY_FREE_MODEL), {})
                prices = match.get('pricing') or {}
                if match.get('available') is not True or any(
                    type((prices.get(side) or {}).get('price_per_million_t')) not in (int, float)
                    or prices[side]['price_per_million_t'] != 0 for side in ('input', 'output')
                ):
                    logger.warning('[external_free] routeway free_catalog_unverified')
                    return None
                _ROUTEWAY_VERIFIED_UNTIL = time.monotonic() + 300
            if not reserve_ai_request():
                return None
            payload = {
                'model': _ROUTEWAY_FREE_MODEL,
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                'max_completion_tokens': max(4096, min(int(max_tokens), 9000)),
                'reasoning_effort': 'none',
                'temperature': 0.1 if json_mode else 0.35, 'stream': False,
            }
            if json_mode:
                payload['response_format'] = {'type': 'json_object'}
            response = client.post(_ROUTEWAY_ENDPOINT, headers={
                'Authorization': 'Bearer ' + cfg['key'], 'Content-Type': 'application/json',
            }, json=payload)
        if response.status_code != 200:
            _http_failure('routeway', response)
            logger.warning('[external_free] routeway http_status=%s', response.status_code)
            return None
        # One request at a time, at most five/minute; no waiting inside News.
        _COOLDOWN_UNTIL['routeway'] = time.monotonic() + 13
        data = response.json()
        if data.get('model') != _ROUTEWAY_FREE_MODEL:
            return None
        return _choice_text(data)
    except Exception as exc:
        logger.warning('[external_free] routeway request_failed=%s', type(exc).__name__)
        return None
    finally:
        _ROUTEWAY_LOCK.release()


def _mistral(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    if not reserve_ai_request():
        return None
    if json_mode:
        system += "\nReturn one valid JSON object only, with no markdown fences or prose."
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.1 if json_mode else 0.35,
        "max_tokens": max(256, min(int(max_tokens), 9000)),
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=8), follow_redirects=False) as client:
            response = client.post(
                _MISTRAL_ENDPOINT,
                headers={"Authorization": "Bearer " + cfg["key"],
                         "Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
        if response.status_code != 200:
            _http_failure("mistral", response)
            logger.warning("[external_free] mistral http_status=%s", response.status_code)
            return None
        return _choice_text(response.json())
    except Exception as exc:
        logger.warning("[external_free] mistral request_failed=%s", type(exc).__name__)
        return None


def _zai(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    if cfg.get('model') != _ZAI_FREE_MODEL or not reserve_ai_request():
        return None
    payload = {
        "model": _ZAI_FREE_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
        "temperature": 0.35,
        "max_tokens": max(256, min(int(max_tokens), 9000)),
        "stream": False,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=8), follow_redirects=False) as client:
            response = client.post(_ZAI_ENDPOINT,
                headers={"Authorization": "Bearer " + cfg["key"],
                         "Content-Type": "application/json", "Accept": "application/json"},
                json=payload)
        if response.status_code != 200:
            _http_failure("zai", response)
            # The numeric documented error distinguishes quota/concurrency
            # without leaking the upstream error message or credentials.
            code = "unknown"
            try:
                error = response.json().get("error", {})
                candidate = str(error.get("code", "")) if isinstance(error, dict) else ""
                if re.fullmatch(r"\d{3,6}", candidate):
                    code = candidate
            except (ValueError, TypeError, AttributeError):
                pass
            logger.warning("[external_free] zai http_status=%s error_code=%s", response.status_code, code)
            return None
        return _choice_text(response.json())
    except Exception as exc:
        logger.warning("[external_free] zai request_failed=%s", type(exc).__name__)
        return None


def _cloudflare(cfg: dict, system: str, user: str, max_tokens: int, json_mode: bool):
    if not reserve_ai_request():
        return None
    if json_mode:
        system = system + "\nReturn one valid JSON object only, with no markdown fences or prose."
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1 if json_mode else 0.35,
        "max_tokens": max(256, min(int(max_tokens), 9000)),
        "stream": False,
    }
    if json_mode and cfg['model'] == '@cf/qwen/qwen3-30b-a3b-fp8':
        # The model's published Workers AI schema supports JSON mode. Merely
        # requesting JSON in prose can spend the small validator output window
        # without returning a usable verdict. Keep the strict downstream schema
        # and independent-provider checks; never salvage an incomplete verdict.
        payload['response_format'] = {'type': 'json_object'}
        # Production returned finish=length at 1400 on a short Cyrillic
        # source. Leave bounded room for the model's reasoning and verdict.
        payload['max_tokens'] = max(4096, payload['max_tokens'])
    try:
        with httpx.Client(
            timeout=httpx.Timeout(120, connect=8), follow_redirects=False
        ) as client:
            response = client.post(
                "https://api.cloudflare.com/client/v4/accounts/"
                + cfg["account"]
                + "/ai/run/"
                + cfg["model"],
                headers={
                    "Authorization": "Bearer " + cfg["key"],
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
        if response.status_code != 200:
            _http_failure("cloudflare", response)
            logger.warning(
                "[external_free] cloudflare http_status=%s", response.status_code
            )
            return None
        data = response.json()
        if not isinstance(data, dict) or data.get("success") is not True:
            return None
        result = data.get("result")
        if not isinstance(result, dict):
            return None
        direct = result.get("response")
        if json_mode and isinstance(direct, dict):
            return json.dumps(direct, ensure_ascii=False)
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        value = _choice_text(result)
        if not value:
            choices = result.get('choices')
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            finish = choice.get('finish_reason')
            finish = finish if finish in {'stop', 'length', 'content_filter', 'tool_calls'} else 'unknown'
            logger.warning('[external_free] cloudflare unusable_completion finish=%s json_mode=%s', finish, json_mode)
        return value
    except Exception as exc:
        logger.warning(
            "[external_free] cloudflare request_failed=%s", type(exc).__name__
        )
        return None


def completion(
    *,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool = False,
    purpose: str = "writer",
    avoid_provider: Optional[str] = None,
) -> tuple[Optional[str], tuple[str, str]]:
    purpose = purpose if purpose in _UNAVAILABLE else "writer"
    for cfg in _ordered_configs(purpose, avoid_provider=avoid_provider):
        # An earlier route may have just discovered a provider-wide auth/quota
        # hold. Respect it before trying another config from the same snapshot.
        if not _route_ready(cfg, purpose):
            continue
        if cfg["provider"] == "groq":
            value = _groq(cfg, system, user, max_tokens, json_mode)
        elif cfg["provider"] == "mistral":
            value = _mistral(cfg, system, user, max_tokens, json_mode)
        elif cfg["provider"] == "zai":
            value = _zai(cfg, system, user, max_tokens, json_mode)
        elif cfg["provider"] == "gemini":
            value = _gemini(cfg, system, user, max_tokens, json_mode)
        elif cfg["provider"] == "routeway":
            value = _routeway(cfg, system, user, max_tokens, json_mode)
        else:
            value = _cloudflare(cfg, system, user, max_tokens, json_mode)
        if value:
            _UNKNOWN_QUOTA_STREAK.pop(cfg['provider'], None)
            return value, (cfg["provider"], cfg["model"])
        # Do not hammer a failed transport/shape route again in this cycle.
        _UNAVAILABLE[purpose].add(_route_key(cfg['provider'], cfg['model']))
    return None, ("unknown", "unknown")
