"""Plan bounded changed-result work from an already fetched football board.

Scheduling only: all writes still pass through consume_board_match. The ordered
coverage cursor is independent; an early result never acknowledges unseen IDs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from typing import Any

from collector.adapters_fotmob import match_to_event
from collector.keeper_revalidation import _same_pair
from collector.live_state import canonical_status
from collector.maintenance_policy import automatic_promotion_blocked
from collector.util import load_json, parse_datetime, isoformat

MAX_PRIORITY_EVENTS = 8
MAX_PRIORITY_RECEIPTS = 128
PRIORITY_RETRY_SECONDS = 300
PLAYED = frozenset({'live', 'halftime', 'break', 'finished', 'walkover', 'awarded'})


def _score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        text = str(value)
        return int(text) if text.isdigit() and 0 <= int(text) <= 99 else None
    except (TypeError, ValueError):
        return None


def changed_result_signature(raw: dict, rows: list, now: datetime) -> str | None:
    """Fresh played evidence and exact existing pair/time, never kickoff inference."""
    event = match_to_event(raw, '')
    if not event:
        return None
    fetched = parse_datetime(event.get('source_fetch_time'))
    kickoff = parse_datetime(event.get('start_time'))
    status = canonical_status(event.get('status'))
    supplied = tuple(_score((event.get('score') or {}).get(s)) for s in ('home', 'away'))
    if (not fetched or not kickoff or not -30 <= (now-fetched).total_seconds() <= 300
            or kickoff > now or status not in PLAYED or None in supplied):
        return None
    candidates = []
    differs = False
    clock_changes = []
    for row in rows:
        if (row.sport_id != 'football' or automatic_promotion_blocked(row)
                or not row.start_time or abs((row.start_time-kickoff).total_seconds()) > 180
                or not _same_pair(row, event)):
            continue
        actual = tuple(_score((load_json(row.score_json, {}) or {}).get(s)) for s in ('home', 'away'))
        stored_status = canonical_status(row.status)
        hidden = row.display_eligible is False or any(
            (load_json(getattr(row, key, None), {}) or {}).get('display_eligible') is False
            for key in ('extra_json', 'list_extra_json'))
        candidates.append((row.event_id, row.competition_id, stored_status, actual, hidden))
        # A matching hidden source result may still leave an older public row
        # blank. Schedule validation; the root planner, not this queue, decides
        # whether exact public identity/visibility recovery is permitted.
        differs |= stored_status != status or actual != supplied or hidden
        minute = (event.get('score') or {}).get('minute')
        old_minute = (load_json(row.score_json, {}) or {}).get('minute')
        clock = (event.get('score') or {}).get('clock')
        old_clock = (load_json(row.score_json, {}) or {}).get('clock')
        if (not hidden and stored_status == status == 'live' and actual == supplied
                and ((minute not in (None, '') and str(minute) != str(old_minute))
                     or (clock not in (None, '') and str(clock) != str(old_clock)))):
            clock_changes.append((row.event_id, str(old_minute), str(minute), str(old_clock), str(clock)))
    if not candidates or not (differs or clock_changes):
        return None
    # Do not include fetch time: a new HTTP contact with identical evidence must
    # not bypass the conflict cooldown. A changed score/physical row may retry.
    proof = {'id': str(raw.get('id') or raw.get('matchId')), 'status': status,
             'score': supplied, 'kickoff': kickoff.isoformat(),
             'league': raw.get('_league'), 'existing': sorted(candidates)}
    if not differs:
        proof['clock_changes'] = clock_changes
    return hashlib.sha256(json.dumps(proof, sort_keys=True, default=str).encode()).hexdigest()


def priority_plan(matches: dict, index: dict, receipts: dict, now: datetime, max_events: int) -> dict[str, str]:
    cap = min(MAX_PRIORITY_EVENTS, max(0, max_events // 2))
    if not cap:
        return {}
    choices = []
    for sid, raw in matches.items():
        signature = changed_result_signature(raw, index.get(sid, []), now)
        if not signature:
            continue
        old = receipts.get(sid) or {}
        due = parse_datetime(old.get('next_due_at'))
        if signature == old.get('signature') and due and due > now:
            continue
        last = parse_datetime(old.get('attempted_at')) or datetime.min
        choices.append((last, sid, signature))
    # Least-recently attempted first, deterministic after restart.
    return {sid: signature for _, sid, signature in sorted(choices)[:cap]}


def interleave_priority(base: list[tuple], matches: dict, priorities: dict) -> list[tuple]:
    """One coverage observation before each priority slot; keep all cursor items."""
    early = [(sid, matches[sid], True) for sid in priorities]
    ordered = []
    for pos, (sid, raw) in enumerate(base):
        ordered.append((sid, raw, False))
        if pos < len(early):
            ordered.append(early[pos])
    ordered.extend(early[len(base):])
    return ordered


def record_priority_attempt(receipts: dict, sid: str, signature: str, now: datetime) -> None:
    receipts[sid] = {'signature': signature, 'attempted_at': isoformat(now),
                     'next_due_at': isoformat(now+timedelta(seconds=PRIORITY_RETRY_SECONDS))}
    if len(receipts) > MAX_PRIORITY_RECEIPTS:
        oldest = sorted(receipts, key=lambda key: (receipts[key].get('attempted_at', ''), key))
        for key in oldest[:len(receipts)-MAX_PRIORITY_RECEIPTS]:
            del receipts[key]


def conflict_evidence(roots: dict, event: dict) -> dict:
    """Bounded internal diagnostics, never source credentials or a write override."""
    kickoff = parse_datetime(event.get('start_time'))
    out = []
    for row in sorted(roots.values(), key=lambda row: row.event_id)[:4]:
        meta = load_json(row.extra_json, {}) or {}
        out.append({'id': row.event_id, 'competition': row.competition_id,
                    'status': row.status, 'visible': row.display_eligible,
                    'policy_blocked': automatic_promotion_blocked(row),
                    'same_pair': _same_pair(row, event),
                    'kickoff_delta_s': (row.start_time-kickoff).total_seconds() if row.start_time and kickoff else None,
                    'season': row.season, 'stage': row.stage,
                    'canonical_event_id': row.canonical_event_id,
                    'source_ids': meta.get('source_event_ids'),
                    'source_competition_id': meta.get('source_competition_id'),
                    'collapsed_count': len(meta.get('collapsed_from') or []),
                    'quality_flags': meta.get('quality_flags'),
                    'quarantine_disposition': meta.get('quarantine_disposition'),
                    'source_group_id': meta.get('source_group_id'),
                    'metadata_family': meta.get('source_family')})
    return {'root_count': len(roots), 'roots': out,
            'incoming_competition': event.get('source_competition_context'),
            'source_group_id': event.get('source_group_id')}
