"""Original English NinkoSports journalism from verified source facts."""

import logging
import os
import random
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

_rate_limited = False
_hard_quota = False
_QUOTA_CODES = {
    "insufficient_quota",
    "billing_not_active",
    "billing_hard_limit_reached",
}

SYSTEM_PROMPT = """You are a staff writer for NinkoSports, an English-language sports news site.

Write an ORIGINAL news story from the provided facts.
- English only. Natural sports journalism. No clickbait.
- Do not translate word-for-word or copy the source paragraph-for-paragraph.
- Do not invent scores, quotes, fees, injuries, statistics, dates, or unnamed details.
- If facts are thin, write a short accurate brief. Prefer short and true over long and guessed.
- Never mention AI, translation, or the original publisher.
- Never include URLs, source names, or attribution lines.
- Never include HTML or markers like [+123 chars].

Output format MUST be:
Line 1: headline (plain text, no quotes, no markdown)
Line 2: blank
Line 3: one-sentence summary
Line 4: blank
Then 2-6 short paragraphs of article body.
"""


def reset_openai_rate_limit() -> None:
    """Clear per-run RPM pauses. Do not clear a hard quota/billing lock."""
    global _rate_limited
    _rate_limited = False


def openai_rate_limited() -> bool:
    return _rate_limited or _hard_quota


def _parse_openai_error(resp: httpx.Response) -> dict:
    payload = {}
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        payload = {}
    err = payload.get("error") if isinstance(payload, dict) else {}
    if not isinstance(err, dict):
        err = {}
    retry_after = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    return {
        "type": err.get("type") or "",
        "code": err.get("code") or "",
        "message": (err.get("message") or "").strip(),
        "retry_after": retry_after or "",
    }


def _is_quota_error(info: dict) -> bool:
    code = str(info.get("code") or "").lower()
    err_type = str(info.get("type") or "").lower()
    message = str(info.get("message") or "").lower()
    if code in _QUOTA_CODES or err_type in _QUOTA_CODES:
        return True
    return "exceeded your current quota" in message or "check your plan and billing" in message


def _call_openai(prompt: str) -> Optional[str]:
    global _rate_limited, _hard_quota
    if openai_rate_limited():
        return None
    if not OPENAI_API_KEY:
        logger.warning("[rewrite_ai] OPENAI_API_KEY is not set")
        return None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": OPENAI_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.35,
                        "max_tokens": 700,
                    },
                )
            if resp.status_code == 429:
                info = _parse_openai_error(resp)
                logger.error(
                    "[rewrite_ai] OpenAI 429 type=%s code=%s retry_after=%s message=%s",
                    info["type"] or "unknown",
                    info["code"] or "unknown",
                    info["retry_after"] or "none",
                    info["message"] or resp.text[:300],
                )
                if _is_quota_error(info):
                    _hard_quota = True
                    logger.error(
                        "[rewrite_ai] OpenAI quota/billing lock; skipping AI until process restart"
                    )
                    return None
                if attempt == 0:
                    wait_s = 5.0
                    if info["retry_after"]:
                        try:
                            wait_s = min(20.0, max(1.0, float(info["retry_after"])))
                        except ValueError:
                            wait_s = 5.0
                    time.sleep(wait_s + random.uniform(0.1, 0.6))
                    continue
                _rate_limited = True
                logger.error("[rewrite_ai] OpenAI rate-limited; pausing AI for this run")
                return None
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error("[rewrite_ai] OpenAI call failed: %s", e)
            return None
    return None


def write_ninkosports_story(
    title: str,
    facts: str,
    sport: str = "sports",
    league: str = "",
) -> Optional[str]:
    if openai_rate_limited():
        return None
    facts = (facts or "").strip()
    title = (title or "").strip()
    if not title and not facts:
        return None
    if len(facts) > 3500:
        facts = facts[:3500]
    prompt = (
        f"SPORT: {sport}\n"
        f"COMPETITION: {league or 'unspecified'}\n\n"
        f"ORIGINAL HEADLINE (any language):\n{title}\n\n"
        "VERIFIED SOURCE FACTS (may be another language; use only what is stated):\n"
        f"{facts}\n"
    )
    return _call_openai(prompt)


def parse_ai_output(ai_text: str) -> dict:
    text = (ai_text or "").strip()
    if not text:
        return {}
    lines = [ln.rstrip() for ln in text.splitlines()]
    headline = (lines[0] if lines else "").strip().strip("*").strip('"')
    rest = lines[1:]
    while rest and not rest[0].strip():
        rest = rest[1:]
    summary = ""
    body_lines = rest
    if rest:
        summary = rest[0].strip()
        body_lines = rest[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
    body = "\n".join(body_lines).strip()
    if not body:
        body = summary
        summary = summary[:240]
    if len(summary) > 280:
        summary = summary[:277].rsplit(" ", 1)[0] + "..."
    return {"title": headline, "summary": summary, "body": body}


def rewrite_to_long_form(title: str, raw_text: str, sport: str = "sports") -> str:
    result = write_ninkosports_story(title, raw_text, sport=sport)
    return result or ""
