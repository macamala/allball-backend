"""One fail-closed writer router for NinkoSports News.

Writers are interchangeable generation engines, never publication authorities.
Every HTTP attempt consumes the shared durable request budget. The downstream
fact-lock, correction memory and public index decide whether text may publish.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
import re
from typing import Callable, Optional

import httpx

from .news_budget import reserve_ai_request
from . import rewrite_ai as openai_writer

logger = logging.getLogger(__name__)

_PROVIDER_ORDER = ("groq", "cloudflare", "openai")
_ALLOWED = set(_PROVIDER_ORDER)
_UNAVAILABLE: set[str] = set()
_REJECTIONS: dict[tuple[str, str], int] = {}
_POLICY: ContextVar[Optional[Callable[[str, str], bool]]] = ContextVar(
    "news_writer_policy", default=None
)
_LAST: ContextVar[tuple[str, str]] = ContextVar(
    "news_last_writer", default=("unknown", "unknown")
)


def _order(env=None) -> tuple[str, ...]:
    env = os.environ if env is None else env
    raw = str(env.get("NEWS_WRITER_ORDER") or "").strip()
    if not raw:
        return _PROVIDER_ORDER
    rows = []
    for value in raw.split(","):
        name = value.strip().lower()
        if name in _ALLOWED and name not in rows:
            rows.append(name)
    return tuple(rows)


def _config(provider: str, env=None) -> Optional[dict]:
    env = os.environ if env is None else env
    if provider == "groq":
        key = str(env.get("GROQ_API_KEY") or "").strip()
        if not key:
            return None
        return {
            "provider": "groq",
            "model": str(env.get("NEWS_GROQ_MODEL") or "openai/gpt-oss-20b").strip(),
            "key": key,
        }
    if provider == "cloudflare":
        key = str(env.get("CLOUDFLARE_API_TOKEN") or "").strip()
        account = str(env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        if not key or not re.fullmatch(r"[A-Fa-f0-9]{32}", account):
            return None
        return {
            "provider": "cloudflare",
            "model": str(
                env.get("NEWS_CLOUDFLARE_MODEL")
                or "@cf/qwen/qwen3-30b-a3b-fp8"
            ).strip(),
            "key": key,
            "account": account,
        }
    if provider == "openai":
        key = str(env.get("OPENAI_API_KEY") or "").strip()
        if not key:
            return None
        return {
            "provider": "openai",
            "model": str(env.get("OPENAI_MODEL") or "gpt-4.1-mini").strip(),
            "key": key,
        }
    return None


def configured_writer_identities(env=None) -> tuple[tuple[str, str], ...]:
    rows = []
    for provider in _order(env):
        cfg = _config(provider, env)
        if cfg:
            rows.append((provider, cfg["model"]))
    return tuple(rows)


def configuration_reason(env=None) -> Optional[str]:
    env = os.environ if env is None else env
    raw = str(env.get("NEWS_WRITER_ORDER") or "").strip()
    if raw:
        names = [item.strip().lower() for item in raw.split(",") if item.strip()]
        if (
            not names
            or any(name not in _ALLOWED for name in names)
            or len(set(names)) != len(names)
        ):
            return "invalid_news_writer_order"
    return None if configured_writer_identities(env) else "news_ai_key_missing"


def last_writer_identity() -> tuple[str, str]:
    return _LAST.get()


@contextmanager
def writer_policy_scope(predicate: Optional[Callable[[str, str], bool]]):
    token = _POLICY.set(predicate)
    try:
        yield
    finally:
        _POLICY.reset(token)


def _allowed_by_policy(provider: str, model: str) -> bool:
    predicate = _POLICY.get()
    if predicate is None:
        return True
    try:
        return bool(predicate(provider, model))
    except Exception:
        # A broken trust policy must never become permission to generate.
        return False


def _mark_unavailable(provider: str, status: Optional[int] = None) -> None:
    if status in {400, 401, 403, 404, 408, 409, 422, 429} or (
        isinstance(status, int) and status >= 500
    ):
        _UNAVAILABLE.add(provider)


def _post(provider: str, url: str, headers: dict, payload: dict) -> Optional[dict]:
    if not reserve_ai_request():
        logger.warning("[news_writer] shared request budget unavailable")
        return None
    try:
        with httpx.Client(
            timeout=httpx.Timeout(65, connect=8),
            follow_redirects=False,
        ) as client:
            response = client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            logger.warning(
                "[news_writer] provider=%s http_status=%s",
                provider,
                response.status_code,
            )
            _mark_unavailable(provider, response.status_code)
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning(
            "[news_writer] provider=%s request_failed=%s",
            provider,
            type(exc).__name__,
        )
        return None


def _choice_text(data: dict) -> Optional[str]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    choice = choices[0]
    message = choice.get("message")
    if (
        choice.get("finish_reason") != "stop"
        or not isinstance(message, dict)
        or message.get("refusal")
    ):
        return None
    value = message.get("content")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _groq(cfg: dict, prompt: str) -> Optional[str]:
    data = _post(
        "groq",
        "https://api.groq.com/openai/v1/chat/completions",
        {
            "Authorization": "Bearer " + cfg["key"],
            "Content-Type": "application/json",
        },
        {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": openai_writer.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_completion_tokens": 1800,
            "reasoning_effort": "low",
            "stream": False,
        },
    )
    return _choice_text(data or {})


def _cloudflare(cfg: dict, prompt: str) -> Optional[str]:
    model = cfg["model"]
    if not re.fullmatch(r"@[A-Za-z0-9._/-]{3,160}", model):
        return None
    data = _post(
        "cloudflare",
        (
            "https://api.cloudflare.com/client/v4/accounts/"
            + cfg["account"]
            + "/ai/run/"
            + model
        ),
        {
            "Authorization": "Bearer " + cfg["key"],
            "Content-Type": "application/json",
        },
        {
            "messages": [
                {"role": "system", "content": openai_writer.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1800,
            "stream": False,
        },
    )
    if not data or data.get("success") is not True:
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    direct = result.get("response")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return _choice_text(result)


def _openai(cfg: dict, prompt: str) -> Optional[str]:
    # Existing adapter already reserves every real HTTP attempt, including its
    # bounded 429 retry. Keep one accounting path rather than double-reserving.
    openai_writer.OPENAI_API_KEY = cfg["key"]
    openai_writer.OPENAI_MODEL = cfg["model"]
    return openai_writer._call_openai(prompt)


def note_writer_rejection(
    provider: str,
    model: str,
    *,
    threshold: int = 3,
) -> int:
    """Short-lived circuit for deterministic rejects; never persistent learning."""
    identity = (provider or "unknown", model or "unknown")
    count = int(_REJECTIONS.get(identity, 0)) + 1
    _REJECTIONS[identity] = count
    if count >= max(1, threshold) and provider in _ALLOWED:
        _UNAVAILABLE.add(provider)
    return count


def reset_writer_state() -> None:
    _UNAVAILABLE.clear()
    _REJECTIONS.clear()
    _LAST.set(("unknown", "unknown"))
    openai_writer.reset_openai_rate_limit()


def writer_rate_limited() -> bool:
    identities = configured_writer_identities()
    if not identities:
        return True
    for provider, model in identities:
        if provider in _UNAVAILABLE:
            continue
        if provider == "openai" and openai_writer.openai_rate_limited():
            continue
        if _allowed_by_policy(provider, model):
            return False
    return True


def write_ninkosports_story(
    title: str,
    facts: str,
    sport: str = "sports",
    league: str = "",
    retry_for_length: bool = False,
    correction_reason: str = "",
    deprioritize_writers: Optional[set[tuple[str, str]]] = None,
) -> Optional[str]:
    title = (title or "").strip()
    facts = (facts or "").strip()
    if not title and not facts:
        return None
    prompt = openai_writer.build_story_prompt(
        title=title,
        facts=facts,
        sport=sport,
        league=league,
        retry_for_length=retry_for_length,
        correction_reason=correction_reason,
    )
    configs = [
        cfg for name in _order()
        if (cfg := _config(name)) is not None
    ]
    deprioritized = set(deprioritize_writers or ())
    configs.sort(
        key=lambda cfg: (
            (cfg["provider"], cfg["model"]) in deprioritized,
            _order().index(cfg["provider"]),
        )
    )
    for cfg in configs:
        provider, model = cfg["provider"], cfg["model"]
        if provider in _UNAVAILABLE:
            continue
        if provider == "openai" and openai_writer.openai_rate_limited():
            continue
        if not _allowed_by_policy(provider, model):
            continue
        _LAST.set((provider, model))
        if provider == "groq":
            result = _groq(cfg, prompt)
        elif provider == "cloudflare":
            result = _cloudflare(cfg, prompt)
        else:
            result = _openai(cfg, prompt)
        if result:
            return result
        # A configured provider that returned no usable completion is held for
        # the remainder of this cycle; the next provider gets the story.
        _UNAVAILABLE.add(provider)
    return None
