# NinkoSports News checkpoint 02 — 26 September 2026

## Status and ownership

**Isolated recovery candidate verified. NOT merged, deployed, or production-freshness acceptance.** News01 reader work is retained; this record does not supersede the primary Live Scores checkpoint. Backend issue8 tracks News; issue6 and the primary Live Scores chat remain the sole integration/release owner. Read their latest comments and current heads before integration; never reset newer work to these recorded bases.

The user reiterated: do not spend Railway Agent on routine work. Use direct tools, GitHub, source inspection, local tests and bounded log/config reads first. Reserve Railway Agent for genuinely necessary tasks that those methods cannot resolve. No Railway Agent was used in News02. This is a work policy, not an installed automatic lock.

Tested backend candidate: `24714028a8e3a1e3b6ac679bd6db703beeddffea`, branch `news/isolated-20260926-01`, based on `cf192f22da637b9b54495cd5fc2ba238abbfbee3`. Candidate's first source commit was `1faef7a05ec3d19910c3d9cee0996a13a60fd68f`; the second changes CI only. This checkpoint is a subsequent documentation-only commit. Frontend News01 remains tested at `808f5133db9945c8036992f3b846bd97a62a6cf8`, documented at `e67f6bf99422645c6e758eca7188883231b68605`; frontend `41d7b34c579fd87cc0a757b46ea45c3c7a945526` adds only a read-only source-export workflow.

## Verified deployed News startup fault

Direct Railway reads inspected project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, production environment `cb27d851-9198-47c8-a733-8356e8b6cf63`, existing News service `hopeful-blessing` / `be857be7-a029-4663-81c7-bcde75efc482`.

Its last inspected deployment `79f761eb-3afc-457a-b222-15c1a5c63088`, created 2026-09-20T09:55:20.031Z, was reported SUCCESS by Railway, but runtime logs repeatedly said `/bin/bash: line 1: python: command not found` between 09:55:50 and 09:56:00Z. Its build logs independently show Node detection, `npm run build`, `allball-frontend@1.0.0 build`, and Vite, while the configured start command is `python -m bot.scheduler`. That proves the inspected artifact/start-command mismatch; a successful deployment label is not a running News worker.

The config read showed RAILPACK and variable names, not values. It did not expose a repository source binding. Do not claim that the precise current source binding, database connection, WORKER_DISABLED value, other potential ingestion processes or all downstream freshness causes are verified. No Railway config, variables, deploy, restart, service, domain, staged environment or database was changed.

The earlier actual public GET sample on 26 September had no sampled latest publication after 19 September; home contained May/June articles. The inspected home route selects sport/league rows without an explicit age cutoff. Shared `app.py`/homepage/public-read code was inspected but NOT changed. Do not re-date old articles or present this candidate as a live freshness repair.

## Exact candidate scope

Only existing runtime file changed: `bot/extract.py`, specifically publication-date parsing plus its datetime import. Added:

- `deploy/news/Dockerfile`
- `deploy/news/preflight.py`
- `tests/test_news_feed_dates.py`
- `tests/test_news_deploy_contract.py`
- `.github/workflows/news02-recovery.yml`

No score collector/worker, scheduler implementation, API bootstrap, shared schema, homepage, navigation, global styles, existing requirements or frontend runtime changed. No root Dockerfile or root Railway config was added. The new Dockerfile applies only when explicitly selected for the existing News service.

### Date correction

RSS/Atom publication timestamps take priority over later modification timestamps, including ISO forms and matching feedparser parsed tuples. Explicit offsets/parsed UTC tuples normalize to UTC; timezone-naive source values remain naive. Missing dates remain missing and future dates are not silently replaced by now. The database contract is unchanged; no historical rows were rewritten. The correction addresses a demonstrated parsing bug, not proof that every provider is healthy.

### Separate News image and startup guard

The Python image copies allowlisted backend/news files, not the frontend or score collector. Build preflight checks required source, syntax and dependencies without importing the app/database/scheduler. Actual image smoke tests additionally import News modules with an ephemeral SQLite configuration and no network.

Default startup fails closed before executing the old scheduler. `--check` is inspection only, not runtime health. `--run` requires the exact existing News service identity, explicit News enablement, explicit disabled score flags, an explicit non-disabled worker flag, PostgreSQL configuration syntax, bounded explicit interval/article settings and acknowledgement of the legacy repair path. It then execs only `python -m bot.scheduler`.

**Cost limitation:** NEWS_MAX_AI_ARTICLES is not an API-request or dollar cap. The legacy pipeline counts accepted rewrites, can retry, and has separate repair work. `NEWS_LEGACY_REPAIR_ACK` forces that unresolved cost/write behavior to be reviewed; it does not solve it. Do not set the acknowledgement blindly or start the scheduler merely for diagnosis. No real AI/provider call or production ingestion was executed here.

## Actual completed evidence

GitHub Actions run `36222297707`, recovery job `108349709864`: all steps SUCCESS at the exact tested candidate.

- **1,119 selected backend tests passed**, zero failures, errors or skips, including retained football tests, existing News tests and **62 new tests** (20 date cases, 42 deployment-contract cases).
- The unchanged base parser, replayed separately, produced **13 failures out of 20 cases**, with no errors. Candidate fixes all 20.
- Docker build and actual image preflight passed with Python 3.12.14.
- Default actual container invocation, network disabled and without production configuration, exited 78 before starting the scheduler.
- Image import smoke passed for `bot.scheduler` and `repair_content`; score collector is absent from this News image and no job executed.
- Two additional offline RSS/Atom XML checks passed using actual pinned feedparser 6.0.11. These are fixture checks, not remote source requests.
- Test/container execution used `--network none`, no production credentials, and only ephemeral test data. Docker build downloaded dependencies normally; no image was pushed or deployed.

Final artifact `10898993692` / `news02-recovery-image-evidence`, 1,280,543 bytes: SHA256 `f34ff0b4d99ed86a6eac5480be1a2b04661f189357b833512dd00ea1598c4103`. After the conversation interruption, it was downloaded again and the ZIP checksum/integrity, exact candidate marker, actual JUnit counts, image/preflight/fixture JSON and archived-source hashes were independently checked. No passing count was inferred merely from the workflow name.

Image ID: `sha256:7b61e10dbd4d0573af63537b9b10e4d648aebd7c5a8b4f17e450a62fbe733994`. Actual resolved Python base digest: `sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`. Installed versions are recorded in artifact `pip-freeze.txt`. The recipe still uses a mutable base tag and existing dependency ranges; these hashes describe the tested build, not a promise of identical future dependency resolution.

Runtime source SHA256: `bot/extract.py` = `cb3d95096b798716a6eb49e2ccdfcb79a1ac94d89ec2a557120cfccaded01b74`; preflight = `3bdbba6527287eed4ca2f4f2516fff44ef2dc5b073992ab95b7aceb762c56d63`; Dockerfile = `b5988c8c446e66f1f37eea6b94cf8ff8e273acc23e4e2abf999a05fa24e87772`.

First run `36222170898` is retained as FAILURE. Its image built successfully, but subsequent daemon inspection of an unstored base-image tag failed before runtime/suite checks. The workflow-only correction records the actual BuildKit FROM digest, adds strict pipe failure handling and asserts zero failed/error/skipped JUnit cases. Do not relabel the first attempt as accepted.

Artifacts expire after 30 days. Committed code/tests, this record and issue comments persist; the CI archive is not a permanent backup service.

## Next integration/recovery gate — not executed

Primary release owner must fresh-read issue8, latest Live Scores checkpoint and current production heads; apply only reviewed News changes without replacing newer shared files. Re-run the combined gates on that integrated code.

For the existing News service only, establish the correct backend source/approved revision and root directory, explicitly select `deploy/news/Dockerfile`, and use the guarded start command `python deploy/news/preflight.py --run`. Inspect actual environment values and legacy repair costs before enabling anything. The direct Railway update-service tool cannot change a repository source binding; do not claim otherwise or create a replacement service as a shortcut. No source-setting/deployment action is authorized from this News chat by this checkpoint.

Production acceptance still requires a genuinely running News process, bounded actual ingestion, original source dates, persisted/public fresh stories, appropriate images/categories, no duplicate/cost regressions, and unchanged Live Scores. Homepage age handling remains a separately coordinated shared-code task. Keep issue8 open; News freshness and whole-product completion remain OPEN.
