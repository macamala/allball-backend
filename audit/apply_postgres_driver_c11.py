from pathlib import Path
import subprocess
subprocess.run(['git','merge-base','--is-ancestor','17315b71e870b1e49be84d6bbe70e2c8868d3bd6','HEAD'],check=True)
p=Path('database.py');s=p.read_text()
old='    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]\n'
new=old+'''\n# Use the driver declared in requirements.txt, independent of SQLAlchemy defaults.
# SQLAlchemy 2.1 changed a bare postgresql:// URL to require psycopg v3.
# Explicit driver URLs are intentionally preserved; no credentials are altered.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://") :]
'''
assert old in s;s=s.replace(old,new,1);p.write_text(s)
Path('tests/test_database_driver_startup.py').write_text('''"""Import the real engine with deployment URL forms; never connect to a DB."""
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
''')
p=Path('audit/football_test_selection.txt');s=p.read_text();assert 'tests/test_database_driver_startup.py' not in s;p.write_text(s.rstrip()+'\ntests/test_database_driver_startup.py\n')
