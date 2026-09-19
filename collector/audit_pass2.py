"""Pass-2 diagnostic: inspect unique mapped generic-http URLs once."""

from __future__ import annotations

import json
import re
import socket
from collections import Counter
from typing import Any, Dict, List
from urllib.parse import urljoin

from collector.family_catalog import JSON_ADAPTERS
from collector.http import fetch_bytes
from collector.registry import build_runtime_registry

JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.I | re.S)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TABLE_RE = re.compile(r"<table", re.I)
SCORE_HINT = re.compile(r"\b\d{1,3}\s*[-–:]\s*\d{1,3}\b|vs\.?|fixture|result|kick.?off", re.I)
FIXTURE_PATH = re.compile(
    r"/(fixture|fixtures|results?|matches|schedule|draw|scores?|timetable|calendar|games)(/|$|\?)",
    re.I,
)


def _title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:140]


def inspect(url: str, status: int, body: str, error: str) -> Dict[str, Any]:
    sample = body[:250000]
    jsonld = JSONLD_RE.findall(sample)
    hrefs = HREF_RE.findall(sample)
    links = []
    for href in hrefs:
        if FIXTURE_PATH.search(href):
            links.append(urljoin(url, href))
    links = list(dict.fromkeys(links))[:8]
    looks_json = sample.lstrip()[:1] in "{["
    return {
        "status": status,
        "error": error,
        "size": len(body.encode("utf-8", "replace")),
        "title": _title(sample),
        "tables": len(TABLE_RE.findall(sample)),
        "score_hints": len(SCORE_HINT.findall(sample[:80000])),
        "jsonld": len(jsonld),
        "sports_jsonld": any("SportsEvent" in blob or '"Event"' in blob for blob in jsonld[:12]),
        "next_data": bool(NEXT_RE.search(sample)),
        "looks_json": looks_json,
        "fixture_links": links,
        "empty_copy": any(tok in sample.lower() for tok in ("no matches", "no fixtures", "coming soon")),
    }


def classify(info: Dict[str, Any]) -> str:
    if info.get("status") in {401, 403, 404, 410}:
        return "SOURCE_RESPONSE_CHANGED"
    if info.get("status") == 0 or info.get("error"):
        return "NETWORK_ERROR"
    if info.get("looks_json") and info.get("size", 0) > 80:
        return "PUBLIC_JSON_AVAILABLE"
    if info.get("next_data") or info.get("sports_jsonld"):
        return "EMBEDDED_JSON_AVAILABLE"
    if info.get("fixture_links"):
        return "INDEX_REQUIRES_TRAVERSAL"
    if info.get("tables", 0) and info.get("score_hints", 0) >= 3:
        return "PARSER_MISSING"
    if info.get("score_hints", 0) >= 8:
        return "PARSER_MISSING"
    if info.get("tables", 0):
        return "PARSER_BROKEN"
    if info.get("empty_copy") or info.get("size", 0) < 1500:
        return "GENUINELY_EMPTY"
    return "GENUINELY_EMPTY"


def unique_generic_targets() -> List[Dict[str, Any]]:
    runtime = build_runtime_registry()
    seen = set()
    rows = []
    extra_families = {"startgg", "futsalplanet"}
    for mapping in runtime["mappings"]:
        if not mapping.get("enabled") and mapping.get("source_family") not in extra_families:
            continue
        family = mapping["source_family"]
        adapter = mapping.get("adapter_key")
        if adapter != "generic-http" and family not in extra_families:
            if family in JSON_ADAPTERS:
                continue
        url = (mapping.get("source_config") or {}).get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "competition_id": mapping["competition_id"],
                "family": family,
                "url": url,
                "adapter": adapter,
            }
        )
    return rows


def main() -> None:
    import collector.http as httpmod

    httpmod.DEFAULT_TIMEOUT = 10
    socket.setdefaulttimeout(10)
    targets = unique_generic_targets()
    results = []
    for item in targets:
        fetched = fetch_bytes(item["url"], timeout=10)
        body = ""
        error = fetched.error or ""
        status = fetched.http_status or 0
        if fetched.ok and isinstance(fetched.payload, (bytes, bytearray)):
            body = fetched.payload.decode("utf-8", "replace")
        elif isinstance(fetched.payload, (bytes, bytearray)):
            body = fetched.payload[:2000].decode("utf-8", "replace")
        info = inspect(item["url"], status, body, error)
        audit = classify(info)
        results.append({**item, **info, "audit": audit})
        print(
            f"{audit:24} {item['family'][:22]:22} {item['competition_id'][:28]:28} "
            f"{status} {info['size']:7} t={info['tables']} s={info['score_hints']} "
            f"links={len(info['fixture_links'])} next={int(info['next_data'])}",
            flush=True,
        )
    counts = Counter(row["audit"] for row in results)
    family = Counter((row["family"], row["audit"]) for row in results)
    payload = {
        "targets": len(results),
        "audit_counts": dict(counts),
        "by_family": [{"family": f, "audit": a, "n": n} for (f, a), n in family.most_common()],
        "results": results,
    }
    with open("pass2_audit.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print("COUNTS", json.dumps(dict(counts), indent=2))


if __name__ == "__main__":
    main()
