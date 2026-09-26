"""Bounded on-demand player facts. Only previously verified native IDs may fetch.

Market values are dated estimates, never transfer fees. Unknown currency stays
unknown. Club at match time is independent from the current primary club.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import math
import re
import threading
import time
from collector.profile_dates import profile_date

_CACHE = OrderedDict()
_LOCK = threading.RLock()
TTL = 6 * 3600
RETRY = 600
MAX_ENTRIES = 256


def _number(value):
    if value in (None, '', 'undefined') or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def _text(value):
    return str(value).strip() if isinstance(value, (str, int, float)) and str(value) not in ('undefined','null') else None


def parse_profile(root, player_id, name):
    from collector.participant_alias import punctuation_identity_key
    if not isinstance(root, dict) or str(root.get('id')) != str(player_id):
        return {}
    if not name or punctuation_identity_key(root.get('name') or '') != punctuation_identity_key(name):
        return {}
    out = {}
    team = root.get('primaryTeam') or {}
    if team.get('teamId') and team.get('teamName'):
        out['current_club'] = {'id': str(team['teamId']), 'name': team['teamName'],
                               'logo': f"https://images.fotmob.com/image_resources/logo/teamlogo/{team['teamId']}.png",
                               'on_loan': team.get('onLoan') is True}
    for key, source in [('birth_date', 'birthDate'), ('contract_end', 'contractEnd')]:
        value = root.get(source) or {}
        if isinstance(value, dict) and value.get('utcTime'):
            out[key] = value['utcTime'][:10]
    position = (root.get('positionDescription') or {}).get('primaryPosition') or {}
    if position.get('label'):
        out['position'] = position['label']
    keys = {'height_sentencecase':'height_cm', 'shirt':'number', 'age_sentencecase':'age', 'preferred_foot':'preferred_foot', 'country_sentencecase':'nationality'}
    info_value = None
    for row in root.get('playerInformation') or []:
        value = row.get('value') or {}; key = row.get('translationKey')
        if key in keys:
            supplied = value.get('numberValue') if value.get('numberValue') is not None else _text(value.get('fallback'))
            if supplied is not None: out[keys[key]] = supplied
        if row.get('countryCode'): out['country_id'] = row['countryCode']
        if key == 'transfer_value': info_value = row
    values = (root.get('marketValues') or {}).get('values') or []
    now = datetime.now(timezone.utc).isoformat()
    values = [v for v in values if isinstance(v, dict) and _number(v.get('value')) is not None and re.fullmatch(r'[A-Z]{3}', str(v.get('currency') or '')) and v.get('date') and str(v['date']) <= now]
    if values:
        latest = max(values, key=lambda v:v['date'])
        out['market_value'] = {'amount': _number(latest['value']), 'currency': latest['currency'], 'as_of': latest['date'][:10], 'estimated':True}
        # The headline may be newer than the chart; use it ONLY with explicit currency.
        if info_value:
            value = info_value.get('value') or {}; fallback = str(value.get('fallback') or '')
            if fallback.startswith('€') and _number(value.get('numberValue')) is not None:
                out['market_value']['amount'] = _number(value['numberValue'])
                out['market_value']['currency'] = 'EUR'
                if latest['currency'] != 'EUR' or out['market_value']['amount'] != _number(latest['value']): out['market_value']['as_of'] = None
    elif info_value:
        value = info_value.get('value') or {}
        if str(value.get('fallback') or '').startswith('€') and _number(value.get('numberValue')) is not None:
            out['market_value'] = {'amount':_number(value['numberValue']), 'currency':'EUR', 'as_of':None, 'estimated':True}
    history = ((root.get('careerHistory') or {}).get('careerItems') or {}).get('senior') or {}
    career = []
    for row in history.get('teamEntries') or []:
        if not row.get('teamId') or not row.get('team'): continue
        career.append({'team_id':str(row['teamId']), 'team':row['team'], 'start':profile_date(row.get('startDate')),
                       'end':profile_date(row.get('endDate')), 'active':row.get('active') is True,
                       'appearances':_text(row.get('appearances')), 'goals':_text(row.get('goals')), 'assists':_text(row.get('assists')),
                       'transfer_type':_text((row.get('transferType') or {}).get('text')), 'uncertain':row.get('hasUncertainData') is True})
    if career: out['career'] = career[:40]
    league = root.get('mainLeague') or {}
    if league.get('leagueName'):
        out['season_summary'] = {'competition':league['leagueName'], 'season':league.get('season'),
            'stats':[{'label':r['title'], 'value':r['value']} for r in league.get('stats') or [] if r.get('title') and _text(r.get('value')) is not None]}
    out['profile_checked_at'] = datetime.now(timezone.utc).isoformat()
    return out


def enriched_profile(player_id, name, getter=None):
    """Caller must establish a verified football lineup or scoped scorer identity first."""
    if not re.fullmatch(r'\d{1,10}', str(player_id or '')) or not name:
        return {}
    key=(str(player_id),name)
    now=time.monotonic()
    with _LOCK:
        previous = _CACHE.get(key) or {}
        if previous.get('due',0)>now:
            return deepcopy(previous.get('data') or {})
        # Reserve before I/O: concurrent visitors share the prior snapshot.
        _CACHE[key]={'due':now+RETRY,'data':previous.get('data') or {}}
        _CACHE.move_to_end(key)
        while len(_CACHE)>MAX_ENTRIES: _CACHE.popitem(last=False)
    try:
        if getter is None:
            from collector.http import fetch_url
            getter=lambda url:fetch_url(url,timeout=6)
        result=getter('https://www.fotmob.com/api/data/playerData?id='+str(player_id))
        data=parse_profile(result.payload,player_id,name) if result.ok else {}
    except Exception:
        data={}
    if data:
        with _LOCK: _CACHE[key]={'due':time.monotonic()+TTL,'data':data}
        return deepcopy(data)
    return deepcopy(previous.get('data') or {})
