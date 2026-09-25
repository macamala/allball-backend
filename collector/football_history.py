"""Verified native historical facts, never a source of current fixture writes.

Keep provider match references private and only attach an app link after the
stored public identity is proved. A historical record is not a new live event.
"""
from copy import deepcopy
from datetime import datetime
import re
from sqlalchemy import or_, func
from collector.util import parse_datetime, isoformat, load_json
from collector.source_ids import id_for_family
from collector.participant_alias import punctuation_identity_key

REVISION = 1
MAX_HISTORY = 120


def _id(value):
    text = str(value or '')
    return text if re.fullmatch(r'\d{1,12}', text) else None


def _side(value):
    if not isinstance(value, dict) or not _id(value.get('id')) or not str(value.get('name') or '').strip():
        return None
    sid = _id(value['id'])
    return {'id': sid, 'name': str(value['name']).strip(),
            'logo': f'https://images.fotmob.com/image_resources/logo/teamlogo/{sid}.png'}


def _same(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    if str(a.get('id') or '') != str(b.get('id') or ''):
        return False
    return bool(a.get('name') and b.get('name')) and punctuation_identity_key(a['name']) == punctuation_identity_key(b['name'])


def _score(value):
    match = re.fullmatch(r'\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*', str(value or ''))
    return {'home': int(match[1]), 'away': int(match[2])} if match else None


def _reference(value):
    # The hash is the documented response's own match reference, not a URL to follow.
    match = re.fullmatch(r'/matches/[^#?\s]+#(\d{1,12})', str(value or ''))
    return match[1] if match else None


def _dedupe(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['_source_match_id'], []).append(row)
    accepted = []
    for items in grouped.values():
        first = items[0]
        if any(any(i.get(k) != first.get(k) for k in ('home', 'away', 'score', 'start_time')) for i in items[1:]):
            continue  # Do not select one of two contradictory historical records.
        accepted.append(first)
    return sorted(accepted, key=lambda r: (r['start_time'], r['_source_match_id']), reverse=True)[:MAX_HISTORY]


def parse_history(root):
    """Caller must prove root match ID, oriented names and kickoff before storage."""
    general = root.get('general') or {}
    current_id = _id(general.get('matchId'))
    home, away = _side(general.get('homeTeam')), _side(general.get('awayTeam'))
    kickoff = parse_datetime(general.get('matchTimeUTCDate'))
    if not current_id or not home or not away or home['id'] == away['id'] or not kickoff:
        return {}
    cutoff = min(kickoff, datetime.utcnow())
    content = root.get('content') or {}
    h2h = (content.get('h2h') or {}).get('matches') or []
    parsed = []
    for item in h2h[:300] if isinstance(h2h, list) else []:
        if not isinstance(item, dict):
            continue
        status = item.get('status') or {}
        mid = _reference(item.get('matchUrl')) or _id(item.get('id'))
        a, b = _side(item.get('home')), _side(item.get('away'))
        at = parse_datetime(status.get('utcTime') or (item.get('time') or {}).get('utcTime'))
        score = _score(status.get('scoreStr'))
        if (status.get('finished') is not True or status.get('cancelled') or status.get('awarded')
                or not mid or mid == current_id or not at or at >= cutoff or not a or not b or score is None):
            continue
        if not ((_same(a, home) and _same(b, away)) or (_same(a, away) and _same(b, home))):
            continue
        league = item.get('league') or {}
        parsed.append({'_source_match_id': mid, 'id': None, 'sport': 'football', 'home': a, 'away': b,
                       'start_time': isoformat(at), 'score': score, 'status': 'finished',
                       'competition': str(league.get('name') or ''),
                       'result_type': str((status.get('reason') or {}).get('short') or 'FT')})
    form = {}
    blocks = (content.get('matchFacts') or {}).get('teamForm') or []
    if isinstance(blocks, list) and len(blocks) == 2:
        for side_name, target, block in zip(('home', 'away'), (home, away), blocks):
            results = []
            for item in block[:30] if isinstance(block, list) else []:
                if not isinstance(item, dict):
                    continue
                mid = _reference(item.get('linkToMatch'))
                a, b = _side(item.get('home')), _side(item.get('away'))
                at = parse_datetime((item.get('date') or {}).get('utcTime'))
                score = _score(item.get('score'))
                if not mid or mid == current_id or not at or at >= cutoff or not a or not b or score is None:
                    continue
                if _same(a, target):
                    own, other = score['home'], score['away']
                elif _same(b, target):
                    own, other = score['away'], score['home']
                else:
                    continue
                outcome = 'W' if own > other else 'L' if own < other else 'D'
                # Explicit form outcome is additional evidence, not a licence to invent wins.
                if item.get('resultString') not in (None, outcome):
                    continue
                results.append({'_source_match_id': mid, 'id': None, 'sport': 'football',
                                'home': a, 'away': b, 'start_time': isoformat(at), 'score': score,
                                'status': 'finished', 'outcome': outcome})
            results = _dedupe(results)[:5]
            if results:
                form[side_name] = {'team': target, 'results': results,
                                   'summary': ' · '.join(r['outcome'] for r in results)}
    return {'revision': REVISION, 'match_id': current_id, 'home': home, 'away': away,
            'kickoff': isoformat(kickoff), 'h2h': _dedupe(parsed), 'form': form}


def known_native_rows(db, mids):
    """Find existing restrictions even in another competition or pre-observation rows.

    Queries are bounded batches over exact typed references, not name matching.
    The textual prefilter is followed by the existing typed-ID parser.
    """
    from collector.models import SportsEvent, SportsEventObservation
    mids = sorted({_id(mid) for mid in mids if _id(mid)})
    by_native, seen = {}, {}
    observed = []
    for offset in range(0, len(mids), 80):
        batch = mids[offset:offset+80]
        observations = db.query(SportsEventObservation.event_id, SportsEventObservation.source_event_id).filter(
            SportsEventObservation.source_family == 'fotmob', SportsEventObservation.source_event_id.in_(batch)).distinct().all()
        observed.extend(observations)
        ids = {eid for eid, _ in observations}
        compact = func.replace(SportsEvent.extra_json, ' ', '')
        clauses = [compact.like('%"fotmob":"'+mid+'"%') for mid in batch]
        candidates = db.query(SportsEvent).filter(SportsEvent.sport_id == 'football',
            or_(SportsEvent.event_id.in_(ids), *clauses)).limit(4001).all()
        if len(candidates) > 4000:
            raise ValueError('Native identity index exceeded its safe read bound')
        seen.update({r.event_id: r for r in candidates})
    for row in seen.values():
        mid = id_for_family(load_json(row.extra_json, {}) or {}, 'fotmob')
        if mid in mids:
            by_native.setdefault(mid, []).append(row)
    for eid, mid in observed:
        row = seen.get(eid)
        if row is not None and row not in by_native.get(mid, []):
            by_native.setdefault(mid, []).append(row)
    return by_native


def public_history(db, current, history):
    """Remove hidden/conflicting known references and link only a proved public row.

    Historical source-only records remain readable but never get fabricated app
    event IDs. This function makes no writes or network requests.
    """
    from collector.models import SportsEvent, SportsEventObservation
    from collector.provider import _row_public_source_allowed, _blocked_public_sources
    from collector.maintenance_policy import automatic_promotion_blocked
    if not isinstance(history, dict) or history.get('revision') != REVISION:
        return [], {}
    meta = load_json(current.extra_json, {}) or {}
    if id_for_family(meta, 'fotmob') != history.get('match_id'):
        return [], {}
    parts = load_json(current.participants_json, {}) or {}
    for side in ('home', 'away'):
        expected = parts.get(side) or {}
        actual = history.get(side) or {}
        if not expected.get('name') or punctuation_identity_key(expected['name']) != punctuation_identity_key(actual.get('name') or ''):
            return [], {}
    if parse_datetime(history.get('kickoff')) != current.start_time:
        return [], {}
    records = list(history.get('h2h') or [])
    for block in (history.get('form') or {}).values():
        records.extend(block.get('results') or [])
    mids = {r['_source_match_id'] for r in records if r.get('_source_match_id')}
    if not mids:
        return [], {}
    by_native = known_native_rows(db, mids)
    blocked, families = _blocked_public_sources(db)
    if 'fotmob' in families:
        return [], {}
    def clean(record):
        result = deepcopy(record)
        mid = result.pop('_source_match_id', '')
        result['id'] = None
        for row in by_native.get(mid, []):
            rich, slim = load_json(row.extra_json, {}) or {}, load_json(row.list_extra_json, {}) or {}
            if automatic_promotion_blocked(row) or not _row_public_source_allowed(row, blocked, families):
                return None
            if row.canonical_event_id:
                continue  # Never turn a hidden observation into a public match link.
            if row.display_eligible is False or rich.get('display_eligible') is False or slim.get('display_eligible') is False:
                return None
            p = load_json(row.participants_json, {}) or {}
            names_match = all(punctuation_identity_key((p.get(s) or {}).get('name') or '') ==
                              punctuation_identity_key((result.get(s) or {}).get('name') or '') for s in ('home', 'away'))
            stamp = parse_datetime(result.get('start_time'))
            if not names_match or not stamp or not row.start_time or abs((row.start_time-stamp).total_seconds()) > 60:
                return None
            local = load_json(row.score_json, {}) or {}
            if row.status in ('finished', 'complete', 'final', 'ft') and any(local.get(s) != result['score'].get(s) for s in ('home', 'away')):
                return None
            if row.status in ('finished', 'complete', 'final', 'ft'):
                result['id'] = row.event_id
        result['label'] = f"{result['home']['name']} {result['score']['home']}–{result['score']['away']} {result['away']['name']}"
        return result
    h2h = [r for item in history.get('h2h') or [] if (r := clean(item)) is not None]
    form = {}
    for side, block in (history.get('form') or {}).items():
        results = [r for item in block.get('results') or [] if (r := clean(item)) is not None]
        if results:
            form[side] = {**block, 'results': results, 'summary': ' · '.join(r['outcome'] for r in results)}
    return h2h, form
