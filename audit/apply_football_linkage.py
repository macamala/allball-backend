"""Apply reviewed source-only patches and verify every resulting file."""
from pathlib import Path
import gzip,hashlib,json,subprocess
packed=b''.join(Path(f'audit/football-linkage.{i:02d}').read_bytes() for i in range(5))
patches=[(gzip.decompress(packed),'630c75dba962bf62c6b00416720c2ec0838f2525db9f1e0b140b52845e5f4ea1'),(Path('audit/football-linkage-integrity.patch').read_bytes(),'cb952d991cd3a63909fe8004437434ce1fe31df37bfdddb9f0cabbe2822c5598')]
for patch,expected_hash in patches:
    assert hashlib.sha256(patch).hexdigest()==expected_hash
    subprocess.run(['git','apply','--check','-'],input=patch,check=True)
    subprocess.run(['git','apply','-'],input=patch,check=True)
expected=json.loads(Path('audit/football_linkage_sha256.json').read_text())
actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in expected}
assert actual==expected,(actual,expected)
print('Source patches and seven resulting file hashes verified; no production access.')
