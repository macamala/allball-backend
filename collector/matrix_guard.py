"""Frozen 180-row source matrix checksum. Never mutate the matrix file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "source_matrix_final.json"
# SHA-256 of the frozen JSON after newline canonicalization to CRLF.
# Git stores this file as LF; Windows working trees check it out as CRLF
# (i/lf w/crlf). Production Linux therefore hashed bfc5c252… of identical
# JSON. The guard must hash content, not host line endings.
FROZEN_CHECKSUM = "e16236bb4666665a6f49856fa6505e9c2defd7ec84b6fb7142fc872c79477440"


def _canonical_matrix_bytes(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\n", b"\r\n")


def matrix_checksum(path: Path | None = None) -> str:
    return hashlib.sha256(_canonical_matrix_bytes((path or MATRIX_PATH).read_bytes())).hexdigest()


def frozen_competition_ids() -> set[str]:
    rows = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if isinstance(rows, list):
        return {str(row.get("competition") or "") for row in rows if row.get("competition")}
    return {str(row.get("competition") or "") for row in rows.get("competitions") or [] if row.get("competition")}


def matrix_status() -> Dict[str, Any]:
    digest = matrix_checksum()
    rows = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if isinstance(rows, list):
        count = len(rows)
    else:
        count = int(rows.get("total_competitions") or len(rows.get("competitions") or []))
    return {
        "checksum": digest,
        "frozen": FROZEN_CHECKSUM,
        "matches_frozen": digest == FROZEN_CHECKSUM,
        "competition_count": count,
        "clean_full_180": count == 180 and digest == FROZEN_CHECKSUM,
    }


def assert_frozen_matrix() -> Dict[str, Any]:
    status = matrix_status()
    if not status["matches_frozen"] or status["competition_count"] != 180:
        raise RuntimeError(
            "STOP: source matrix checksum/count mismatch "
            f"got={status['checksum']} count={status['competition_count']}"
        )
    return status
