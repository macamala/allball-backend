"""Apply exact-baseline source patch only; no database/runtime access."""
from pathlib import Path
import gzip,hashlib,subprocess
base={'collector/football_board_refresh.py':'cc38dbd1fd226fb46cc16a0a2914bf8584a5a357','audit/football_test_selection.txt':'47821764efdc0935b0a5a9a6553d99fe007b258f'}
for name,sha in base.items():
    raw=Path(name).read_bytes()
    assert hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==sha,name
patch=gzip.decompress(b''.join(Path(f'audit/football-priority.{i:02d}').read_bytes() for i in range(3)))
assert hashlib.sha256(patch).hexdigest()=='d2add2643ff952994d0bb89632d180155b5ca100cb00686eccd8e07b115e5626'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
expected={'collector/football_board_priority.py':'d5f6883ccf10bb02de73b1724d6bd08e026ef2dd2b2e4a573a5997e58aeec408','collector/football_board_refresh.py':'c83aaeff740b14f2c56c26a1ceaa2f482966a1a2bb50ad4d281716c9731d9e43','tests/test_football_board_priority.py':'5c585fe341cb5d24fd8e087ddad841c5151cbfe9e4d02a03d574608e5e1700a1','audit/football_test_selection.txt':'0dcd3c462ed40a55411a9a8928ac6c43c685713efb922651cdd46d8cf1c3a698'}
for name,sha in expected.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha,name
print('All four reviewed source file hashes verified.')
