"""Restore checksum-verified global football edits in an isolated checkout.

No database or production request is made. Source changes are published only to
an isolated repair branch after the regression gate, never automatically to main.
"""
import gzip
import hashlib
import subprocess
from pathlib import Path

chunks=[Path(f'audit/global-football-patch.{n:02}') for n in range(3)]
patch=gzip.decompress(b''.join(p.read_bytes() for p in chunks))
assert hashlib.sha256(patch).hexdigest()=='f2df7749613db6e56ff972f104b72c70c3f3645f10f724772102651aad7296d0'
subprocess.run(['git','apply','--check','-'],input=patch,check=True)
subprocess.run(['git','apply','-'],input=patch,check=True)
print('Applied exact isolated all-football patch; no production or DB mutation.')
