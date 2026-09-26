# Combined release 19 preflight — 26 September 2026

User explicitly authorized this primary chat as the sole Live Scores and News integration/deploy owner. This is a PRE-FLIGHT, not final production acceptance. Latest issue6/8 comments, C17 accepted state, C18 review WIP, both News checkpoints and current production refs were read first. No older source snapshot replaces newer code.

## Exact source and rollback

Current production backend main: cf192f22da637b9b54495cd5fc2ba238abbfbee3. Current frontend master: 9a9d1cc996f746a63d4716043b849a7b12e57538. Both are preserved on rollback/pre-combined-20260926 in their respective repositories. These are source snapshots, NOT database backups and NOT permission to force-reset production.

Tested combined backend: **9db4b7cd3b83aac57981cd2769fec089d7786b1f**, integration/c18-news-20260926, normal ahead5/behind0. Test source retains exact News02 candidate24714028a8e3a1e3b6ac679bd6db703beeddffea ancestry and applies SHA-verified C18 original+review patches. Thirteen changed files: five modified/new score runtime files? Exact runtime scope is bot/extract.py; collector/detail_enrich.py, football_detail_retry.py, football_enrichment_cycle.py and provider.py; new deploy/news/Dockerfile and preflight.py; four tests and two branch-scoped workflows. The collector directory has exactly four changed runtime files. No API bootstrap/schema/DB migration/root deployment recipe changes.

Tested combined frontend: **7183733e5eed7dae566aeaf1632fc757c547cc4c**, same isolated branch name, normal ahead11/behind0. Retains exact News01 candidate808f5133db9945c8036992f3b846bd97a62a6cf8 ancestry plus SHA-verified C18 patches. Fourteen files: ArticlePage/newsArticleState and MatchPage/matchRefresh/matchRequestGate, tests and audit/gates. Homepage, global CSS, shared api.js and navigation are not overwritten.

Every C18 changed file on both candidate archives matched the v2 restoration manifest byte count/SHA256. News02 extract/preflight/Dockerfile remained byte-identical to the separately verified News02 source. Full integrated patches were reviewed. All C17 gender/exact-ID/manual-hidden/retired/source/score/delta/scheduler guards retained.

Rollback, only if required after diagnosis: new forward revert limited to this release's runtime differences relative to the preserved refs. Never delete/reset DB, force-push, revert correct fixture results, remove C17 guards or use old unreviewed full files. Candidate code can be rolled back independently of the dormant News deployment recipe. No automatic rollback is installed.

## Actual combined gates — not reused isolated passes

Backend run36224259466 SUCCESS: **1160 selected combined tests, zero failures/errors/skips**, including retained football, News and all41 C18 cases. Real dependencies installed through the reviewed Python News Docker recipe. Tests executed with network disabled and ephemeral test data. Actual image preflight passed; default unconfigured command exited78 before scheduler execution; module import smoke passed without starting ingestion. No AI/provider or production DB call.
Artifact10900226165, ZIP SHA25600c03f964bdb7524704e44ecd41b71b162dc4522ec0b252a2bef333607f042c8. Downloaded, integrity checked, JUnit parsed, candidate archive and per-file hashes checked independently. First workflow version referenced a wrong review-test filename; corrected to actual tests/test_c18_review_safety.py before this successful run. Do not treat that first attempt as passing.

Frontend run36224285554 all stepsSUCCESS: **329 complete frontend tests, zero failures/errors/skips**, including all5 C18 React cases;24 Node polling-policy and6 ownership cases; local fixture News browser journeys at1440/390/320; both isolated fixture build and production-API-target build passed. Those browser journeys used controlled LOCAL data, not production acceptance.
Artifact10900286079, ZIP SHA256f1c1acd8fda862fa99f04033212bfca32877e50819e192cd843db45e9a7269cb. Downloaded/ZIP checked, actual JUnit and browser JSON read. This resolves the earlier C18 dependency/test execution blocker for this integrated version.

Earlier blocked broad C18 baseline workflow was not retried. Current legitimate gate is offline combined-source testing, no production requests/secrets. Actual public browser inspection used the newly user-connected TinyFish without credentials.

## Pre-release infrastructure and public observations

API deployment7a1b9c48-d901-49b9-afbe-fe5aa7d16c4b and results-worker895c2984-96b8-4bf5-8b3a-5fbbbeca68ad SUCCESS at exact current backend SHA. Both service configs show backend/main and their existing uvicorn/collector.worker commands. Frontend99ecb805-db14-4af8-9316-3074aeaa5a22 SUCCESS at exact current frontend SHA; config shows frontend/master, existing npm build/start. No config changes made.

Unrelated staged Railway patchdb7eb99e-400a-4e62-ba03-c10610fea2f4 targets audit-scheduler-lease and remains untouched. Do NOT accept environment-wide staged changes.

TinyFish bounded public session22f94c93-74eb-49e0-a8ff-bbc75f073006 completed17steps/110sec, no profile/vault/logins. Jamaica–Guatemala ninko-evt-7e1e5af03b232f24ef0e observedFT3-2, five-goal timeline, partially visible lineups; statistics tab existed but actual stat values were not enumerated, so not full statistics proof. News article nottingham-forest-stadium-expansion-approved-so-what-now loaded body/stadium image and original19Sept2026 date. TinyFish could NOT configure1440/390 widths; no mobile proof from that run. Separate fetch_content attempts returned no usable API body and are not data proof.

## News activation explicitly BLOCKED pending safe configuration/access

Existing hopeful-blessing servicebe857be7-a029-4663-81c7-bcde75efc482 was inspected directly. Latest deployment79f761eb-3afc-457a-b222-15c1a5c63088 reportsSUCCESS but build shows allball-frontend/npm/Vite and runtime repeats python: command not found. Config has no source stanza, so correct repository/branch/root remain unverified. Actual variable read returns valuesRedacted=true. DATABASE_URL and flag names exist, but values, DB identity and other active ingestion process ownership cannot be confirmed. No access workaround or credential extraction is authorized.

Source review independently confirms startup immediately calls job(); repair_summary_only() runs BEFORE new ingestion (defaults page_size80,max_pages8,max_rewrite8), then ingestion(use_ai=True), index_missing loop and repair_contaminated(). max_ai_articles counts accepted rewrites, not all attempts. _ai_story may request a second rewrite for length, while _call_openai can make a second HTTP attempt on429. No hard global request/dollar cap is added by News02. This is why NEWS_LEGACY_REPAIR_ACK must NOT be set blindly.

Safe release decision: merge/deploy the tested application code, but **do not change, restart or activate News service** until source/root, real non-secret control values, DB and single-owner process are verified and costs/legacy writes explicitly bounded. New recipe is dormant unless selected; no root recipe affects API/results-worker. No Railway Agent, new service, paid subscription, variable overwrite or secret disclosure performed.

Actual source→DB→fresh public News acceptance remains BLOCKED. Older homepageMay/June selection and dates are unchanged/unresolved. Never change original dates to simulate freshness.

## Release steps

Fresh-read heads immediately before nonforce updates. Backend main to exact9db4 candidate, verify both exact matching terminal Railway deployments. Frontend master to exact718 candidate, verify exact matching terminal deployment. Then execute bounded actual public desktop/mobile views for scores, match details/refresh, standings, logos and article open; record any remaining coverage defect, not just SUCCESS. Save final combined checkpoint and update both issues6/8 with exact outcomes. Global football and News completeness remains open.
