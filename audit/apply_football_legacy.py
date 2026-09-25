"""Apply exact reviewed source only; never modifies a runtime database."""
from pathlib import Path
import gzip
import hashlib
import subprocess

patch=gzip.decompress(b''.join(Path(f'audit/football-legacy.{n:02}').read_bytes() for n in range(4)))
assert hashlib.sha256(patch).hexdigest()=='6250af62f971e7bbc37d09f30b16cb3d42ef0e679c3006f46690ae242bacff33'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
p=Path('audit/football_test_selection.txt')
name='tests/test_football_legacy_classification.py'
files=p.read_text().splitlines()
if name not in files:files.append(name)
p.write_text('\n'.join(files)+'\n')
print('Exact legacy classification/result safeguard patch applied; no database access.')
