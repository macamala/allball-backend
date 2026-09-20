"""Public duplicate-fixture audit. Read-only over already collected events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from collector.participant_alias import contextual_pair_match, names_equivalent


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _side(event: Dict[str, Any], key: str) -> str:
    blob = event.get(key) or {}
    if isinstance(blob, dict):
        return str(blob.get("display_name") or blob.get("name") or "")
    return str(blob or "")


def audit_duplicates(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [event for event in events if event]
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for event in rows:
        groups[(str(event.get("sport") or ""), str(event.get("competition_key") or event.get("competition") or ""))].append(
            event
        )
    exact = []
    probable = []
    ambiguous = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                ok, reason = contextual_pair_match(left, right)
                lh, la = _side(left, "home"), _side(left, "away")
                rh, ra = _side(right, "home"), _side(right, "away")
                names = names_equivalent(lh, rh) and names_equivalent(la, ra)
                swapped = names_equivalent(lh, ra) and names_equivalent(la, rh)
                t0, t1 = _ts(left.get("start_time")), _ts(right.get("start_time"))
                delta = abs((t0 - t1).total_seconds()) if t0 and t1 else None
                pair = {
                    "left": left.get("id") or left.get("event_id"),
                    "right": right.get("id") or right.get("event_id"),
                    "home": [lh, rh],
                    "away": [la, ra],
                    "reason": reason,
                    "kickoff_delta_seconds": delta,
                    "swapped": bool(swapped and not names),
                }
                if ok and names:
                    exact.append(pair)
                elif ok:
                    probable.append(pair)
                elif (names or swapped) and reason in {"kickoff", "round"}:
                    ambiguous.append(pair)
                elif names or swapped:
                    ambiguous.append(pair)
    return {
        "inspected": len(rows),
        "exact_duplicates": exact,
        "probable_duplicates": probable,
        "ambiguous_pairs": ambiguous,
        "exact_count": len(exact),
        "probable_count": len(probable),
        "ambiguous_count": len(ambiguous),
    }
