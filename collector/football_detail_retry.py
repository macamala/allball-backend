"""Bounded post-match repair policy; never a score or fixture authority.

A final score does not imply that the upstream statistics/lineups are final.
Recent finals are checked again for late-arriving detail. Older partial detail
is retried on demand without treating an unavailable section as invented data.
"""
from datetime import datetime, timezone

RECOVERY_HOURS = 72
FINAL_REFRESH_SECONDS = 300
LATE_FINAL_REFRESH_SECONDS = 900
FAILED_REFRESH_SECONDS = 120
HISTORICAL_PARTIAL_SECONDS = 3600
STATE_KEY = '_football_detail_sync'
STATE_REVISION = 1
FINISHED_STATUSES = frozenset({'finished', 'complete'})


def utc_naive(value):
    """Parse only explicit timestamps; use naive UTC consistently with storage."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def capped_ttl(extra, status, start_time, *, now, default):
    """Shorten only football FINAL detail TTLs, not live score polling.

    The recovery window is measured from kickoff (a verified stored timestamp),
    not an invented finish time. All recent finals get reconciliation even when
    the first response included some detail. Transport failures have a separate
    bounded negative interval; collector.http still owns its host backoff.
    """
    if str(status or '').lower() not in FINISHED_STATUSES:
        return default
    kickoff, current = utc_naive(start_time), utc_naive(now)
    age_hours = (current-kickoff).total_seconds()/3600 if kickoff and current else None
    if age_hours is None or age_hours < 0:
        return min(default, LATE_FINAL_REFRESH_SECONDS)
    if age_hours <= RECOVERY_HOURS:
        if extra.get('detail_negative') or extra.get('detail_empty'):
            return min(default, FAILED_REFRESH_SECONDS)
        return min(default, FINAL_REFRESH_SECONDS if age_hours <= 24 else LATE_FINAL_REFRESH_SECONDS)
    state = extra.get(STATE_KEY)
    sections = state.get('sections') if isinstance(state, dict) else None
    if isinstance(sections, dict):
        partial = not all(sections.get(key) for key in ('incidents', 'statistics', 'home_starters', 'away_starters'))
    else:
        # Legacy marker: this means not yet obtained, never "unsupported forever".
        partial = bool(extra.get('lineups_absent'))
    return min(default, HISTORICAL_PARTIAL_SECONDS) if partial else default


def note_attempt(extra, record, *, errors=(), received=False, now=None):
    """Keep actual stored-section coverage and separate attempts from success.

    Absence is not proof that a source will never provide a section. The state
    stays internal and contains no URLs, exception messages or credentials.
    """
    from collector.canonical_detail import canonicalize_lineups, canonicalize_statistics, canonicalize_timeline
    from collector.util import load_json
    previous = extra.get(STATE_KEY)
    previous = previous if isinstance(previous, dict) else {}
    lineup = canonicalize_lineups(load_json(record.lineups_json)) if record else None
    lineup = lineup or {}
    sections = {
        'incidents': len(canonicalize_timeline(load_json(record.incidents_json))) if record else 0,
        'statistics': len(canonicalize_statistics(load_json(record.statistics_json))) if record else 0,
        'home_starters': len((lineup.get('home') or {}).get('start') or []),
        'away_starters': len((lineup.get('away') or {}).get('start') or []),
    }
    now = utc_naive(now or datetime.utcnow())
    state = {
        'revision': STATE_REVISION,
        'last_attempt_at': now.isoformat(),
        'sections': sections,
        'outcome': 'received' if received else 'retry_pending',
    }
    success = now.isoformat() if received else previous.get('last_success_at')
    if success:
        state['last_success_at'] = success
    if errors:
        state['error_types'] = sorted(set(errors))[:8]
    extra[STATE_KEY] = state


def retain_final_lineup_sections(current, incoming):
    """Retain absent sections only; a nonempty corrected roster replaces its old one.

    Do not concatenate player lists: that would retain withdrawn starters or
    mix rosters. Explicit false flags remain meaningful. Inputs are never edited.
    """
    from copy import deepcopy
    if not isinstance(incoming, dict):
        return deepcopy(incoming)
    if not isinstance(current, dict):
        return deepcopy(incoming)
    def present(value):
        return value is not None and value != '' and value != [] and value != {}
    result = deepcopy(current)
    for key, value in incoming.items():
        if key in ('home', 'away') and isinstance(value, dict):
            existing = result.get(key)
            side = dict(existing) if isinstance(existing, dict) else {}
            side.update({k: deepcopy(v) for k, v in value.items() if present(v)})
            result[key] = side
        elif present(value):
            result[key] = deepcopy(value)
    return result
