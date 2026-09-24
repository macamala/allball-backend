"""Apply only the checksum-verified, locally tested recovery diff."""
import base64
import hashlib
from pathlib import Path
import subprocess
import zlib

root = Path(__file__).resolve().parent / "recovery"
expected = [root / f"{n:02d}.b64" for n in range(11)]
assert sorted(root.glob("*.b64")) == expected, "Missing or unexpected patch chunk"
data = "".join(path.read_text().strip() for path in expected)
patch = zlib.decompress(base64.b64decode(data, validate=True))
digest = hashlib.sha256(patch).hexdigest()
assert digest == "79c6f5bc2ad274529337e010403a29919ade8d63902f1141c0717a2289d885d2", "Recovery patch checksum mismatch"
path = Path("/tmp/ninkosports-verified-recovery.patch")
path.write_bytes(patch)
subprocess.run(["git", "apply", "--check", str(path)], check=True)
subprocess.run(["git", "apply", str(path)], check=True)
print(f"Applied verified recovery patch SHA256={digest}", flush=True)
