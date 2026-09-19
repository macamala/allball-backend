"""Compare SQLAlchemy models to the live database. Additive report only."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import inspect

from collector import models as collector_models  # noqa: F401
from models import Base


def schema_drift_report(bind) -> Dict[str, Any]:
    insp = inspect(bind)
    live_tables = set(insp.get_table_names())
    missing_tables: List[str] = []
    extra_tables: List[str] = []
    column_drift: List[Dict[str, Any]] = []
    for table in Base.metadata.sorted_tables:
        name = table.name
        if name not in live_tables:
            missing_tables.append(name)
            continue
        live_cols = {col["name"]: col for col in insp.get_columns(name)}
        for column in table.columns:
            live = live_cols.get(column.name)
            if live is None:
                column_drift.append({"table": name, "column": column.name, "issue": "missing_in_db"})
                continue
            model_null = bool(column.nullable)
            live_null = bool(live.get("nullable"))
            if model_null != live_null:
                column_drift.append(
                    {
                        "table": name,
                        "column": column.name,
                        "issue": "nullable_mismatch",
                        "model": model_null,
                        "db": live_null,
                    }
                )
        for live_name in live_cols:
            if live_name not in table.c:
                column_drift.append({"table": name, "column": live_name, "issue": "extra_in_db"})
    model_names = {table.name for table in Base.metadata.sorted_tables}
    extra_tables = sorted(live_tables - model_names)
    return {
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "column_drift": column_drift,
        "live_table_count": len(live_tables),
        "model_table_count": len(model_names),
    }
