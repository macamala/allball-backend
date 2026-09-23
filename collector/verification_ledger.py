"""Live coverage ledger.

production_verified in audit/rich_production_overlay.json is a legacy manual
flag. It is not incremented when a collector writes a canonical event, which
is why GRI, World Athletics, WEC and WST stayed outside the old 38.

This module recomputes status from registry rows plus persisted evidence.
A parser test is not evidence. Evidence is a canonical event that was stored
and returned by the production-shaped API, or a standings snapshot row.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from collector.matrix_guard import MATRIX_PATH
from collector.source_family_closeout import (
    REGISTRY_MIGRATIONS,
    TERMS_BLOCKED,
    provider_independence,
)

ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = ROOT / "audit" / "rich_production_overlay.json"

MODEL_SCOPE_KEYS = {"national-and-club", "tier1", "futsalplanet-leagues-cups", "title-fights"}
TERMS_COMPETITIONS = {
    "usa-usta-meetings": "PERMISSION_REQUIRED",
    "owcs-historical": "RESTRICTED",
    "vct": "PERMISSION_REQUIRED",
    "worlds-msi-regional": "PERMISSION_REQUIRED",
    "rlcs": "PERMISSION_REQUIRED",
    "korean-golf-tour": "TERMS_REVIEW_REQUIRED",
    "tier1": "RESTRICTED",
    "atp-tour": "PERMISSION_REQUIRED",
}
ATP_PERMISSION_DETAIL = (
    "Official ATP result pages reject automated collection (403/429). "
    "ATP's public copyright notice restricts reproduction without written permission. "
    "The existing SportScore tennis feed requires a visible 'Powered by SportScore' credit, "
    "and NinkoSports does not render provider branding, so the free SportScore tier is not approved."
)
SAME_ORIGIN_COMPETITIONS = {
    "nordic-water-polo-league",
    "nsw-hrnsw-meetings",
    "ireland-gri-meetings",
}
A_ONLY_COMPETITIONS = {"ireland-gri-meetings", "biathlon"}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def legacy_overlay_counts() -> Dict[str, int]:
    overlay = _load_json(OVERLAY_PATH)
    if not isinstance(overlay, dict):
        return {"production_verified": 0, "standings_proven": 0}
    verified = 0
    standings = 0
    for row in overlay.values():
        if not isinstance(row, dict):
            continue
        if row.get("production_verified") is True:
            verified += 1
        if row.get("standings") == "PROVEN":
            standings += 1
    return {"production_verified": verified, "standings_proven": standings}


def _family(block: Optional[Dict[str, Any]]) -> str:
    if not isinstance(block, dict):
        return ""
    return str(block.get("family") or "")


def _stored_coverage(event: Dict[str, Any]) -> str:
    detail = event.get("sport_detail") if isinstance(event.get("sport_detail"), dict) else {}
    coverage = str(event.get("coverage") or event.get("coverage_kind") or detail.get("coverage") or "").lower()
    if "top_10" in coverage or "official_summary" in coverage:
        return coverage
    home = event.get("home") if isinstance(event.get("home"), dict) else {}
    away = event.get("away") if isinstance(event.get("away"), dict) else {}
    label = f"{home.get('name') or ''} {away.get('name') or ''}".lower()
    rows = event.get("classification") or []
    if "official prologue" in label and isinstance(rows, list) and rows:
        if all(isinstance(row, dict) and row.get("time_kind") for row in rows[:5]):
            return "official_top_10_summary"
    return coverage


def _classification_status(event: Optional[Dict[str, Any]]) -> str:
    if not event:
        return "NONE"
    coverage = _stored_coverage(event)
    rows = event.get("classification") or []
    if not isinstance(rows, list):
        rows = []
    if "top_10" in coverage or "official_summary" in coverage or coverage == "official_top_10_summary":
        return "OFFICIAL_SUMMARY"
    if len(rows) >= 3 and coverage in {"full", "official_result", "official_match", ""}:
        if coverage == "official_match" and not rows:
            return "FINAL_SCORE_ONLY"
        if rows:
            return "FULL" if coverage in {"full", "official_result", ""} else "PARTIAL"
    if event.get("home_score") is not None or (event.get("score") or {}).get("home") is not None:
        return "FINAL_SCORE_ONLY" if not rows else "PARTIAL"
    if rows:
        return "PARTIAL"
    return "NONE"


def _event_status(event: Optional[Dict[str, Any]], *, applicable: bool = True) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if not event or not event.get("id"):
        return "UNPROVEN"
    if event.get("partial"):
        return "PARTIAL"
    return "PROVEN"


def _standings_status(rows: Optional[List[Dict[str, Any]]], *, applicable: bool) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if not rows:
        return "NONE"
    if len(rows) >= 2:
        return "PROVEN"
    return "PARTIAL"


def _terms(competition: str, family_a: str, family_b: str) -> str:
    if competition in TERMS_COMPETITIONS:
        return TERMS_COMPETITIONS[competition]
    if family_a in TERMS_BLOCKED:
        if "TERMS_REVIEW" in TERMS_BLOCKED[family_a]:
            return "TERMS_REVIEW_REQUIRED"
        return "RESTRICTED"
    return "CLEAR"


def _blocker(row: Dict[str, Any]) -> str:
    if row["competition_key"] in MODEL_SCOPE_KEYS and row["production_event_status"] != "PROVEN":
        return "MODEL_SCOPE"
    if row["terms_status"] in {"TERMS_REVIEW_REQUIRED", "PERMISSION_REQUIRED", "RESTRICTED"} and row["production_event_status"] != "PROVEN":
        return "TERMS" if row["terms_status"] != "PERMISSION_REQUIRED" else "PERMISSION"
    if row["production_event_status"] == "PROVEN":
        if row["provider_independence"] == "A_ONLY":
            return "NO_SECOND_SOURCE"
        if row["provider_independence"] == "SAME_ORIGIN":
            return "SAME_ORIGIN"
        return "NONE"
    if row["provider_independence"] == "SAME_ORIGIN":
        return "SAME_ORIGIN"
    return "TECHNICAL_FETCH"


def recompute_ledger(
    evidence: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    matrix_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Recompute every registry competition from evidence.

    evidence maps competition_key -> {
      event: public event dict or None,
      standings: list or None,
      standings_applicable: bool,
    }
    Missing evidence is UNPROVEN. Nothing here reads production_verified.
    """
    matrix = json.loads((matrix_path or MATRIX_PATH).read_text(encoding="utf-8"))
    competitions = matrix.get("competitions") or []
    proof = evidence or {}
    rows = []
    for comp in competitions:
        key = str(comp.get("competition") or "")
        family_a = _family(comp.get("provider_a") or comp.get("primary"))
        family_b = _family(comp.get("provider_b") or comp.get("fallback"))
        if key in SAME_ORIGIN_COMPETITIONS:
            independence = "SAME_ORIGIN" if key != "ireland-gri-meetings" else "A_ONLY"
        elif key in A_ONLY_COMPETITIONS or not family_b:
            independence = "A_ONLY"
        else:
            independence = provider_independence(family_a, family_b)
        item = proof.get(key) or {}
        event = item.get("event")
        summary_events = item.get("summary_events") if isinstance(item.get("summary_events"), list) else None
        standings_rows = item.get("standings") or []
        applicable = bool(item.get("standings_applicable", True))
        if key in {"bha-meetings", "gbgb-meetings", "ireland-gri-meetings"} and not standings_rows:
            applicable = bool(item.get("standings_applicable", False))
        built = {
            "competition_key": key,
            "sport": comp.get("sport") or "",
            "competition_name": ((comp.get("primary") or {}).get("reason") or key),
            "primary_source_family": family_a,
            "secondary_source_family": family_b,
            "upstream_origin_a": family_a,
            "upstream_origin_b": family_b,
            "provider_A_status": "WORKING" if event else "UNPROVEN",
            "provider_B_status": "UNPROVEN" if independence != "A_B_INDEPENDENT" else ("WORKING" if item.get("provider_b_event") else "UNPROVEN"),
            "provider_independence": independence,
            "terms_status": _terms(key, family_a, family_b),
            "production_event_status": _event_status(event),
            "classification_status": _classification_status(event),
            "official_summary_event_count": (
                sum(1 for summary in summary_events if _classification_status(summary) == "OFFICIAL_SUMMARY")
                if summary_events is not None
                else (1 if _classification_status(event) == "OFFICIAL_SUMMARY" else 0)
            ),
            "standings_status": _standings_status(standings_rows, applicable=applicable),
            "coverage_kind": _stored_coverage(event) if event else "",
            "last_success_at": (event or {}).get("updated_at"),
            "canonical_proof_event_id": (event or {}).get("id"),
            "upstream_proof_identity": (event or {}).get("source_event_id") or (event or {}).get("meeting_id"),
            "classification_row_count": len((event or {}).get("classification") or []),
            "standings_row_count": len(standings_rows),
            "proof_source_path": item.get("proof_source_path") or "",
            "payload_hash": item.get("payload_hash"),
            "proof_retrieved_at": item.get("proof_retrieved_at"),
        }
        built["blocker_code"] = _blocker(built)
        migration = next((row for row in REGISTRY_MIGRATIONS if row.get("old_key") == key), None)
        built["blocker_detail"] = item.get("blocker_detail") or (
            (migration or {}).get("migration_reason") if built["blocker_code"] == "MODEL_SCOPE" else ""
        ) or (ATP_PERMISSION_DETAIL if key == "atp-tour" and built["blocker_code"] == "PERMISSION" else "")
        rows.append(built)
    totals = summarize(rows)
    legacy = legacy_overlay_counts()
    return {
        "competition_count": len(rows),
        "legacy": legacy,
        "totals": totals,
        "migrations": REGISTRY_MIGRATIONS,
        "rows": rows,
        "legacy_differences": _legacy_differences(rows, _load_json(OVERLAY_PATH)),
    }


def summarize(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    rows = list(rows)
    families = {
        row["primary_source_family"]
        for row in rows
        if row["production_event_status"] == "PROVEN" and row["primary_source_family"]
    }
    return {
        "production_proven_competitions": sum(row["production_event_status"] == "PROVEN" for row in rows),
        "production_proven_source_families": len(families),
        "classification_full": sum(row["classification_status"] == "FULL" for row in rows),
        "classification_official_summary": sum(int(row.get("official_summary_event_count") or 0) for row in rows),
        "standings_proven": sum(row["standings_status"] == "PROVEN" for row in rows),
        "A_B_independent": sum(
            row["provider_independence"] == "A_B_INDEPENDENT"
            and row["production_event_status"] == "PROVEN"
            and row["terms_status"] == "CLEAR"
            for row in rows
        ),
        "A_only": sum(row["provider_independence"] == "A_ONLY" for row in rows),
        "same_origin": sum(row["provider_independence"] == "SAME_ORIGIN" for row in rows),
        "terms_or_permission_blocked": sum(
            row["terms_status"] in {"TERMS_REVIEW_REQUIRED", "PERMISSION_REQUIRED", "RESTRICTED"} for row in rows
        ),
        "technical_blocked": sum(row["blocker_code"] == "TECHNICAL_FETCH" for row in rows),
        "model_scope_blocked": sum(row["blocker_code"] == "MODEL_SCOPE" for row in rows),
    }


def _legacy_differences(rows: List[Dict[str, Any]], overlay: Any) -> List[Dict[str, Any]]:
    if not isinstance(overlay, dict):
        return []
    out = []
    by_key = {row["competition_key"]: row for row in rows}
    for key, old in overlay.items():
        if not isinstance(old, dict) or not old.get("production_verified"):
            continue
        current = by_key.get(key)
        new_status = (current or {}).get("production_event_status") or "UNPROVEN"
        if new_status != "PROVEN":
            out.append(
                {
                    "competition": key,
                    "old_status": "production_verified",
                    "new_status": new_status,
                    "reason": "Legacy overlay flag has no persisted canonical event in the evidence set.",
                    "proof_canonical_id": None,
                }
            )
    proven_now = {row["competition_key"] for row in rows if row["production_event_status"] == "PROVEN"}
    flagged = {key for key, old in overlay.items() if isinstance(old, dict) and old.get("production_verified")}
    for key in sorted(proven_now - flagged):
        row = by_key[key]
        out.append(
            {
                "competition": key,
                "old_status": "not_in_legacy_overlay",
                "new_status": "PROVEN",
                "reason": "Persisted canonical event exists. The legacy overlay was not rewritten when this collector landed.",
                "proof_canonical_id": row.get("canonical_proof_event_id"),
            }
        )
    return out


def counters_are_derived(totals: Dict[str, int], rows: List[Dict[str, Any]]) -> bool:
    """Guard against a hand-edited headline number."""
    return totals == summarize(rows) and totals["production_proven_competitions"] == sum(
        row["production_event_status"] == "PROVEN" for row in rows
    )
