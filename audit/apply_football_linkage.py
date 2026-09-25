"""Apply reviewed source-only patch and verify every resulting file."""
from pathlib import Path
import gzip,hashlib,json,subprocess
packed=b''.join(Path(f'audit/football-linkage.{i:02d}').read_bytes() for i in range(5))
patch=gzip.decompress(packed)
assert hashlib.sha256(patch).hexdigest()=='630c75dba962bf62c6b00416720c2ec0838f2525db9f1e0b140b52845e5f4ea1'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
expected=json.loads(Path('audit/football_linkage_sha256.json').read_text())
actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in expected}
assert actual==expected,(actual,expected)
print('Source patch and six resulting file hashes verified; no production access.')
