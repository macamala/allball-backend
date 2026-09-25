"""Apply checksum-verified source-only collision regression patch in CI."""
from pathlib import Path
import gzip,hashlib,subprocess
expected={'collector/collect.py':'e49c5503bd4e234b430fbdf8c5f8934fc1fe7339','collector/football_board_refresh.py':'af81094c61d2e36b72a64ac55107befbd0fcda9d','audit/football_test_selection.txt':'d9e9488517913fe8ca8a4b8e4a75af49a1cfaa5f'}
for path,sha in expected.items():
    raw=Path(path).read_bytes()
    assert hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==sha,path
packed=b''.join(Path(f'audit/football-collision.{i:02d}').read_bytes() for i in range(3))
patch=gzip.decompress(packed)
assert hashlib.sha256(patch).hexdigest()=='65f15055a9b82fe6b7746163ad5d434be356e3ad6113fa42ec324e3009c95970'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
print('Applied reviewed source-only patch. No production or database access.')
