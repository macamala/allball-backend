"""One-shot News connection diagnostic, NOT an ingestion worker.

Only GLM-4.7-Flash may generate text here. Other providers receive metadata GETs.
No database, app, collector, scheduler or ledger module is imported or modified.
Run only on the existing News service with NEWS_FREE_PROBE=1 and --once.
An exit0 means the diagnostic completed, not that providers or News are healthy.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import httpx

SERVICE_ID = "be857be7-a029-4663-81c7-bcde75efc482"
LANGUAGES = ("en", "sr", "es", "de", "fr", "it", "pt")
METADATA = (
    ("groq", "https://api.groq.com/openai/v1/models", "GROQ_API_KEY"),
    ("llm7", "https://api.llm7.io/v1/models", "LLM7_API_KEY"),
    ("xkiro", "https://api.xkiro.com/v1/usage", "XKIRO_API_KEY"),
    ("nara", "https://router.bynara.id/v1/models", "NARAROUTER_API_KEY"),
    ("airforce", "https://api.airforce/v1/models", "AIRFORCE_API_KEY"),
    ("cloudflare", "https://api.cloudflare.com/client/v4/user/tokens/verify", "CLOUDFLARE_API_TOKEN"),
)


def request_json(method, url, key, payload=None):
    """No retries, redirects, response-body logging or exception messages."""
    start = time.monotonic()
    report = {"http_status": None, "reply_received": False}
    try:
        with httpx.Client(timeout=httpx.Timeout(65, connect=8), follow_redirects=False) as client:
            with client.stream(method, url, headers={"Authorization": "Bearer " + key,
                               "Accept": "application/json"}, json=payload) as response:
                report.update(http_status=response.status_code, reply_received=True)
                if response.status_code != 200:
                    report["result"] = "http_non_success"
                    return report, None
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000 or time.monotonic() - start > 85:
                        report["result"] = "response_limit"
                        return report, None
                data = json.loads(raw)
                report["result"] = "json_received" if isinstance(data, dict) else "unexpected_json"
                return report, data if isinstance(data, dict) else None
    except Exception as error:
        report["result"] = "network_unavailable" if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)) else "request_failed"
        report["error_class"] = type(error).__name__
        return report, None
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 2)


def safe_number(value):
    return value if type(value) in (int, float) and 0 <= value < 10**15 else None


def inspect_provider(row):
    name, url, variable = row
    key = os.environ.get(variable, "").strip()
    result = {"provider": name, "operation": "metadata_only", "key_present": bool(key),
              "generation_verified": False}
    if not key:
        return {**result, "result": "missing_key"}
    status, data = request_json("GET", url, key)
    result.update(status)
    if data is None:
        return result
    if name == "cloudflare":
        result["token_active"] = bool(data.get("success") and isinstance(data.get("result"), dict) and data["result"].get("status") == "active")
        result["workers_ai_permission_verified"] = False
    elif name == "xkiro":
        free = data.get("free_tokens")
        if isinstance(free, dict):
            result["free_tokens"] = {field: safe_number(free.get(field)) for field in ("limit_per_day", "remaining", "used_today")}
    else:
        models = data.get("data")
        if isinstance(models, list):
            result["model_count"] = len(models)
            result["model_ids"] = [m["id"] for m in models[:80] if isinstance(m, dict) and isinstance(m.get("id"), str) and re.fullmatch(r"[a-zA-Z0-9._/@:+-]{1,120}", m["id"])]
            result["free_entitlement_verified"] = False
    return result


def free_sample():
    """Synthetic text stays in diagnostic logs; it is never a published story."""
    key = os.environ.get("ZAI_API_KEY", "").strip()
    report = {"provider": "zai", "model": "glm-4.7-flash", "key_present": bool(key),
              "operation": "one_free_completion", "content_kind": "synthetic_diagnostic_fixture",
              "new_articles_published": 0, "quality_accepted": False}
    if not key:
        return {**report, "result": "missing_key"}
    prompt = (
        "This is a SYNTHETIC integration fixture, NOT a real sports report. "
        "Use only these fictional facts: in a practice match, North Club beat South Club 2-1. "
        "North led 1-0 at half-time. No scorers, venue, date or league are supplied. "
        "Write a short original English match brief (40-60 words) without adding any facts. "
        "Then translate that exact brief in full into Serbian Latin, Spanish, German, French, Italian and Portuguese. "
        "Return ONLY a JSON object with exactly these string keys: en,sr,es,de,fr,it,pt. "
        "No extra notes, markdown or invented details."
    )
    status, data = request_json("POST", "https://api.z.ai/api/paas/v4/chat/completions", key,
        {"model": "glm-4.7-flash", "messages": [{"role": "user", "content": prompt}],
         "thinking": {"type": "disabled"}, "max_tokens": 2500, "stream": False})
    report.update(status)
    if data is None:
        return report
    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        report["usage"] = {field: safe_number(usage.get(field)) for field in ("prompt_tokens", "completion_tokens", "total_tokens")}
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        report["result"] = "missing_completion"
        return report
    choice = choices[0]
    report["finish_reason"] = choice.get("finish_reason") if choice.get("finish_reason") in ("stop", "length", "content_filter", "tool_calls") else "other"
    message = choice.get("message") or {}
    text = message.get("content") if isinstance(message, dict) else None
    if choice.get("finish_reason") != "stop" or not isinstance(text, str) or message.get("refusal"):
        report["result"] = "incomplete_or_refused"
        return report
    try:
        translations = json.loads(text)
    except (ValueError, TypeError):
        report["result"] = "invalid_output_json"
        return report
    if not isinstance(translations, dict) or set(translations) != set(LANGUAGES) or not all(isinstance(v, str) and 20 <= len(v) <= 3000 for v in translations.values()):
        report["result"] = "incomplete_languages"
        return report
    # Only reviewable fictional text is emitted; credential substrings are redacted.
    secrets = [os.environ.get(var, "") for _, _, var in METADATA] + [key]
    for language in LANGUAGES:
        for secret in secrets:
            if len(secret) >= 12:
                translations[language] = translations[language].replace(secret, "[REDACTED]")
    report.update(result="complete_fixture_received", translations=translations,
                  seven_language_shape_verified=True,
                  note="Human review still required. A short fixture is not long-article throughput or production acceptance.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.once or os.environ.get("NEWS_FREE_PROBE") != "1" or os.environ.get("RAILWAY_SERVICE_ID") != SERVICE_ID:
        print(json.dumps({"result": "explicit_existing_news_service_probe_required", "news_started": False}))
        return 78
    report = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "mode": "bounded_existing_news_service_probe", "new_articles_published": 0,
              "paid_model_selected": False, "database_accessed": False, "news_worker_started": False}
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = [pool.submit(inspect_provider, row) for row in METADATA]
        sample = pool.submit(free_sample)
        report["providers"] = [future.result() for future in futures]
        report["sample"] = sample.result()
    print("NEWS_FREE_PROBE_REPORT " + json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
