"""Single bounded provider writing/translation fixture. Never starts News or accesses DB."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from news_free_probe import LANGUAGES, METADATA, SERVICE_ID, request_json, safe_number

PROMPT = (
    "This is a SYNTHETIC test fixture, never a real news story. "
    "Fictional facts only: North Club beat South Club 2-1 in a practice match. "
    "North led 1-0 at half-time. No date, venue, scorers or league are supplied. "
    "Write an original English brief of 40-60 words using only those facts, without filler. "
    "Translate that same brief completely into Serbian Latin, Spanish, German, French, Italian and Portuguese. "
    "Return ONLY a JSON object with string keys en,sr,es,de,fr,it,pt. No markdown, notes or added facts."
)


def clean_model(model):
    value = model.get("id")
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._/@:+-]{1,120}", value):
        return None
    row = {"id": value}
    for field, number in model.items():
        if any(term in field.lower() for term in ("price", "token", "context")) and type(number) in (int, float):
            row[field] = safe_number(number)
    for field in ("tier", "type"):
        value = model.get(field)
        if isinstance(value, str) and re.fullmatch(r"[a-zA-Z_-]{1,32}", value):
            row[field] = value
    pricing = model.get("pricing")
    if isinstance(pricing, dict):
        row["pricing"] = {k: str(v) for k, v in pricing.items() if re.fullmatch(r"[A-Za-z_]{1,40}", k) and re.fullmatch(r"[0-9.eE+-]{1,30}", str(v))}
    return row


def catalog(name, endpoint, keyname):
    key = os.environ.get(keyname, "").strip()
    if not key:
        return {"provider": name, "result": "missing_key"}, []
    status, data = request_json("GET", endpoint, key)
    rows = data.get("data", []) if isinstance(data, dict) else []
    rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    keep = rows if name == "llm7" else [row for row in rows if str(row.get("id", "")).endswith(":free")]
    return {"provider": name, **status, "models": [cleaned for row in keep[:80] if (cleaned := clean_model(row))]}, rows


def completion(name, url, variable, model, native=False):
    key = os.environ.get(variable, "").strip()
    report = {"provider": name, "model": model, "content_kind": "synthetic_fixture", "quality_accepted": False}
    if not key:
        return {**report, "result": "missing_key"}
    payload = {"messages": [{"role": "user", "content": PROMPT}], "stream": False}
    if not native:
        payload["model"] = model
    if name == "groq":
        payload.update(max_completion_tokens=4096, reasoning_effort="low", response_format={"type":"json_object"})
    else:
        payload.update(max_tokens=4096)
    status, data = request_json("POST", url, key, payload)
    report.update(status)
    if not isinstance(data, dict):
        return report
    if native:
        if data.get("success") is not True:
            return {**report, "result": "provider_failure"}
        data = data.get("result") or {}
    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        report["usage"] = {k: safe_number(usage.get(k)) for k in ("prompt_tokens","completion_tokens","total_tokens")}
    choices = data.get("choices") or []
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        message = choice.get("message") or {}
        if not isinstance(message, dict) or message.get("refusal") or choice.get("finish_reason") != "stop":
            return {**report, "result": "incomplete_or_refused"}
        text = message.get("content")
        report["finish_reason"] = "stop"
    else:
        text = data.get("response")
        report["finish_reason"] = "not_supplied"
    if not isinstance(text, str):
        return {**report, "result": "no_visible_output"}
    # Permit a wrapper fence, but not removal of reasoning or content to fake completeness.
    if text.strip().startswith("```json") and text.strip().endswith("```"):
        text = text.strip()[7:-3].strip()
    try:
        result = json.loads(text)
    except (ValueError, TypeError):
        return {**report, "result": "invalid_output_json", "visible_characters": len(text)}
    if not isinstance(result, dict) or set(result) != set(LANGUAGES) or not all(isinstance(v, str) and 20 <= len(v) <= 3000 for v in result.values()):
        return {**report, "result": "incomplete_languages"}
    secrets = [os.environ.get(v, "") for _,_,v in METADATA] + [os.environ.get("ZAI_API_KEY", "")]
    for language in LANGUAGES:
        for secret in secrets:
            if len(secret) >= 12:
                result[language] = result[language].replace(secret, "[REDACTED]")
    report.update(result="seven_language_fixture_received", translations=result,
                  note="Not a long-article capacity or factuality certification. No publication.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.once or os.environ.get("NEWS_FREE_PROBE") != "1" or os.environ.get("RAILWAY_SERVICE_ID") != SERVICE_ID:
        print(json.dumps({"result":"explicit_existing_news_service_probe_required"}));return 78
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    report = {"observed_at":datetime.now(timezone.utc).isoformat(), "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "new_articles_published":0,"database_accessed":False,"news_worker_started":False,
              "paid_fallback":False,"mode":"bounded_generation_fixture"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        groq = pool.submit(completion, "groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "openai/gpt-oss-20b")
        cf = pool.submit(completion, "cloudflare", f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/qwen/qwen3-30b-a3b-fp8", "CLOUDFLARE_API_TOKEN", "@cf/qwen/qwen3-30b-a3b-fp8", True) if re.fullmatch(r"[a-f0-9]{32}", account) else None
        llm7 = pool.submit(catalog,"llm7","https://api.llm7.io/v1/models","LLM7_API_KEY")
        airforce = pool.submit(catalog,"airforce","https://api.airforce/v1/models","AIRFORCE_API_KEY")
        report["generation"]=[groq.result(),cf.result() if cf else {"provider":"cloudflare","result":"missing_or_invalid_account_id"}]
        llm7_report,_ = llm7.result()
        airforce_report,air_models = airforce.result()
        report["catalogs"]=[llm7_report,airforce_report]
    # Only an explicitly advertised :free variant may run; never a paid bare alias.
    available={row.get("id") for row in air_models if isinstance(row.get("id"), str)}
    permitted=("deepseek-v3.2:free","gpt-oss-120b:free","glm-4.7-flash:free","qwen3-30b-a3b-instruct-2507:free")
    selected=next((model for model in permitted if model in available),None)
    if selected:
        report["generation"].append(completion("airforce","https://api.airforce/v1/chat/completions","AIRFORCE_API_KEY",selected))
    else:
        report["generation"].append({"provider":"airforce","result":"no_reviewed_free_model_variant"})
    print("NEWS_FREE_GENERATION_REPORT "+json.dumps(report,ensure_ascii=False),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
