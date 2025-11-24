import os
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You are a senior sports journalist. "
    "You write detailed, 400–600 word sports news and match reports "
    "in clear English. You structure articles with intro, key moments, "
    "tactical notes, context, and what it means next."
)


def rewrite_to_long_form(title: str, raw_text: str) -> str:
    prompt = (
        f"Title: {title}\n\n"
        f"Source text:\n{raw_text}\n\n"
        "Write a fresh, original long-form sports news article based on this. "
        "Do not copy sentences. Keep it factual and engaging. "
        "Length: 400–600 words."
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()
