# NinkoSports News04 review WIP — 26 September 2026

## Not a deployable/runtime-committed checkpoint

**Source research completed; local runtime changes and focused tests preserved for review. Runtime GitHub write was safety-blocked. No full accepted News04 gate, merge or deployment.** This documentation records the limitation and does not upload, apply or activate the blocked runtime payload.

The primary Live Scores chat remains the sole integration/release owner. News issue8 and primary issue6 remain open. No Railway Agent, Railway operation, real AI call, production DB mutation, main/master write, worker activation or new paid resource occurred in this News04 workstream.

## Exact base and actual remote state

Started from the primary chat's prepared C21 documentation commit `833d24c354fe326da64ed2a4a9478eaa3b56ea92`, runtime `39b49492fe38fdac50a7320673d4c7e244c6dae2`. This preserves integrated C20 + News03 and C21 boundary tests instead of replaying an old C17 snapshot. At the start, production main read `ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726`; this is an observed base, not a future reset target.

New isolated branch: `news/sources-identity-20260926-04`.
Last verified head before this documentation: `38627ae743066fd9baea4df196b31b99957105e7`, tree `ac7e89be3be524218435b963d205959b81191e41`.

That branch contains only four new source-audit/workflow files, not the News04 runtime implementation:
- `audit/news04_source_probe.py`
- `.github/workflows/news04-source-probe.yml`
- `audit/news04_additional_sources.py`
- `.github/workflows/news04-additional-sources.yml`

An unreferenced partial Git tree `1c53ef797f1f2eaadb80805ca0762fe569f4fcb1` was created with three new modules. It has no commit/ref and is NOT a runtime handoff. The subsequent GitHub.create_tree request for additional runtime code returned: "This tool call was blocked by OpenAI because we couldn't determine the safety status of the request." It was not retried, split, re-encoded, applied by another tool or placed into a workflow to bypass the block. No partial runtime tree was committed.

## Local proposed implementation — not on the branch

Four existing News files were modified locally: `bot/dedupe.py`, `bot/news_policy.py`, `bot/feeds.py`, `bot/fetch_sources.py`.
Four new local modules: `bot/news_identity.py`, `bot/news_classification.py`, `bot/news_article_html.py`, `bot/news_additional_feeds.py`.
Four new test files: `tests/test_news04_identity.py`, `tests/test_news04_classification.py`, `tests/test_news04_article_html.py`, `tests/test_news04_ingest.py`.

### Source identity

Recognized tracking parameters and fragments share one digest in the existing unique Article.external_id field, while the exact original source URL remains stored. Unknown query bytes/order, path case, trailing slashes and HTTP/HTTPS remain distinct. Too-long source URLs are held instead of silently truncated. Bounded origin/path lookup recognizes legacy raw tracking URLs; excessive ambiguity fails closed. Identical-key insert collisions do not swallow unrelated IntegrityErrors. No schema migration, old-article deletion or historical backfill was run.

The ordinary existing-duplicate path stops before extraction/AI. This is not an absolute concurrent cost guarantee: simultaneous processes may both spend requests before the unique insert check.

### News sport classification

News-specific explicit evidence separates handball from football, field hockey from ice hockey, table tennis from tennis, AFL and esports games. Source/category hints can route discovery but cannot alone establish the published sport. Full source and original draft must agree; conflicting evidence is held rather than guessed. No competition is invented. The shared resolver/version, historical cached rows and score taxonomy remain unchanged.

This is a conservative heuristic, not calibrated factuality certification. Historical reindex behavior still needs review because the global resolver is unchanged.

### Article extraction

Local tests reproduce the old HTML parser failure: an unclosed void element such as an image in an ignored header could keep later article text suppressed. The new News parser tracks void and nested elements correctly in those tests, respects the existing bounded public/robots transport, validates declared page identity and holds explicit structured paywall markers. It does not switch clients to bypass denied access.

The new parser has not been validated remotely against all affected articles. Synthetic parser success is NOT proof those actual source pages or their reuse rights are fixed.

### Additional feeds

Sixteen opt-in RSS metadata endpoints are prepared locally alongside the existing twenty-nine: **45 prepared endpoints across 35 of 41 sport scopes**, not 35 fresh production categories. The new sixteen contain nine fresh and seven stale/undated endpoint observations. Eight previously missing scopes gain prepared metadata candidates. Remaining six without prepared usable feeds are EA Sports FC, League of Legends, Valorant, Call of Duty, Overwatch and Rocket League.

The additional candidates cover Handball Planet; Futsal Focus/U.S. Futsal; The Hockey Paper; Zero Hanger; Table Tennis England; Badzine/myKhel; ESL; WPBSA/World Snooker Federation; Racing NSW; USA Water Polo/SwimSwam; Etusuora/FasterSkier. Access to metadata is not permission to republish text or images. NEWS_ADDITIONAL_FEEDS_ENABLED is an unactivated local proposal, not a production setting. All prior feeds are retained. The inspected Esports.gg feed was deliberately not added because its sampled article returned HTTP403.

## Actual completed source research

Sixty candidate URLs were examined in two bounded read-only GET audits. These ran successfully before the runtime-code write block; no AI, DB, publication or deployment was involved. Full publisher prose was not stored in their artifacts.

1. Run `36230947646`, artifact `10902760047`, observed `2026-09-26T08:49:52.315936+00:00`: 37 candidates; 7 fresh RSS, 5 stale/undated RSS, 16 read failures, 9 non-RSS pages. ZIP SHA256 `a8086a8da1360c291c75e414fd1d85d98abc8acf639ca6b3f42436bd5f752370`.
2. Run `36231266663`, artifact `10902269627`, observed `2026-09-26T08:56:26.348286+00:00`: 23 additional candidates; 3 fresh RSS, 3 stale/undated RSS, 17 read failures. ZIP SHA256 `ad4d642ee024dc503e05819d68ee110c4a6fd2da0ccc912163819dc5c71e1c99`.

Both ZIPs were downloaded and their integrity/SHA256 independently checked. Sampled actual pages exposed old handball-to-football and field-to-ice-hockey classification and three fresh-source samples with no extracted body from the old parser. Some relevant headlines had unknown sport despite more informative body evidence. These are diagnostic observations, not new-parser or production acceptance. Robots/access denials were kept and not bypassed.

## Honest test status

- **Focused local run completed: 188 tests, zero failures/errors/skips**, including **131 new News04 cases and 57 retained cases**.
- Attempt of all selected retained tests stopped at three missing-psycopg2 driver failures after 362 passes. This was a failed/incomplete run, not accepted.
- Two diagnostic subsets omitted the entire five-case PostgreSQL driver file. Each emitted JUnit with 1,453 cases and zero recorded assertion failures, but the tool calls timed out after 45 and 90 seconds without a confirmed successful process exit. Neither is a successful full gate. The second original filename contains "completed" and is retained for traceability; that filename does not describe its outcome.
- Local Python3.13 / pytest9.0.2 differs from the expected Python3.12 environment and pytest<9 project range. psycopg2 and apscheduler are unavailable locally. No stubs or project requirement changes were used to hide this.
- No News04 runtime CI/image/browser gate, real AI output or source→AI→DB→public acceptance completed. Prior C21 tests belong to C21, not this local diff.

## Verified review archive

Conversation archive **NinkoSports_NEWS04_REVIEW_WIP_2026-09-26.zip**: **131,249 bytes, 27 members**; SHA256 **`2e95df347cdbc5d24677d0b3703056808b6d413fba821eef2dd1b312e2e3c325`**.

Includes the twelve local runtime/test files, review-only patch, exact source hashes, the successful/failed/timed-out test logs and JUnit, source-observation JSON and README explaining the block. ZIP integrity and every manifest member were verified.

Review patch: 55,236 bytes; SHA256 `f7e355f8675232d9f85bb3f6ee01dcfdcf77b6a1e1767df3fd5101676126c4a7`. It was verified forward and in reverse in a temporary local copy of the exact C21 source; resulting hashes matched and **536 other base files stayed byte-identical**. This verifies work preservation, not release acceptance. The archive is for inspection/recovery, not a route around the safety-blocked code write or authorization to auto-merge.

## Remaining before any release

Respect the write block and use the normal authorized resolution process; do not retry through alternate payloads/tools. Complete dependency-compatible tests with actual successful exits and real relevant source checks. Review taxonomy persistence, attribution/image rights, source completeness, original-copy quality and duplicate concurrency.

C21's source binding/root, real environment/database identity, one News owner, approved durable shared request ledger and explicit actual-request budget remain separate activation blockers. Do not set acknowledgements blindly, create unapproved paid resources, reset production data or overwrite newer Live Scores code. Shared homepage stale-selection remains untouched. New confirmed public News04 articles: zero. Keep this work WIP and issues6/8 open.