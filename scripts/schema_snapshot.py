"""Read-only production schema snapshot. No writes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

url = os.environ["DATABASE_URL"]
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://") :]
engine = create_engine(url)
insp = inspect(engine)
tables = sorted(insp.get_table_names())
out = {"tables": {}, "row_counts": {}}
for name in tables:
    out["tables"][name] = {
        "columns": [
            {"name": col["name"], "type": str(col["type"]), "nullable": col["nullable"]}
            for col in insp.get_columns(name)
        ],
        "pk": insp.get_pk_constraint(name),
        "uniques": insp.get_unique_constraints(name),
        "indexes": [
            {"name": idx["name"], "unique": idx["unique"], "columns": idx["column_names"]}
            for idx in insp.get_indexes(name)
        ],
    }
with engine.connect() as conn:
    for name in tables:
        out["row_counts"][name] = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
path = Path("audit") / "production_schema_pre_migrate.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print("tables", len(tables))
print("names", ",".join(tables))
print("sports_tables", [n for n in tables if n.startswith("sports_")])
print("row_counts_sports", {k: v for k, v in out["row_counts"].items() if k.startswith("sports_") or k in {"articles"}})
