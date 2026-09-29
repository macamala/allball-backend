"""Explicit free-tier external writer/validator pool for NinkoSports News.

This module never reads or calls OpenAI. It is enabled only by
NEWS_EXTERNAL_FREE_WRITERS_ENABLED=1 and uses already-configured Groq and
Cloudflare credentials. Every actual HTTP attempt is reserved in the same
durable News request ledger. Provider output is never publication authority:
downstream deterministic, semantic, taxonomy, dedupe and image gates decide.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from .news_budget import reserve_ai_request

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_CF_MODEL_RE = re.compile(r"^@[A-Za-z0-9._/-]{3,160}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._/+:-]{3,160}$")
_PURPOSES = ("writer", "validator", "translation")
_UNAVAILABLE = {name: set() for name in _PURPOSES}
_CURSOR = {name: 0 for name in _PURPOSES}
_COOLDOWN_UNTIL = {}


def _provider_ready(provider: str) -> bool:
    return time.monotonic() >= _COOLDOWN_UNTIL.get(provider, 0.0)


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


def _http_failure(provider: str, response) -> None:
    """Share provider quota/auth failures across purposes; never log response bodies."""
    status = response.status_code
    if status not in {401, 403, 429}:
        return
    headers = getattr(response, "headers", {}) or {}
    seconds = _retry_seconds(headers.get("retry-after"))
    dimension = "unknown"
    error_codes = []
    if status == 429:
        try:
            payload = response.json()
            payload = payload if isinstance(payload, dict) else {}
            error = payload.get("error")
            message = str(error.get("message") if isinstance(error, dict) else error or "").lower()
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
                                 ("tokens per minute", "tpm"), ("requests per minute", "rpm")):
                if marker in message or re.search(r"\b" + code + r"\b", message):
                    dimension = code
                    break
        except (ValueError, TypeError, AttributeError):
            pass
        if seconds is None:
            reset_key = "x-ratelimit-reset-requests" if dimension == "rpd" else "x-ratelimit-reset-tokens"
            seconds = _retry_seconds(headers.get(reset_key)) if dimension in {"rpd", "tpm"} else None
    seconds = seconds or (3600 if status in {401, 403} else 600)
    _COOLDOWN_UNTIL[provider] = max(_COOLDOWN_UNTIL.get(provider, 0), time.monotonic() + seconds)
    for unavailable in _UNAVAILABLE.values():
        unavailable.add(provider)
    logger.warning("[external_free] provider=%s status=%s cooldown_seconds=%s limit_dimension=%s error_codes=%s",
                   provider, status, int(seconds), dimension, error_codes)


def enabled() -> bool:
    return os.getenv("NEWS_EXTERNAL_FREE_WRITERS_ENABLED") == "1"


def _config(provider: str) -> Optional[dict]:
    if not enabled():
        return None
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


def configured_identities(purpose: str = "writer") -> tuple[tuple[str, str], ...]:
    purpose = purpose if purpose in _UNAVAILABLE else "writer"
    rows = []
    for provider in ("groq", "cloudflare"):
        cfg = _config(provider)
        if cfg and provider not in _UNAVAILABLE[purpose] and _provider_ready(provider):
            rows.append((provider, cfg["model"]))
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
    rows = [cfg for name in ("groq", "cloudflare") if (cfg := _config(name))]
    rows = [row for row in rows if row["provider"] not in _UNAVAILABLE[purpose]
            and _provider_ready(row["provider"])]
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
            max(700, min(int(max_tokens), 2200))
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
            _http_failure("groq", response)
            logger.warning("[external_free] groq http_status=%s", response.status_code)
            return None
        return _choice_text(response.json())
    except Exception as exc:
        logger.warning("[external_free] groq request_failed=%s", type(exc).__name__)
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
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        return _choice_text(result)
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
        if cfg["provider"] == "groq":
            value = _groq(cfg, system, user, max_tokens, json_mode)
        else:
            value = _cloudflare(cfg, system, user, max_tokens, json_mode)
        if value:
            return value, (cfg["provider"], cfg["model"])
        # Do not hammer a failed transport/shape route again in this cycle.
        _UNAVAILABLE[purpose].add(cfg["provider"])
    return None, ("unknown", "unknown")
