"""Import the real engine with deployment URL forms; never connect to a DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.parametrize("url,expected,driver", [
    ("postgres://qa:dummy@127.0.0.1:1/test?sslmode=require", "postgresql+psycopg2://qa:dummy@127.0.0.1:1/test?sslmode=require", "psycopg2"),
    ("postgresql://qa:dummy@127.0.0.1:1/test", "postgresql+psycopg2://qa:dummy@127.0.0.1:1/test", "psycopg2"),
    ("postgresql+psycopg2://qa:dummy@127.0.0.1:1/test", "postgresql+psycopg2://qa:dummy@127.0.0.1:1/test", "psycopg2"),
    ("postgresql://qa:p%40ss%2Fword@127.0.0.1:1/test?application_name=ninko%20sports", "postgresql+psycopg2://qa:p%40ss%2Fword@127.0.0.1:1/test?application_name=ninko%20sports", "psycopg2"),
    ("sqlite:///:memory:", "sqlite:///:memory:", "pysqlite"),
])
def test_real_engine_driver_import_without_database_connection(url, expected, driver):
    code = "import database,json; print(json.dumps({'url':database.DATABASE_URL,'driver':database.engine.dialect.driver})); database.engine.dispose()"
    result = subprocess.run([sys.executable, "-c", code], env={**os.environ, "DATABASE_URL":url}, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"url":expected,"driver":driver}
