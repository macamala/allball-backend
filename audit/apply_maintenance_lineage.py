"""Apply reviewed, exact-anchor edits in an isolated checkout, never a database.

The workflow tests the resulting source before publishing it to its repair
branch. It never moves main and does not deploy or access production secrets.
"""
from pathlib import Path
import ast
import hashlib

EXPECTED = {
    "collector/integrity.py": "f09360e13098c5e4812c1d6c9963e8254b622382",
    "collector/source_native_reconcile.py": "6975b64571096962f703435c1e25f8cdd5e97088",
    "collector/canonical_collapse.py": "27b2ea457bf97a8d54a532ca646cfb9ed5c46c65",
    "app.py": "552061cde389de49b3c99b2817924eedf0f68873",
}


def replace(text, old, new, count=1):
    actual = text.count(old)
    if actual != count:
        raise AssertionError(f"Expected {count} occurrences, got {actual}: {old[:100]!r}")
    return text.replace(old, new)


def patch(path, text):
    if path == "collector/integrity.py":
        text = replace(text, "from collector.cache import cache_clear\n", "from collector.cache import cache_clear\nfrom collector.maintenance_policy import automatic_promotion_blocked, sync_public_visibility\n")
        text = replace(text, "    for row in query:\n        event = _sides(row)\n", "    for row in query:\n        if automatic_promotion_blocked(row):\n            continue\n        event = _sides(row)\n")
        text = replace(text, "    eligible = is_display_eligible(event) and row.event_id not in quarantine\n", "    eligible = (is_display_eligible(event) and row.event_id not in quarantine\n                and not automatic_promotion_blocked(row, extra))\n")
        text = replace(text, "    if dirty:\n        row.extra_json = dump_json(extra)\n    return dirty\n", "    synced = sync_public_visibility(row, extra, extra.get(\"display_eligible\", False))\n    return dirty or synced\n")
        text = replace(text, "            if row.display_eligible is not False\n            and _extra(row).get(\"display_eligible\") is not False\n", "            if not automatic_promotion_blocked(row)\n            and row.display_eligible is not False\n            and _extra(row).get(\"display_eligible\") is not False\n")
        text = replace(text, "        for row in cluster_rows:\n            extra = _extra(row)\n", "        for row in cluster_rows:\n            extra = _extra(row)\n            if automatic_promotion_blocked(row, extra):\n                continue\n")
        text = replace(text, "        extra.pop(\"canonical_event_id\", None)\n        row.display_eligible = True\n        row.canonical_event_id = None\n        row.extra_json = dump_json(extra)\n", "        sync_public_visibility(row, extra, True)\n")
        text = replace(text, "    for row in public:\n        extra = load_json(row.extra_json, {}) or {}\n        eligible = row.display_eligible", "    for row in public:\n        extra = load_json(row.extra_json, {}) or {}\n        if automatic_promotion_blocked(row, extra):\n            sync_public_visibility(row, extra, False)\n            continue\n        eligible = row.display_eligible")
        start = text.index("def apply_competition_attribution(")
        end = text.index("\ndef _side_name", start)
        section = text[start:end]
        # Keep the slim board view in agreement for every attribution outcome.
        section = section.replace("row.extra_json = dump_json(extra)", "sync_public_visibility(row, extra, extra.get(\"display_eligible\", row.display_eligible is not False))")
        text = text[:start] + section + text[end:]
    elif path == "collector/source_native_reconcile.py":
        text = replace(text, "from collector.models import SportsCollectorJob, SportsEvent\n", "from collector.models import SportsCollectorJob, SportsEvent\nfrom collector.maintenance_policy import automatic_promotion_blocked, sync_public_visibility\n")
        text = replace(text, "        extra = _merged_source_extra(row)\n        family =", "        extra = _merged_source_extra(row)\n        if automatic_promotion_blocked(row, extra):\n            blocked += 1\n            sync_public_visibility(row, extra, False)\n            continue\n        family =")
        text = replace(text, "        row.extra_json = dump_json(extra)\n        row.display_eligible = True\n        store_list_extra(row, extra)\n", "        sync_public_visibility(row, extra, True)\n")
    elif path == "collector/canonical_collapse.py":
        text = replace(text, "from collector.models import SportsEvent, SportsEventDetail, SportsEventObservation\n", "from collector.models import SportsEvent, SportsEventDetail, SportsEventObservation\nfrom collector.maintenance_policy import automatic_promotion_blocked, sync_public_visibility\n")
        text = replace(text, "    extra[\"display_eligible\"] = eligible\n    row.display_eligible = eligible\n    row.extra_json = dump_json(extra)\n", "    sync_public_visibility(row, extra, eligible)\n")
        text = replace(text, "    for row in rows:\n        if _repair_participants(row):\n", "    for row in rows:\n        if automatic_promotion_blocked(row):\n            continue\n        if _repair_participants(row):\n")
        text = replace(text, "        event = _event_dict(row)\n        events.append(event)\n", "        event = _event_dict(row)\n        if row.display_eligible is False:\n            event[\"extra\"][\"display_eligible\"] = False\n        events.append(event)\n")
        text = replace(text, "    if loser.canonical_event_id:\n        return False\n", "    if automatic_promotion_blocked(keeper) or automatic_promotion_blocked(loser):\n        return False\n")
        text = replace(text, "    keeper.extra_json = dump_json(k_extra)\n    _merge_event_details", "    _sync_public_flags(keeper, k_extra, True)\n    _merge_event_details")
        text = replace(text, "    loser.extra_json = dump_json(l_extra)\n", "    _sync_public_flags(loser, l_extra, False)\n")
        text = replace(text, "        \"COLLAPSED_OBSERVATION\": 0,\n", "        \"COLLAPSED_OBSERVATION\": 0,\n        \"POLICY_BLOCKED\": 0,\n")
        text = replace(text, "        if extra.get(\"canonical_event_id\") or row.canonical_event_id:\n            still[\"COLLAPSED_OBSERVATION\"] += 1\n            row.display_eligible = False\n            continue\n", "        if automatic_promotion_blocked(row, extra):\n            bucket = (\"COLLAPSED_OBSERVATION\" if extra.get(\"canonical_event_id\")\n                      or row.canonical_event_id or extra.get(\"collapse_role\") == \"observation_only\"\n                      else \"POLICY_BLOCKED\")\n            still[bucket] += 1\n            _sync_public_flags(row, extra, False)\n            continue\n")
        text = replace(text, "            row.extra_json = dump_json(extra)\n            row.display_eligible = False\n        else:\n            row.display_eligible = True if extra.get(\"display_eligible\") is not False else False\n", "            _sync_public_flags(row, extra, False)\n        else:\n            _sync_public_flags(row, extra, extra.get(\"display_eligible\") is not False)\n")
    elif path == "app.py":
        text = replace(text, "from collector.attribution import attribution_payload\n", "from collector.attribution import attribution_payload\nfrom collector.maintenance_policy import startup_integrity_enabled\n")
        text = replace(text, "    if os.getenv(\"NINKO_SKIP_INTEGRITY_BACKFILL\") != \"1\":\n", "    if startup_integrity_enabled():\n")
        # The decorator was attached to the synchronous index function rather
        # than lifespan. Index creation must be callable by its worker thread.
        text = replace(text, "@asynccontextmanager\ndef _startup_list_indexes():", "def _startup_list_indexes():")
        text = replace(text, "async def lifespan(app: FastAPI):", "@asynccontextmanager\nasync def lifespan(app: FastAPI):")
    ast.parse(text, filename=path)
    return text


pending = {}
for path, sha in EXPECTED.items():
    raw = Path(path).read_bytes()
    actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if actual != sha:
        raise SystemExit(f"Refusing changed baseline: {path}: {actual} != {sha}")
    pending[path] = patch(path, raw.decode())
# Verify every anchor and syntax before writing any of the affected files.
for path, text in pending.items():
    Path(path).write_text(text)
print("Applied lifecycle/visibility/startup guards to:", ", ".join(pending))
