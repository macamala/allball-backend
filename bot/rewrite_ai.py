# bot/rewrite_ai.py

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

if not OPENAI_API_KEY:
    logger.warning(
        "[rewrite_ai] OPENAI_API_KEY is not set. "
        "AI rewrite will not work and raw text will be used."
    )


def _call_openai(prompt: str) -> Optional[str]:
    """
    Low-level call to OpenAI chat completions.
    Returns a single string: first line is English headline,
    blank line, then the rest is the article body.
    """
    if not OPENAI_API_KEY:
        return None

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
                        {
                            "role": "system",
                            "content": (
                                "You are a professional sports journalist.\n"
                                "- You ALWAYS write in natural, fluent ENGLISH only.\n"
                                "- You never include sentences in other languages.\n"
                                "- Ignore any HTML tags (like <img>, <br>, <a>) and never copy them.\n"
                                "- Output format MUST be:\n"
                                "  1) First line: English headline, plain text, no quotes, no markdown.\n"
                                "  2) One blank line.\n"
                                "  3) Several paragraphs of article text in English.\n"
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "temperature": 0.5,
                    "max_tokens": 900,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[rewrite_ai] OpenAI call failed: {e}")
        return None


def rewrite_to_long_form(title: str, raw_text: str, sport: str = "sports") -> str:
    """
    Main function for the rest of the code.

    Input:
      - title: original title (any language)
      - raw_text: text or summary from RSS, may contain HTML
      - sport: 'football', 'basketball', etc.

    Output:
      - A string where:
        * first line = English headline
        * blank line
        * rest = English article body
    """
    base_title = (title or "").strip()
    base_text = (raw_text or "").strip()

    if not base_title and not base_text:
        return ""

    prompt = (
        f"SPORT: {sport}\n\n"
        f"ORIGINAL TITLE:\n{base_title}\n\n"
        "SOURCE TEXT (may contain a different language and some HTML tags):\n"
        f"{base_text}\n\n"
        "TASK:\n"
        "- Write a sports news piece in ENGLISH only.\n"
        "- If the original language is not English, translate and rewrite it into English.\n"
        "- DO NOT include any sentences in the original language.\n"
        "- Ignore HTML tags (<img>, <br>, <a>, etc.) and do not copy them.\n"
        "- Output format MUST be:\n"
        "  First line: English headline, no quotes, no markdown.\n"
        "  Then a blank line.\n"
        "  Then 3–6 paragraphs of English article text.\n"
    )

    ai_result = _call_openai(prompt)

    if not ai_result:
        # fallback: return plain cleaned text (title + raw)
        from html import unescape
        import re

        text = f"{base_title}\n\n{base_text}".strip()
        text = unescape(text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    return ai_result
