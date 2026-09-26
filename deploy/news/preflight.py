"""News image/start guard. Inspection does not import app/DB/bot or use network."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
NEWS_SERVICE_ID = "be857be7-a029-4663-81c7-bcde75efc482"
REQUIRED_FILES = (
    "requirements.txt", "database.py", "models.py", "public_index.py",
    "public_read.py", "editorial.py", "taxonomy_resolver.py", "repair_content.py",
    "bot/__init__.py", "bot/scheduler.py", "bot/fetch_sources.py", "bot/extract.py",
    "bot/feeds.py", "bot/rewrite_ai.py", "sports_registry/__init__.py",
)
DEPENDENCIES = ("apscheduler", "feedparser", "sqlalchemy", "psycopg2", "httpx", "requests")
FALSE_VALUES = {"0", "false", "no", "off"}


def inspect_artifact(root: Path, finder=importlib.util.find_spec) -> dict:
    errors = []
    hashes = {}
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing_or_linked_backend_file:{relative}")
            continue
        raw = path.read_bytes()
        hashes[relative] = hashlib.sha256(raw).hexdigest()
        if path.suffix == ".py":
            try:
                compile(raw, relative, "exec")
            except (SyntaxError, ValueError):
                errors.append(f"invalid_python:{relative}")
    if (root / "package.json").exists():
        errors.append("unexpected_node_build_context")
    if (root / ".env").exists():
        errors.append("unexpected_baked_dotenv")
    for module in DEPENDENCIES:
        try:
            present = finder(module) is not None
        except (ImportError, ValueError, AttributeError):
            present = False
        if not present:
            errors.append(f"missing_dependency:{module}")
    return {"artifact_ready": not errors, "errors": errors, "source_sha256": hashes,
            "python": sys.version.split()[0], "news_started": False,
            "runtime_health_verified": False}


def runtime_errors(env) -> list[str]:
    """Fail closed before importing the legacy, immediately-writing scheduler.

    Only keys/error codes are returned, never a secret or its configured value.
    NEWS_MAX_AI_ARTICLES is NOT a dollar/request cap: legacy repair has separate
    calls and retries. Its explicit acknowledgement is required until replaced.
    """
    errors = []
    if env.get("NEWS_WORKER_ENABLED") != "1":
        errors.append("news_worker_not_explicitly_enabled")
    if env.get("RAILWAY_SERVICE_ID") != NEWS_SERVICE_ID:
        errors.append("wrong_or_missing_news_service_identity")
    for flag in ("WORKER_DISABLED", "RESULTS_COLLECTION_ENABLED",
                 "RESULTS_SCHEDULER_ENABLED", "RESULTS_WRITE_ENABLED"):
        if str(env.get(flag, "")).strip().lower() not in FALSE_VALUES:
            errors.append(f"must_be_explicitly_false:{flag}")
    try:
        url = urlsplit(env.get("DATABASE_URL") or "")
        if url.scheme not in {"postgres", "postgresql", "postgresql+psycopg2"} or not url.hostname or not url.path.strip("/"):
            errors.append("missing_or_invalid_postgres_configuration")
    except (TypeError, ValueError):
        errors.append("missing_or_invalid_postgres_configuration")
    for flag, minimum, maximum in (("NEWS_FETCH_INTERVAL_MINUTES", 5, 1440),
                                   ("NEWS_MAX_AI_ARTICLES", 0, 10)):
        value = str(env.get(flag, "")).strip()
        if not value.isascii() or not value.isdigit() or not minimum <= int(value) <= maximum:
            errors.append(f"missing_or_invalid_integer:{flag}")
    if env.get("NEWS_LEGACY_REPAIR_ACK") != "1":
        errors.append("legacy_repair_cost_and_write_review_required")
    return errors


def main(argv=None, *, root=None, env=None, finder=None, exec_fn=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Inspect image without DB, AI or scheduler")
    mode.add_argument("--run", action="store_true", help="Guard then exec the existing News scheduler")
    args = parser.parse_args(argv)
    root = ROOT if root is None else root
    env = os.environ if env is None else env
    report = inspect_artifact(root, finder=finder or importlib.util.find_spec)
    if args.run:
        report["errors"].extend(runtime_errors(env))
    report["ready_for_requested_mode"] = not report["errors"]
    print(json.dumps(report, sort_keys=True), flush=True)
    if report["errors"]:
        return 78
    if args.run:
        os.chdir(root)
        (exec_fn or os.execv)(sys.executable, [sys.executable, "-m", "bot.scheduler"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
