"""Apply exact-baseline reviewed source patch; no runtime or database access."""
from pathlib import Path
import gzip,hashlib,subprocess
base={'audit/football_test_selection.txt':'2d72d2e8d933277061d218ddd8f585cc7ca9cc44','collector/football_board_priority.py':'991ce006dcdba0d41a3e82e950801382e297b5c3','collector/football_board_refresh.py':'de15dbe01505537f98ddd7a46e1e4f39cdfed299','collector/football_fixture_linkage.py':'2122a97bb398a0c1f0b76e74ca1e4adfb5ba7578'}
for name,sha in base.items():
    raw=Path(name).read_bytes()
    assert hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==sha,name
patch=gzip.decompress(b''.join(Path(f'audit/football-source-roots.{i:02d}').read_bytes() for i in range(4)))
assert hashlib.sha256(patch).hexdigest()=='117cd60eab51451682d5ef4114d8fdd154e7cc907af0df16514c7911a995763f'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
expected={'audit/football_test_selection.txt':'faba3ed0032d4a92d1d558d4c49faf77edc12279141393b20fb8df44f829494f','collector/football_board_priority.py':'32ead94ec74478a9f6f2ad21a45cef3e51b2aadff18a835846c8e3a15fe94b90','collector/football_board_refresh.py':'08540113c20c5b970978c470578e70b0624d54cfab84372e410fdbece4c2fb3d','collector/football_fixture_linkage.py':'b9244e3f7452e6301e1dc60496591b99debe130a3d6673afc448b08145e9a06b','collector/football_source_roots.py':'9672c8a1df16d1a8fcfefc1411cd34d66ae74e7bcddd934e17957ad42cd4eef3','tests/test_football_source_roots.py':'a250c4021b0cfbd176fb9c0673acb641a99e1bf634e927596c9e8457efab920e'}
for name,sha in expected.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha,name
print('Reviewed source hashes verified; only isolated source checkout modified.')
