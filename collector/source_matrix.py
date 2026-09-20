"""Final mapped-source matrix from inventory + proven capability + latest smoke.

Does not live-fetch 180 competitions. Capability is preserved separately from
current health (429 / DNS / empty calendar).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collector.capability_ledger import proven_status
from collector.discovery_inventory import COVERAGE
from collector.coverage_capability import FAMILY_EVIDENCE, annotate_record
from collector.event_quality import (
    BRACKET,
    HEAD_TO_HEAD,
    MEET,
    MULTI_EVENT_MEET,
    RACE,
    TEAM_MATCH,
    TOURNAMENT,
    event_type_for,
)
from collector.registry import build_runtime_registry

ROOT = Path(__file__).resolve().parent.parent


def _canonical_competition_ids() -> set:
    import subprocess

    try:
        raw = subprocess.check_output(["git", "show", "HEAD:source_matrix_final.json"], cwd=str(ROOT))
        payload = json.loads(raw)
        return {row["competition"] for row in payload.get("competitions") or []}
    except Exception:
        current = json.loads((ROOT / "source_matrix_final.json").read_text(encoding="utf-8")) if (ROOT / "source_matrix_final.json").exists() else {}
        return {row["competition"] for row in current.get("competitions") or []}

# Already identified during discovery / earlier live passes.
KNOWN_RESTRICTED = {
    "plusliga-web": "official HTML/API returns 403; discovery listed plusliga.pl",
    "super-rugby-web": "official HTML restricted; discovery status restricted",
    "afc-web": "the-afc.com returns 403 on collector UA",
    "startgg": "GraphQL requires credentials",
    "fortuna-liga-cz-web": "fortunaliga.cz returns 403",
    "nrl-web": "official NRL path restricted to collector UA",
    "flashscore": "Flashscore ToU: no copy/download/reuse without written authorization",
    "hltv-web": "HLTV terms forbid scraping and commercial use of site materials",
    "vlr-web": "VLR terms forbid automated access and commercial reuse of content",
    "lolesports-web": "Riot Terms of Service forbid scraping/expropriating data and unauthorized bots/scripts interacting with Riot Services",
    "valorantesports-web": "TECHNICALLY_WORKING public HTML; TERMS_RESTRICTED: Riot ToS forbid scraping/expropriating data and unauthorized bots/scripts; ingestion not enabled",
    "ewc-owcs-web": "TECHNICALLY_WORKING esportsworldcup.com OWCS standings; TERMS_RESTRICTED: EWC Terms of Use forbid data mining, harvesting, scraping, or other unauthorized collection of data",
    "blizzard-owcs-recaps": "TECHNICALLY_WORKING esports.overwatch.com recap HTML; TERMS_RESTRICTED Blizzard consumer/esports properties; bot/script ingestion not enabled",
    "overwatch-esports-web": "TECHNICALLY_WORKING public HTML; TERMS_RESTRICTED Blizzard Overwatch esports properties; bot/script ingestion not enabled",
    "owgr-web": "OWGR terms: website material may not be reproduced/adapted/transmitted without prior written permission except private viewing or Sharing Widget",
    "europeantour-web": "europeantour.com returned 403 ACCESS_DENIED from Railway; live coverage not claimed",
}

KNOWN_PARTIAL = {
    "microplus-timing": "World Aquatics coverage is partial (verified scope only)",
    "nba-japan-web": "Japan association result pages for selected Super 750 days, not BWF-wide",
    "jla-web": "Host WP score hub; independence from World Lacrosse CMS is derived",
}

KNOWN_SOURCE_CHANGED = {
    "sackmann-tennis": "mapped atp_matches_{year}.csv 404; same-repo listing used if files moved",
}

KNOWN_NETWORK = {
    "lnr-web": "TLS: unable to get local issuer certificate (verification left enabled)",
    "isl-web": "TLS: remote certificate expired (verification left enabled)",
    "super-league-web": "TLS: hostname mismatch for superleague.co.uk (verification left enabled)",
}


def _load_proof() -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = ROOT / "collector" / "proof_ledger.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for key, row in (payload.get("pairs") or {}).items():
        if "|" not in str(key):
            continue
        cid, family = str(key).split("|", 1)
        row = row or {}
        if row.get("status") == "WORKING" and not _strict_working_sample(row.get("sample") or "", competition_id=cid):
            row = dict(row)
            row["status"] = "EMPTY_ARCHIVE"
            row["reason"] = "page reachable but extracted names were not plausible canonical events"
        out[(cid, family)] = row
    return out


def _strict_working_sample(sample: str, competition_id: str = "", sport_id: str = "") -> bool:
    text = (sample or "").strip()
    kind = event_type_for(competition_id, sport_id)
    lowered_all = text.lower()
    if any(
        token in lowered_all
        for token in (
            "cookie",
            "subscribe",
            "function ",
            "weather",
            "full calendar",
            "estimated purse",
            "arrow_drop",
            "like us",
            "off time",
            "searchtab",
            "todos",
            "gols vs",
            "rank vs",
            "event #",
            "tune in",
            "hungarian capital",
            "white sox",
        )
    ):
        return False
    if kind in {RACE, MEET, TOURNAMENT, MULTI_EVENT_MEET}:
        if re.search(r"\d{4}", text) and re.search(r"[A-Za-z]{3}", text):
            if " vs " in text:
                home, away = text.split(" vs ", 1)
                away = away.strip()
                if away.lower().split()[0] in {"race", "filly", "colt", "news", "local"} and kind != MEET:
                    return False
                if away.lower().split()[0] in {"filly", "colt", "news"}:
                    return False
            return True
        return False
    if text.endswith(" vs"):
        text = text + " "
    if " vs " not in text:
        return False
    home, away = text.split(" vs ", 1)
    home, away = home.strip(), away.strip()
    if not home or not away:
        return False
    lowered = f"{home} {away}".lower()
    if len(home.split()) > 8 or len(away.split()) > 8:
        return kind in {BRACKET, HEAD_TO_HEAD} and len(home.split()) <= 12 and len(away.split()) <= 12
    if home.lower() == away.lower():
        return False
    if away.lower() in {"race", "local", "news", "filly", "colt", "sex", "vs", "rider", "rank", "f. c."}:
        return False
    if re.search(r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", away, re.I):
        return False
    if not re.search(r"[A-Za-z]{3}", home):
        return False
    return True


def _enabled_mappings() -> Dict[str, List[Dict[str, Any]]]:
    runtime = build_runtime_registry()
    by_comp: Dict[str, List[Dict[str, Any]]] = {}
    for mapping in runtime["mappings"]:
        if not mapping.get("enabled"):
            continue
        by_comp.setdefault(mapping["competition_id"], []).append(mapping)
    for rows in by_comp.values():
        rows.sort(key=lambda row: int(row.get("priority") or 100))
    return by_comp


def _load_smokes() -> List[Dict[str, Any]]:
    rows = []
    for name in ("smoke_pass2.json", "smoke_pass3.json", "smoke_pass4.json", "smoke_pass5.json"):
        path = ROOT / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.extend(payload.get("results") or [])
    return rows


def _family_evidence() -> Dict[Tuple[str, str], Dict[str, Any]]:
    evidence: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in _load_smokes():
        cid = row.get("competition_id") or ""
        for mapping in row.get("mapping_results") or []:
            family = mapping.get("family") or ""
            if not family:
                continue
            key = (cid, family)
            prev = evidence.get(key) or {}
            events = int(mapping.get("events") or 0)
            label = mapping.get("label") or ""
            error = mapping.get("error") or ""
            http_status = mapping.get("http_status")
            if events > prev.get("events", 0):
                evidence[key] = {
                    "events": events,
                    "label": label,
                    "error": error,
                    "http_status": http_status,
                    "capability": mapping.get("capability"),
                }
            elif key not in evidence:
                evidence[key] = {
                    "events": events,
                    "label": label,
                    "error": error,
                    "http_status": http_status,
                    "capability": mapping.get("capability"),
                }
    return evidence


def _status_for(competition_id: str, family: str, mapping: Dict[str, Any], evidence: Dict[Tuple[str, str], Dict[str, Any]], proof: Dict[Tuple[str, str], Dict[str, Any]]) -> Tuple[str, str]:
    proof_row = proof.get((competition_id, family)) or {}
    proof_status = proof_row.get("status") or ""
    if proof_status == "WORKING" and not _strict_working_sample(proof_row.get("sample") or "", competition_id=competition_id):
        proof_status = "EMPTY_ARCHIVE"
        proof_row = dict(proof_row)
        proof_row["reason"] = "latest proof sample failed canonical quality"
    if proof_status == "RESTRICTED":
        return "RESTRICTED", proof_row.get("reason") or KNOWN_RESTRICTED.get(family) or "restricted"
    if proof_status == "EMPTY_ARCHIVE":
        return "EMPTY_ARCHIVE", proof_row.get("reason") or "fixtures/results path checked; no extractable events"
    if mapping.get("coverage") == "partial" or family in KNOWN_PARTIAL:
        notes = KNOWN_PARTIAL.get(family) or mapping.get("coverage_notes") or "partial coverage"
        return "PARTIAL_WORKING", notes
    rail = FAMILY_EVIDENCE.get(family) or {}
    if rail.get("railway_access") and family not in KNOWN_RESTRICTED:
        return "WORKING", rail.get("transport") or "Railway-proven public transport"
    if family in KNOWN_RESTRICTED:
        return "RESTRICTED", KNOWN_RESTRICTED[family]
    row = evidence.get((competition_id, family)) or {}
    events = int(row.get("events") or 0)
    label = (row.get("label") or "").upper()
    error = (row.get("error") or "").lower()
    http_status = row.get("http_status")
    if proof_status == "WORKING" and int(proof_row.get("events") or 0) > 0:
        return "WORKING", proof_row.get("reason") or "canonical events from mapped public path"
    if events > 0 or (proof_status != "EMPTY_ARCHIVE" and proven_status(competition_id, family) == "WORKING"):
        if "certificate" in error or "ssl" in error:
            return "WORKING", "capability proven; current health NETWORK_UNAVAILABLE"
        if label == "RATE_LIMITED":
            return "WORKING", "capability proven; current health RATE_LIMITED"
        if "timeout" in error or "getaddrinfo" in error or "dns" in error:
            return "WORKING", "capability proven; current health NETWORK_TEMPORARY"
        return "WORKING", "canonical events produced from upstream"
    if proof_status == "RESTRICTED":
        return "RESTRICTED", proof_row.get("reason") or "restricted"
    if proof_status == "SOURCE_CHANGED":
        return "SOURCE_CHANGED", proof_row.get("reason") or "source URL no longer serves data"
    if proof_status == "NETWORK_UNAVAILABLE":
        return "NETWORK_UNAVAILABLE", proof_row.get("reason") or KNOWN_NETWORK.get(family, "network/tls failure")
    if proof_status == "EMPTY_ARCHIVE":
        return "EMPTY_ARCHIVE", proof_row.get("reason") or "fixtures/results path checked; no extractable events"
    if family in KNOWN_NETWORK:
        return "NETWORK_UNAVAILABLE", KNOWN_NETWORK[family]
    if family in KNOWN_SOURCE_CHANGED:
        return "SOURCE_CHANGED", KNOWN_SOURCE_CHANGED[family]
    if http_status in {401, 403} or "403" in error:
        return "RESTRICTED", error or f"http {http_status}"
    if "certificate" in error or "ssl" in error:
        return "NETWORK_UNAVAILABLE", error
    if http_status == 429 or label == "RATE_LIMITED":
        return "RATE_LIMITED", error or "http 429"
    if "timeout" in error or "getaddrinfo" in error or "timed out" in error:
        return "NETWORK_UNAVAILABLE", error
    if http_status in {404, 410} or label == "SOURCE_CHANGED":
        return "SOURCE_CHANGED", error or "source URL no longer serves data"
    if label in {"NO_CURRENT_EVENTS"} or row.get("capability") == "PARTIAL_OPERATIONAL":
        return "EMPTY_ARCHIVE", "fixtures/results path reachable; no extractable canonical events after archive/schedule check"
    if not row:
        return "UNAVAILABLE", "no proven canonical events for this mapped family"
    return "UNAVAILABLE", error or label or "no canonical events"


_STATUS_RANK = {
    "WORKING": 0,
    "PARTIAL_WORKING": 1,
    "EMPTY_ARCHIVE": 4,
    "SOURCE_CHANGED": 5,
    "RESTRICTED": 6,
    "NETWORK_UNAVAILABLE": 7,
    "UNAVAILABLE": 8,
}


def rank_families(families: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Effective A/B/C: WORKING providers occupy slots before empty/403/TLS rows."""
    return sorted(
        families,
        key=lambda row: (
            _STATUS_RANK.get(row.get("status") or "", 9),
            int(row.get("priority") or 100),
            row.get("family") or "",
        ),
    )


def _bucket(a_status: str, b_status: Optional[str], two: bool) -> str:
    working = {"WORKING"}
    partial = {"PARTIAL_WORKING"}
    if not two:
        if a_status in working:
            return "ONLY ONE SOURCE EXISTS"
        return "BOTH UNAVAILABLE"
    assert b_status is not None
    if a_status in working and b_status in working:
        return "A+B WORKING"
    if (a_status in working and b_status in partial) or (b_status in working and a_status in partial):
        return "A+B PARTIAL"
    statuses = {a_status, b_status}
    if working & statuses:
        other = b_status if a_status in working else a_status
        if other == "RESTRICTED":
            return "ONE WORKING + RESTRICTED"
        if other == "SOURCE_CHANGED":
            return "ONE WORKING + SOURCE_CHANGED"
        if other in {"NETWORK_UNAVAILABLE", "NETWORK_TEMPORARY", "UNAVAILABLE", "RATE_LIMITED"}:
            return "ONE WORKING + NETWORK_UNAVAILABLE"
        if other == "EMPTY_ARCHIVE":
            return "ONE WORKING + EMPTY_ARCHIVE"
        if other in partial:
            return "A+B PARTIAL"
        return "ONE WORKING + NETWORK_UNAVAILABLE"
    if partial & statuses:
        return "A+B PARTIAL"
    return "BOTH UNAVAILABLE"


def build_matrix() -> Dict[str, Any]:
    by_comp = _enabled_mappings()
    allowed = _canonical_competition_ids()
    evidence = _family_evidence()
    proof = _load_proof()
    discovery_known = {}
    for row in COVERAGE:
        discovery_known.setdefault(row["competition"], []).append(row)
    competitions = []
    buckets = Counter()
    exceptions = []
    for competition_id, mappings in sorted(by_comp.items()):
        if allowed and competition_id not in allowed:
            continue
        families = []
        seen = set()
        for mapping in mappings:
            family = mapping.get("source_family")
            if not family or family in seen:
                continue
            seen.add(family)
            status, reason = _status_for(competition_id, family, mapping, evidence, proof)
            families.append(
                {
                    "family": family,
                    "adapter": mapping.get("adapter_key"),
                    "url": (mapping.get("source_config") or {}).get("url"),
                    "access": mapping.get("source_type"),
                    "priority": mapping.get("priority"),
                    "independence": mapping.get("independence_status"),
                    "coverage": mapping.get("coverage"),
                    "status": status,
                    "reason": reason,
                }
            )
        families = rank_families(families)
        sport = (discovery_known.get(competition_id) or [{}])[0].get("sport")
        a = families[0] if families else None
        b = families[1] if len(families) > 1 else None
        bucket = _bucket(a["status"] if a else "UNAVAILABLE", b["status"] if b else None, b is not None)
        if len(families) < 2:
            bucket = "ONLY ONE SOURCE EXISTS"
        buckets[bucket] += 1
        extra_c = families[2:]
        proof_a = proof.get((competition_id, (a or {}).get("family") or "")) or {}
        proof_b = proof.get((competition_id, (b or {}).get("family") or "")) or {}
        record = {
            "competition": competition_id,
            "sport": sport,
            "primary": a,
            "fallback": b,
            "optional_additional": extra_c,
            "provider_a": a,
            "provider_b": b,
            "provider_c": extra_c[0] if extra_c else None,
            "provider_family": [row["family"] for row in families],
            "scope": (a or {}).get("coverage") or "full",
            "full_or_partial": "full"
            if bucket == "A+B WORKING"
            else ("partial" if "PARTIAL" in bucket else "not-full"),
            "verification_event": proof_a.get("sample") or proof_b.get("sample"),
            "verification_date": proof_a.get("verified_at") or proof_b.get("verified_at"),
            "method": "family-cached proof ledger + smoke evidence",
            "last_success": proof_a.get("verified_at") or proof_a.get("reason"),
            "health": {
                "a": (a or {}).get("status"),
                "b": (b or {}).get("status") if b else None,
            },
            "independence": {
                "a": (a or {}).get("independence"),
                "b": (b or {}).get("independence") if b else None,
            },
            "free_source_status": "free-$0",
            "bucket": bucket,
        }
        annotate_record(record, families)
        competitions.append(record)
        if bucket != "A+B WORKING":
            known = False
            for row in discovery_known.get(competition_id) or []:
                family = row.get("upstream_family")
                if family in KNOWN_RESTRICTED or family in KNOWN_PARTIAL or family in KNOWN_SOURCE_CHANGED:
                    known = True
                probe = (row.get("probe") or "").lower()
                if "403" in probe or "restricted" in probe or "timeout" in probe or "partial" in probe:
                    known = True
            exceptions.append(
                {
                    "competition": competition_id,
                    "provider_a": (a or {}).get("family"),
                    "a_status": (a or {}).get("status"),
                    "provider_b": (b or {}).get("family"),
                    "b_status": (b or {}).get("status"),
                    "reason": "; ".join(
                        item
                        for item in (
                            (a or {}).get("reason"),
                            (b or {}).get("reason") if b else "no second enabled family",
                        )
                        if item
                    ),
                    "already_known_from_discovery": known,
                    "bucket": bucket,
                }
            )
    cap_counts = Counter(row.get("capability") or "UNKNOWN" for row in competitions)
    live_capable = sum(1 for row in competitions if row.get("capability") in {"LIVE", "STRUCTURALLY_LIVE"})
    redundant = sum(1 for row in competitions if row.get("redundant_live_paths"))
    return {
        "total_competitions": len(competitions),
        "buckets": dict(buckets),
        "capability_totals": dict(cap_counts),
        "live_capable_count": live_capable,
        "redundant_live_count": redundant,
        "rapid_result_count": int(cap_counts.get("RAPID_RESULT") or 0),
        "exceptions": exceptions,
        "competitions": competitions,
    }


def write_matrix(path: Optional[Path] = None) -> Dict[str, Any]:
    matrix = build_matrix()
    out = path or (ROOT / "source_matrix_final.json")
    out.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    return matrix
