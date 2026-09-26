"""Apply reviewed News-only edits in an isolated checkout. No production work."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

BASE='833d24c354fe326da64ed2a4a9478eaa3b56ea92'
EXPECTED={
 'news_runtime.py':'c889e50a1cfe2034f6d99cdb8d7037c2cbc7300a0e2babdca02ad32cbf76bfa3',
 'bot/scheduler.py':'3a766a4f609ac8b02611addfa39ca7593cdc9c1ec5ccc2fc2dc9d0c29b233b7c',
 'bot/news_budget.py':'c4f95465a7c3eedd5abc6e4857900ebed8d16ab6270a14bfa221b43dfca92175',
 'deploy/news/preflight.py':'04cadc72f094340a8f5e7503aa3694f9235ad19871fe03d7b6d08a483d0e9d08',
 'tests/test_news_deploy_contract.py':'8831c4a49db2faaa2b17173b1314ec0b4fc93893300ff1b6b646727bdd9de520',
 'tests/test_c22_news_runtime.py':'af8257ef5db6070a24b1f808e0217508040eabb595c02718dcc33d34818d5ffc',
 'tests/test_c22_news_scheduler.py':'5a4bbb6df8157093a0f4ce39d09c409fb53b6891d4d18737856c2f016d95453a',
}


def edit(name, changes):
 p=Path(name)
 if hashlib.sha256(p.read_bytes()).hexdigest()==EXPECTED[name]: return
 assert p.read_bytes()==subprocess.check_output(['git','show',f'{BASE}:{name}']),name
 text=p.read_text()
 for old,new in changes:
  assert text.count(old)==1,(name,old[:60],text.count(old))
  text=text.replace(old,new)
 p.write_text(text)


def apply():
 edit('bot/news_budget.py',[(
  "        requests = int(os.environ.get('NEWS_AI_MAX_REQUESTS_PER_RUN', str(max_articles)))\n        daily = int(os.environ.get('NEWS_AI_MAX_REQUESTS_PER_DAY', '40'))\n        return AiRequestBudget(requests, os.environ.get('NEWS_AI_LEDGER_PATH'), daily)",
  "        from news_runtime import request_limits\n        limits = request_limits(os.environ)\n        if limits is None:\n            return AiRequestBudget(0)\n        requests, daily = limits\n        return AiRequestBudget(requests, os.environ.get('NEWS_AI_LEDGER_PATH'), daily)"
 )])
 edit('deploy/news/preflight.py',[
  ('    "requirements.txt", "database.py", "models.py", "public_index.py",','    "requirements.txt", "news_runtime.py", "database.py", "models.py", "public_index.py",'),
  ('    return errors\n\n\ndef main(', '    if str(ROOT) not in sys.path:\n        sys.path.insert(0, str(ROOT))\n    from news_runtime import configuration_errors\n    errors.extend(configuration_errors(env))\n    return errors\n\n\ndef main('),
  ('        report["errors"].extend(runtime_errors(env))','        report["errors"].extend(runtime_errors(env))\n        if not report["errors"]:\n            from news_runtime import storage_errors\n            report["errors"].extend(storage_errors(env))'),
 ])
 edit('tests/test_news_deploy_contract.py',[
  ("            'NEWS_LEGACY_REPAIR_ACK':'1'}", "            'NEWS_LEGACY_REPAIR_ACK':'1',\n            'NEWS_AI_MAX_REQUESTS_PER_RUN':'2','NEWS_AI_MAX_REQUESTS_PER_DAY':'3',\n            'NEWS_HISTORICAL_REPAIR_ENABLED':'0','NEWS_EXPANDED_FEEDS_ENABLED':'0',\n            'OPENAI_API_KEY':'FIXTURE_ONLY', 'NEWS_AI_LEDGER_PATH':'/news-data/budget.sqlite',\n            'RAILWAY_VOLUME_MOUNT_PATH':'/news-data'}"),
  ("    monkeypatch.setattr(guard.os,'chdir',lambda path:dirs.append(path))", "    monkeypatch.setattr(guard.os,'chdir',lambda path:dirs.append(path))\n    # This remains an exec-target unit test; actual mounts have dedicated tests.\n    import news_runtime\n    monkeypatch.setattr(news_runtime,'storage_errors',lambda env:[])"),
 ])


def verify():
 for name,wanted in EXPECTED.items():
  actual=hashlib.sha256(Path(name).read_bytes()).hexdigest()
  assert actual==wanted,(name,actual,wanted)
 untouched={}
 for name in subprocess.check_output(['git','ls-tree','-r','--name-only',BASE]).decode().splitlines():
  if name in EXPECTED: continue
  original=subprocess.check_output(['git','show',f'{BASE}:{name}'])
  assert Path(name).read_bytes()==original,name
  untouched[name]=hashlib.sha256(original).hexdigest()
 Path('evidence').mkdir(exist_ok=True)
 Path('evidence/reviewed-hashes.json').write_text(json.dumps(EXPECTED,indent=2))
 Path('evidence/unchanged-source-hashes.json').write_text(json.dumps(untouched,indent=2))
 print('Unchanged existing source paths:',len(untouched))


if __name__=='__main__':
 assert subprocess.check_output(['git','symbolic-ref','--short','HEAD']).decode().strip()=='fix/news03-startup-c22-20260926'
 if sys.argv[1:]==['--apply']: apply()
 elif sys.argv[1:]!=['--verify']: raise SystemExit('unsupported mode')
 verify()
