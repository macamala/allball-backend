"""Lossless football detail fields from the already fetched native response.

No scoreboard, identity, visibility, or network scheduling writes live here.
"""
from datetime import datetime, timedelta
import math
from typing import Any

REVISION = 2


def number(value: Any):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def pitch_position(value):
    if not isinstance(value, dict):
        return None
    x, y = number(value.get('x')), number(value.get('y'))
    return {'x': x, 'y': y} if x is not None and y is not None and 0 <= x <= 1 and 0 <= y <= 1 else None


def clean_statistics(rows):
    """Section headings are not unknown statistics; repeated metrics appear once."""
    out, seen = [], set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not (row.get('label') or row.get('name')):
            continue
        if all(row.get(key) in (None, '') for key in ('home', 'away', 'value')):
            continue
        key = str(row.get('label') or row.get('name')).strip().casefold()
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def _name(value):
    if isinstance(value, dict):
        return value.get('name') or value.get('fullName')
    return value if isinstance(value, str) else None


def complete_fotmob_detail(root, out):
    content = root.get('content') if isinstance(root.get('content'), dict) else root
    general = root.get('general') or content.get('general') or {}
    facts = content.get('matchFacts') or {}
    block = facts.get('events') or {}
    rows = block.get('events') or block.get('list') or [] if isinstance(block, dict) else block
    timeline, period = [], '1'
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get('type') or item.get('eventType') or item.get('key') or 'event').lower()
        if kind == 'half':
            marker = str(item.get('halfStrShort') or item.get('halfStrKey') or '').lower()
            if marker in ('ht', 'halftime_short'):
                period = '2'
            elif marker in ('et', 'extra_time_short'):
                period = '3'
            continue
        if kind in ('addedtime', 'added time'):
            continue
        player = item.get('player') if isinstance(item.get('player'), dict) else {}
        swap = item.get('swap') if isinstance(item.get('swap'), list) else []
        pin = item.get('playerIn') or item.get('inPlayer') or (swap[0] if len(swap) > 0 else {})
        pout = item.get('playerOut') or item.get('outPlayer') or (swap[1] if len(swap) > 1 else {})
        card = str(item.get('card') or item.get('cardType') or '').lower()
        if card:
            kind = 'second_yellow' if 'second' in card or 'yellowred' in card.replace(' ', '') else f'{card} card'
        if kind in ('sub', 'subst'):
            kind = 'substitution'
        if kind == 'goal' and item.get('ownGoal') is True:
            kind = 'own_goal'
        if kind == 'goal' and (str(item.get('goalDescriptionKey') or '').lower() in ('penalty', 'penalty_goal') or item.get('isPenalty') is True):
            kind = 'penalty_goal'
        if item.get('isPenaltyShootoutEvent') is True:
            period = 'penalties'
        # FotMob homeScore/awayScore are PRE-event at goal time.
        score = item.get('newScore')
        if isinstance(score, list) and len(score) == 2 and all(number(x) is not None for x in score):
            after = {'home': score[0], 'away': score[1]}
        else:
            after = {'home': item.get('homeScore'), 'away': item.get('awayScore')} if item.get('homeScore') is not None or item.get('awayScore') is not None else None
        minute = item.get('time') if item.get('time') is not None else item.get('minute')
        explicit_period = item.get('period')
        if explicit_period in ('3', '4', 'ExtraFirstHalf', 'ExtraSecondHalf', 'penalties'):
            event_period = str(explicit_period)
        else:
            event_period = period if period != '1' or number(minute) is None or number(minute) <= 45 else '2'
        timeline.append({
            'id': item.get('eventId') or item.get('reactKey'), 'type': kind,
            'minute': minute, 'stoppage': item.get('overloadTime'), 'period': event_period,
            'player': _name(item.get('name') or player or item.get('playerObj')) or item.get('nameStr'),
            'player_id': item.get('playerId') or player.get('id'),
            'assist': _name(item.get('assist')) or item.get('assistStr'),
            'assist_id': (item.get('assist') or {}).get('id') if isinstance(item.get('assist'), dict) else None,
            'player_in': _name(pin) or (_name(item.get('name') or player) if kind == 'substitution' else None), 'player_out': _name(pout),
            'player_in_id': pin.get('id') if isinstance(pin, dict) else None,
            'player_out_id': pout.get('id') if isinstance(pout, dict) else None,
            'side': 'home' if item.get('isHome') is True else 'away' if item.get('isHome') is False else None,
            'score_after': after, 'description': item.get('varReason') or item.get('text') or item.get('str'),
        })
    if timeline:
        out['incidents'] = timeline
    if out.get('statistics'):
        out['statistics'] = clean_statistics(out['statistics'])
    detail = out.get('sport_detail') or {}
    if isinstance(detail.get('statistics_periods'), dict):
        detail['statistics_periods'] = {k: clean_statistics(v) for k, v in detail['statistics_periods'].items()}
    lineup = content.get('lineup') or content.get('lineups') or {}
    if isinstance(lineup, dict) and isinstance(out.get('lineups'), dict):
        for side in ('home', 'away'):
            source = lineup.get(side+'Team') or {}
            by_id = {str(p.get('id') or p.get('playerId')): p for p in (source.get('starters') or []) + (source.get('subs') or []) if isinstance(p, dict)}
            for key in ('start', 'bench'):
                for p in out['lineups'].get(side, {}).get(key, []):
                    original = by_id.get(str(p.get('id'))) or {}
                    position = pitch_position(original.get('verticalLayout'))
                    if position:
                        p['pitch_position'] = position
                    if original.get('id') and original.get('name'):
                        p['profile_ref'] = {'family':'fotmob', 'id':str(original['id'])}
                    if source.get('id') and source.get('name'):
                        p['team_at_match'] = {'id':str(source['id']), 'name':source['name']}
                    if number(original.get('age')) is not None:
                        p['age'] = original['age']
                    if original.get('countryCode'):
                        p['country_id'] = original['countryCode']
                    # Provider formation-slot IDs (e.g. 115) are not position names.
                    if isinstance(p.get('position'), (int, float)):
                        p['position_id'] = p.pop('position')
        if isinstance(lineup.get('confirmed'), bool):
            out['lineups']['confirmed'] = lineup['confirmed']
    home_id = str((general.get('homeTeam') or {}).get('id') or '')
    away_id = str((general.get('awayTeam') or {}).get('id') or '')
    raw_shots = (content.get('shotmap') or {}).get('shots') or []
    shots = []
    for shot in raw_shots if isinstance(raw_shots, list) else []:
        if not isinstance(shot, dict) or not shot.get('playerName'):
            continue
        team = str(shot.get('teamId') or '')
        shots.append({'id': shot.get('id'), 'player': shot['playerName'], 'player_id': shot.get('playerId'),
                      'side': 'home' if home_id and team == home_id else 'away' if away_id and team == away_id else None,
                      'minute': shot.get('min'), 'stoppage': shot.get('minAdded'), 'period': shot.get('period'),
                      'type': shot.get('eventType'), 'xg': number(shot.get('expectedGoals')),
                      'on_target': shot.get('isOnTarget') if isinstance(shot.get('isOnTarget'), bool) else None})
    if shots:
        detail['shots'] = shots
        detail['shots_total'] = len(shots)
        detail['shots_on_target'] = sum(1 for s in shots if s['on_target'] is True)
    if detail:
        out['sport_detail'] = detail
    # Zero is real, not an absent xG value.
    players = content.get('playerStats') or {}
    for player in out.get('player_statistics') or []:
        source = players.get(str(player.get('id'))) or {}
        for group in source.get('stats') or []:
            stats = group.get('stats') or {}
            if 'Expected goals (xG)' in stats:
                player['xg'] = (stats['Expected goals (xG)'].get('stat') or {}).get('value')
    return out


def verified_detail_identity(payload, source_id, identity):
    """Only exact match + oriented names + kickoff allow replacement of cached detail."""
    if not isinstance(identity, dict):
        return False
    from collector.participant_alias import punctuation_identity_key
    from collector.util import parse_datetime
    general = payload.get('general') or {}
    if str(general.get('matchId') or '') != str(source_id):
        return False
    supplied = parse_datetime(general.get('matchTimeUTCDate'))
    expected = parse_datetime(identity.get('start_time'))
    if not supplied or not expected or abs((supplied - expected).total_seconds()) > 60:
        return False
    for key in ('home', 'away'):
        actual = (general.get(key+'Team') or {}).get('name')
        expected_name = (identity.get(key) or {}).get('name')
        if not actual or not expected_name or punctuation_identity_key(actual) != punctuation_identity_key(expected_name):
            return False
    return True


def refresh_due(extra, now=None):
    if extra.get('fotmob_detail_rev') == REVISION:
        return False
    from collector.util import parse_datetime
    checked = parse_datetime(extra.get('fotmob_detail_checked_at'))
    return checked is None or ((now or datetime.utcnow()) - checked).total_seconds() >= 900
