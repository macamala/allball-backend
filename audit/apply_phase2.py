"""Apply only the exact regression-tested football completion patch."""
import base64, hashlib, subprocess, zlib
from pathlib import Path
paths=sorted(Path('audit/phase2').glob('*.b64'))
assert len(paths)==7
raw=zlib.decompress(base64.b64decode(''.join(p.read_text().strip() for p in paths),validate=True))
assert hashlib.sha256(raw).hexdigest()=='42d4f0d798ee00ba34f69ecdea8c86155d51c013312eba018cc46f1c9bb417fb'
p=Path('/tmp/football-completion.patch'); p.write_bytes(raw)
subprocess.run(['git','apply','--check',str(p)],check=True)
subprocess.run(['git','apply',str(p)],check=True)
