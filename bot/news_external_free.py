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


def enabled() -> bool:
    return os.getenv("NEWS_EXTERNAL_FREE_WRITERS_ENABLED") == "1"


def _config(provider: str) -> Optional[dict]:
    if not enabled():
        return None
    if provider == "groq":
        key = (os.getenv("GROQ_API_KEY") or "").strip()
        model = (os.getenv("NEWS_GROQ_MODEL") or "openai/gpt-oss-20b").strip()
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
        if cfg and provider not in _UNAVAILABLE[purpose]:
            rows.append((provider, cfg["model"]))
    return tuple(rows)


def available(purpose: str = "writer") -> bool:
    return bool(configured_identities(purpose))


def reset() -> None:
    for values in _UNAVAILABLE.values():
        values.clear()
    for key in _CURSOR:
        _CURSOR[key] = 0


def _ordered_configs(purpose: str, avoid_provider: Optional[str] = None) -> list[dict]:
    purpose = purpose if purpose in _UNAVAILABLE else "writer"
    rows = [cfg for name in ("groq", "cloudflare") if (cfg := _config(name))]
    rows = [row for row in rows if row["provider"] not in _UNAVAILABLE[purpose]]
    if not rows:
        return []
    offset = _CURSOR[purpose] % len(rows)
    _CURSOR[purpose] += 1
    rows = rows[offset:] + rows[:offset]
    if avoid_provider and len(rows) > 1:
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
