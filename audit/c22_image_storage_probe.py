"""CI-only mount/counter test; fixture caps are not production approval."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

from bot.news_budget import AiRequestBudget
from news_runtime import storage_errors

phase=sys.argv[1]
assert phase in ('first','second','unmounted')
path=os.environ['NEWS_AI_LEDGER_PATH']
assert path=='/news-fixture/budget.sqlite'
errors=storage_errors(os.environ)
if phase=='unmounted':
    assert errors and not Path(path).exists()
    print(json.dumps({'phase':phase,'errors':errors,'ai_calls':0,'ledger_created':False}))
else:
    assert not errors,errors
    budget=AiRequestBudget(2,path,daily_limit=3,
        clock=lambda:datetime(2026,9,26,12,tzinfo=timezone.utc))
    decisions=[budget.reserve(),budget.reserve()]
    assert decisions==([True,True] if phase=='first' else [True,False]),decisions
    with sqlite3.connect(path) as db:
        total=db.execute('SELECT SUM(attempts) FROM news_ai_requests').fetchone()[0]
    assert total==(2 if phase=='first' else 3)
    print(json.dumps({'phase':phase,'mounted':True,'decisions':decisions,
        'fixture_reservations':total,'real_ai_calls':0,'railway_persistence_proven':False}))
