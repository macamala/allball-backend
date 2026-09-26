# Combined checkpoint 21 — News03 prepared on C20, 26 September 2026

## Status: PREPARED AND JOINTLY TESTED, NOT DEPLOYED

This is the latest prepared News03 integration record. **C20 remains the current production release.** This document does not supersede C20 as deployed source or declare News ingestion, all football results, all-sport freshness or a public launch complete. The primary Live Scores chat remains the only merge/deploy owner; keep backend issues6 and8 open.

User requested the exact new News03 package on top of current Live Scores, new joint tests, persistent actual-request accounting and explicit approved caps before activation, no new paid resources without approval, no hidden historical rewrites, and saving prepared work when access/storage/budget cannot be established. Those activation prerequisites remain unresolved; neither main nor master moved in this pass.

## Exact source and provenance

- Production backend main, freshly read before and after: `ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726` (C20).
- Production frontend master, freshly read before and after: `7183733e5eed7dae566aeaf1632fc757c547cc4c` (C19 frontend, unchanged by C20/News03).
- Original News03 candidate: `f08633d0221fbf9d9850f291dbab4ffe927c11c7`.
- Its frozen News02 base: `99cc5f0a1d0951e286c58bd1176d729141a28f02`.
- Original News03 checkpoint: `c3bdb1ccf39373cbb5a94a7a5964ab954f466e33`, `docs/checkpoints/NINKOSPORTS_NEWS_03_2026-09-26.md`.
- **New integrated/tested candidate: `39b49492fe38fdac50a7320673d4c7e244c6dae2`**, branch `integration/news03-c20-20260926-21`.
- This later checkpoint is documentation only. Do not confuse its commit with the tested runtime commit.
- Source preservation branch `rollback/pre-news03-c21-20260926` points to the unchanged production C20 SHA. This is NOT a database backup.

Read before work: latest issue6 comment5844408311, latest News03 and coordination issue8 comments5844137533/5844410465, C20 production update atb777820375975247d94fce6eabab8e1f9607048c, original News03 checkpoint and both current production heads. News01/02 and C18/C20 were already integrated. No old checkpoint was replayed over current code.

## Integration proof and exact scope

Original News03 compare against its base contained19 paths. The integration applies only its **14 runtime/test paths**; it does not copy old release workflows, re-run source probes or replace unrelated documentation. The five existing modified News paths were byte-unchanged between the frozen News02 base and C20 before application. All14 resulting files exactly match the pinned News03 candidate.

Runtime paths (10):
- bot/feeds.py
- bot/fetch_sources.py
- bot/news_budget.py
- bot/news_feed_http.py
- bot/news_policy.py
- bot/news_source_catalog.py
- bot/news_verified_feeds.py
- bot/pipeline.py
- bot/rewrite_ai.py
- repair_content.py

Original News03 tests (4): tests/test_news03_budget.py, test_news03_http.py, test_news03_integration.py, test_news03_policy.py.

Additional integration-only paths (3): tests/test_c21_news03_release.py, audit/c21_integrate_news03.py, .github/workflows/c21-news03-integration.yml.

Final tested compare is ahead4/behind0 from C20,17files. **All523 other tracked C20 files were checked byte-for-byte unchanged**, including every collector/runtime guard, models/database/schema, app.py, public_read/public_index/editorial, News02 extract-date code, News02 Dockerfile/preflight, scheduler and requirements. No frontend source changed. No new source-policy relaxation.

Exact News03 delta SHA256: `a8caf5c25a493d9b876e104b5e209f2f79363d04bf4a15c09b53f9b31dfc7ce3`.
The new candidate has C20 as ancestor and applies the News03 delta rather than making the old News03 branch the production branch. Existing line-ending normalization in the original News03 files accounts for much of the textual diff; semantic changes were reviewed separately.

## What the prepared package contains

New articles require accepted original prose. Failed/unavailable/budget-exhausted AI processing cannot publish extracted publisher copy or an RSS-summary fallback as an original article. Automated checks hold copied/overlapping, unsupported-numeric, incomplete, redirect and certain direct-quote drafts. They are heuristics, not guarantees of factuality or rights.

Known-timezone original publication timestamps are preserved; stale, naive, missing or future dates are held rather than replaced by the ingestion date. Sport queues rotate instead of a permanent football-first order. New RSS expansion is opt-in and remains unactivated here.

Actual AI HTTP attempts require a reservation before dispatch. Timeouts, failed requests,429retries and length retries consume the same allowance; they are not refunded when output is rejected. The SQLite ledger is a shared-file request counter, NOT a money cap, token-cost estimator or account-wide/multihost guarantee. Separate local ledgers on multiple workers do not constitute one global cap.

Historical repair scans default off unless explicitly opted in. The unchanged scheduler still has a separate index_missing loop; do not equate disabled body-repair functions with proof that the entire scheduler never touches historical index rows. This is one reason the existing News02 acknowledgement must remain a genuine review gate, not a checkbox to bypass.

Original source URLs remain in stored provenance. Source/image rights and required credits have not been cleared. Existing editorial/public sanitizers and their credit-like-text handling were deliberately NOT modified or certified by this integration. Material needing required attribution/photographic credits must pass a separate review before enabling that source/content path. No actual production attribution or photograph was changed.

## New joint tests — actual inspected evidence

**GitHub Actions run36229950821**, workflow head9c0c692c4d2c043f97949abdad35f20f9fe2636f, both jobs completedSUCCESS:

- combined-backend job108371099929: **1327 test cases,0failures,0errors,0skips** in80selected files. This is the union of the latest C20 selection and the original News03 selection plus11new integration cases, not the old separate1235pass reused as acceptance.
- Count reconciliation: C20's1200 +22additional pre-existing News tests +94News03 cases +11new integration cases =1327. This is a selected combined backend suite, not every unrelated repository test.
- unchanged-frontend job108371100047: **329 complete frontend tests,0failures,0errors,0skips**, plus24polling-policy and6request-ownership checks. Production-API-target build passed. No frontend deployment.
- Existing News02 Docker recipe built from the combined source, Python3.12.14. Actual image inspection/preflight/import checks passed.
- Actual default unconfigured image invocation exited78 before scheduler execution. No live database or AI credentials were provided; no production ingestion ran.
- Tests executed in a container with `--network none`, ephemeral SQLite fixtures and mocked upstream/AI. Docker build downloaded ordinary dependencies. These are not real provider/editorial/output acceptance or production browser checks.

### New persistence and safety cases

Separate Python processes sharing the same fixture ledger preserve already-reserved attempts after the first process exits with a simulated failure. The next process can consume only the remaining daily allowance. Six concurrent processes against one shared fixture ledger produced exactly three allowed reservations, not separate free allowances. Corrupt ledger bytes are not silently replaced; reservation fails closed. Zero per-run/day caps do not start ingestion. Explicit0/false/off/invalid or absent historical flags do not start historical DB scans. News03 flags do not bypass the old News02 service-ID/acknowledgement guard.

**This proves the accounting code across process boundaries on one shared test file, NOT persistence across a Railway restart/deploy.** Fixture limits2/3 and temporary test directories are NOT production budget approval or proposed production storage.

### Downloaded artifacts independently verified

| Artifact | ID | ZIP SHA256 |
| --- | --- | --- |
| c21-combined-news03-backend |10901897318|91636a641dfafdd501637d6fa6fb96a760e7f3b8d151ea529e2dd289635d50fa|
| c21-unchanged-frontend |10901727485|5139b999df0a0a5e47f0880525736a9540e28c939bddd45c2d9b85c1e01e7542|

ZIP integrity checked; actual JUnit, candidate markers, image preflight/import output and source manifests parsed. All14 News03 hashes and523protected-source hashes matched the downloaded tested archive. Full source and reviewed delta are in the backend artifact. No failed CI attempt was relabelled as passed; this integration gate passed its first execution. CI artifacts have30-day retention, not permanent backup.

Original source artifact10901105275 was also downloaded and ZIP SHA256c1c5716f1d7276f9ee69dd39e5dffa5d3f1f0d1cee61b32f9308090dfa1917e0 verified before review. Original News03 metadata observations remain historical point-in-time evidence, not new production coverage.

## Actual activation blockers, directly checked

Existing News service: hopeful-blessing / be857be7-a029-4663-81c7-bcde75efc482 in project17f6ebff-0f6b-42dd-be86-35ca9ca40301, environmentcb27d851-9198-47c8-a733-8356e8b6cf63.

1. **Persistent storage absent in returned service status.** get-status reports `volumes: []` for this News service; no approved durable ledger directory was established. No new volume/resource was created. No live restart persistence test is claimed.
2. **Actual variable values unavailable.** The connected OAuth list-variables response explicitly gives `valuesRedacted: true`; the returned names do not include NEWS_AI_LEDGER_PATH, NEWS_AI_MAX_REQUESTS_PER_RUN, NEWS_AI_MAX_REQUESTS_PER_DAY, NEWS_EXPANDED_FEEDS_ENABLED or NEWS_HISTORICAL_REPAIR_ENABLED. Do not infer a DB identity or flag value from a variable name.
3. **No explicit approved request caps retrieved.** Prior NEWS_MAX_AI_ARTICLES<=10 is an accepted-article operational limit, not authorization for a daily request/dollar budget. News03 default40/day and the2/3fixture values are not approved spending. No cap was invented or configured.
4. **Source/root and single-process ownership unresolved.** get-service-config still has no source stanza, usesRAILPACK and start`python -m bot.scheduler`. Correct backend binding/root and the approved running revision are not verified. No replacement service or alternate hidden process was started. One configured replica alone does not prove no other News process exists.
5. **Old startup fault still present in the latest available logs.** Latest News deployment remains79f761eb-3afc-457a-b222-15c1a5c63088 from20September. Its last runtime log entries repeat`python: command not found`. Those are20September log timestamps, not a newly observed crash today. SUCCESS is not proof of healthy ingestion.
6. **Expanded-feed extraction and rights not accepted.** The29prepared metadata endpoints/27sport scopes include the historical21fresh sport scopes,6additional stale-feed scopes and14scopes without prepared usable sources. None is newly certified as a complete production article/image source here. NEWS_EXPANDED_FEEDS_ENABLED was not enabled.

No Railway variable/config/start command, NEWS_LEGACY_REPAIR_ACK, News activation, database connection, resource or setting was changed. Historical flag was not written to production; the candidate's default-off behavior is tested and the required eventual explicit production value remains0. Do not say the existing old worker configuration has been safely updated.

## Production remained unchanged

Fresh end-of-pass GitHub heads and direct Railway deployment reads:
- API b9d2539c-b8cc-49b9-bd31-68e39bb50039, SUCCESS, backendC20 SHA above.
- results-worker98ceeeb2-9762-4686-81da-fc9e0c44521a, SUCCESS, backendC20 SHA above.
- frontendeb8f55ff-64b5-47da-9d5f-99ef218df5ef, SUCCESS, frontend7183733 SHA above.
- News remains old deployment79f761eb..., not configured with the prepared News Dockerfile.

**Services deployed in this pass:0. Actual external AI calls:0. Newly confirmed public News03 articles:0.** No source->real extraction->real draft->production DB->public article test ran because the activation gates are not met. No new production desktop/mobile/crest acceptance is claimed. Existing C20 source and its retained tests are preserved, but its remaining football results/identity/asset gaps stay open.

No Railway Agent, TinyFish session/image, new subscription, user credential disclosure, database reset, manual result edit, mass historical article rewrite, force-push, frontend redeploy or unrelated staged Railway change. Existing staged patchdb7eb99e-400a-4e62-ba03-c10610fea2f4 targets another diagnostic service and remains untouched.

## Controlled next release and rollback plan

- Keep the tested candidate saved. Fresh-read main/master and issues6/8 again before any release; later Live Scores work may advance beyond C20. Reconcile only the missing News03 delta, never move main backwards or apply an entire old branch snapshot.
- Establish authorized backend source/root for the EXISTING News service, non-secret DB identity/worker flags, a single News owner, an approved persistent ledger directory and explicit approved request caps. Do not obtain/echo secrets through a different tool to bypass OAuth redaction. Do not use the Agent as a credential workaround.
- Before activation, verify a harmless ledger marker/reservation survives the actual deployment/restart on the approved storage, with no AI call. Review preservation/backup of the ledger; losing it resets accounting. No filesystem probe on production has been performed here.
- Retain deploy/news/Dockerfile and `python deploy/news/preflight.py --run` for this News service only. Keep News02 guards; its image/check mode does not itself validate persistence, new request-cap approval, uniqueness of News processes or image rights. Do not blindly set NEWS_LEGACY_REPAIR_ACK.
- Set NEWS_HISTORICAL_REPAIR_ENABLED=0 explicitly in the eventual authorized config. Enable expanded feeds only after selected source extraction and required attribution/image review. Use bounded approved actual-request quotas and record failed/retry reservations.
- Rerun relevant combined tests on the exact future deploy commit, persist preflight with actual current refs/config/rollback boundary, then deploy only necessary services. News03 has no frontend changes; do not redeploy frontend merely to match a checkpoint number.
- Only after those gates, test a bounded actual source->extraction->original draft->DB->public story and review original date, claims/category, photo/credits, internal URL, mobile/desktop full text and duplication. Compare Live Scores before/after without rewriting scores or weakening identity guards.
- If a future activation misbehaves, stop/disable only the News process through an authorized service-specific change first; preserve ledger and all article/score rows. A code rollback is a reviewed forward revert limited to News03 runtime paths against the then-current head, not a branch reset or DB rollback. No rollback has been executed.

Separate outstanding work: stale homepage article selection (do not re-date old stories),14missing source adapters/stale alternatives, factual/editorial/image/attribution review, semantic duplicate handling, actual News health/cost acceptance; C20's remaining football conflicts, source-only rich MatchCentres, tables/old links/transfers/scorers/brackets/assets. Keep all of these open.
