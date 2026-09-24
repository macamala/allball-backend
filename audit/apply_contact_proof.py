"""Preserve the collector's actual completed-fetch timestamp through normalization."""
from pathlib import Path
p=Path('collector/normalize.py');s=p.read_text()
old='"source_fetch_time": raw.get("source_fetch_time") or raw.get("retrieved_at"),'
new='"source_fetch_time": raw.get("source_fetch_time") or raw.get("retrieved_at") or raw.get("fetch_completed_at"),'
assert s.count(old)==1
p.write_text(s.replace(old,new))
