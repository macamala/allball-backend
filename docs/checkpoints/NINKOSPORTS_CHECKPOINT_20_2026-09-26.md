# NinkoSports checkpoint 20 — 26 September 2026

## Current state

**C20 collector code is DEPLOYED; one native collision is verified repaired in production. Full result coverage and full public/mobile acceptance remain OPEN.** This is the current source/deployment handoff, superseding C19 as the backend version, not a claim that all football results/details are complete. User reiterated that results are missing. Do not dismiss that report because a sampled board displayed some correct finals.

User also requires no TinyFish pictures/screenshots in chat and no extra plugin steps for them; avoid browser runs that display unnecessary widgets, prefer text-only public reads. No Railway Agent was used. The primary Live Scores chat remains sole merge/deploy owner; News03 stays isolated for later review.

## Exact source and deployments

- Backend main: **ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726**, also on `fix/football-result-queue-c20-20260926`.
- Frontend master: **7183733e5eed7dae566aeaf1632fc757c547cc4c**, unchanged from combined C19.
- API deployment **b9d2539c-b8cc-49b9-bd31-68e39bb50039** SUCCESS at2026-09-26T07:42:08.185Z, matching backend SHA.
- Results-worker deployment **98ceeeb2-9762-4686-81da-fc9e0c44521a** SUCCESS at2026-09-26T07:41:51.154Z, matching backend SHA.
- Both production Git heads were freshly read back after deployment and still matched these versions.

Backend Railway project17f6ebff-0f6b-42dd-be86-35ca9ca40301, environmentcb27d851-9198-47c8-a733-8356e8b6cf63; APIservicec08822c6-e602-4f32-a2bc-87aedbbe9b05; workerservice2c89eecf-b094-428a-8f7c-9642605a6baa.

Pre-release source is preserved on `rollback/pre-c20-results-20260926` at9db4b7cd3b83aac57981cd2769fec089d7786b1f. Preflight was committed BEFORE production ref update: **4b78fc0dc658d539a00b9f5976978ddef8f9daf1**, `docs/checkpoints/C20_RESULTS_RELEASE_PREFLIGHT_2026-09-26.md`, on this audit branch. It records detailed proof, hashes, review failures and rollback scope. These are source records, NOT a DB backup.

## Runtime changes

Five collector files only: football_board_priority.py, football_board_refresh.py, football_fixture_linkage.py, football_source_roots.py and new football_native_scope.py. Three new test files, one inert patch record and one offline CI workflow accompany them. Exact compare against C19: ten files, ahead10/behind0.

1. Newly observed live/final source IDs ahead of the saved discovery cursor can use up to2of the existing maximum8 priority slots, instead of waiting behind a long future-fixture page. Existing changed-result slots, normal coverage interleaving, receipts/backoff, total/time budget and validation remain. No new source request or scheduler. The lane does not guarantee immediate ingestion for every unknown ID, especially IDs already passed by the cursor; this is a bounded scheduling improvement, not a global latency SLA.
2. An exact owned native match/team identity may bridge an explicit ungrouped canonical parent and its source leaf. Groups, copied provider IDs, conflicting team IDs, old finals, manual restrictions and independent child trees are not blanket-authorized.
3. Native women's duplicates under known non-women's domestic buckets require exact owned oriented team IDs, native match/leaf, confirmed incoming women's category and matching explicit native/catalog/registry countries. No inference from missing old-league gender, no permissive empty-country fallback. Spain/Italy/Germany cases are covered in tests and captured-source replay; see production limitations below.
4. Linkage revision5 lets previous deferred entries receive normal bounded revalidation once. Unproven conflicts are retained. Original physical rows, IDs and fingerprints remain; proven duplicate rows become old-link aliases rather than being deleted.

No News runtime, frontend, shared API bootstrap, database/schema, root deployment recipe, credentials, service settings or worker ownership/draining changes. Combined C19 News01/02 and C18 post-match recovery remain present.

## Completed test gate

Final workflow **36227263924**, exact tested candidateba0b70017fa2d96717ce4c4f8e40e2ac95ec3726: backend and retained-frontend jobs terminalSUCCESS.

- **1200 selected combined backend tests, zero failures/errors/skips**:1160 retained C19 cases plus40 C20 cases.
- Five selected new cases fail by assertion on unchanged deployed C19, zero errors. Candidate resolves these reproductions. These use controlled test data, not claims about five actual final scores.
- **329 full frontend tests, zero failures/errors/skips**, production-target build,24 polling-policy and6 request-gate checks passed against the unchanged frontend.
- Actual dependency-compatible Docker image; test execution network-disabled with ephemeral data, no production credentials. Not every unrelated backend repository test was run.

Actual downloaded and independently checked evidence:
- Backend artifact10901415327: ZIP SHA256 **568c0ecfa3517ccb209ac64d2971c4caed2ad8bf35b65132cecf285e389e0d28**.
- Frontend artifact10900169610: ZIP SHA256 **563246d6a3ba7a8a01f10dcfe8a62573ac13f047d5043a1fae0c07ae68801e98**.
- Final runtime/test source patch SHA256 **8705ed35ddaeccda9e1dcbe63c8a1f9e38f13f5f1221e055ab677346857c573e**.

ZIP integrity, actual baseline and final JUnit, candidate marker and eight source/test hashes were checked. After interruption the ZIP hashes and JUnit1200/329/5baseline-failures were checked again. Artifacts have30-day retention, not permanent backups. Committed code/tests/checkpoint remain.

Earlier gate36226932874 passed the earlier selection. Further review found missing old-league metadata and the empty-country default issue; corrected country requirements and extra negatives, then ran the final full gate. No earlier draft was deployed. Historical native scheduled cases5882299/5977767/6040018 replayed unchanged against synthetic duplicate rows and preserved original kickoff/status/score/participants; that is NOT proof those real production rows have all been reconciled. The preflight contains exact replay and transport-correction history.

## Actual production result so far

NEW worker log at **2026-09-26T07:41:57.097510635Z**:

`FOOTBALL_SOURCE_ROOT_LINK keeper=ninko-evt-a65e5b0f697618a40473 source=1000014161 aliases=['ninko-evt-48ee659f22a82cb68ef9']`

This is the Colombia parent274/leaf1000001696 collision (Chico/Pasto source identity) previously blocked by two roots. The normal source acceptance path now links the old source-native bucket to the existing canonical keeper. No final-score number is claimed here: no usable fresh public response body was obtained. Synthetic3-0 used by a test must NEVER be described as this match's actual result.

Comparable source-day25 backlog:
- Old deployment3b49e467-8ce2-4eb2-a10e-158fc59dc574 at07:40:57.390365487Z: day20260925,102seen,**3deferred**.
- New deployment at07:43:30.772343671Z: same source day,102seen,**2deferred**.

Thus one actual conflict is resolved, not all missing results. These are native UTC source-day counters, not Sydney-local board totals or a count of missing finals.

**Current source-day26 remains12deferred/449seen**, including the post-release07:47:28.885545878Z observation. Do not claim12to0,12to11, or all results fixed. Source-day27 last verified PRE-release at07:40:57 had20deferred/283seen; C20 production repair of all future women's rows is not yet verified in this record. Older28deferred snapshots must not be substituted as the current baseline.

New worker continues normal persistence and the retained C18 enrichment lane. At07:46:17.581281363Z it attempted2details and returned20 J.League3 table rows;07:47:30.268096893Z returned14 Norway2div table rows. Other observed table attempts returned0 (AsianGames); those are not marked complete.

At07:42:50 the existing60-second watchdog printed a stack currently insideSQLAlchemy/db.get in consume_board_match. Persistence continued at07:42:54 and subsequent cycles ran. This is not proof of a new crash, but long-cycle/database timing remains a performance gap. Do not promise a measured live delay or pretend this diagnostic never occurred.

NEW API logs at07:48:34 confirm HTTP200 for BOTH the old alias and canonical `/sports-data/matches/{id}/score` routes. This proves endpoint responses, NOT equality of unread response bodies or final score correctness. Ordinary favicon404 is not a missing-match error.

## Public QA limits

One bounded TinyFish normal public board visit used13steps, no vault/profile/login, screenshots/recording/capture disabled. It reported19visibleFTrows with nonempty scores and two detail headers matching the board, but found no demonstrable empty-score row. Its unsupported claims of exhaustive469-match correctness and no local timezone conversion are NOT accepted. Existing frontend uses local-date/time logic; no controlled timezone test occurred. User's missing-results report remains open.

Subsequent checks were text-only. Public API extraction, including compact score routes, did not yield usable bodies; body/pre selectors did not match. Web access and a direct download attempt also failed; no partial snippet was upgraded to a complete response. No images were sent manually and no further browser session was started after the first run. No blocked production-audit workflow was retried or bypassed.

No new complete source-vs-public fixture sweep,912-ID retention sweep, all-final comparison, actual1440/390/320 production browser test or global logo/flag check is claimed in C20. Those remain required. Old successful C17/C19 results are historical only.

## Remaining work and safe continuation

1. Resolve the remaining source-day26 conflicts from exact source IDs, orientation, kickoff, category and score, not by widening all tolerances or hiding inconvenient rows. Known remaining classes include NWSL5161651 and USL5109962 with other roots carrying unequal/reversed pairs or inherited IDs; Mexico5898735 pair mismatch; Chile6162931/6162932 kickoff shifts of9000seconds. Some are upcoming fixtures, not missing completed results. HistoricalUSL300second/LaLiga7200second differences and independent trees require separate evidence.
2. Recheck source-day27 after normal worker rotation to confirm the tested women's legacy bridges actually apply. Do not count offline replay as production recovery.
3. Continue source-only match detail, incomplete/group tables, old Myanmar/Sligo links, possible Waterford duplicates, full transfers/fees/squads, global scorers/brackets/assets and18 previously unclassified examples only after fresh evidence. Not closed by this queue fix.
4. Complete actual public score/alias/coverage and desktop/mobile verification through available authorized tools without pictures or unnecessary plugin interaction for the user. Preserve explicit evidence limitations.

News03 latest known issue8 comment5844137533 is on separate branch `news/coverage-originality-20260926-03`: candidatef08633d0221fbf9d9850f291dbab4ffe927c11c7, checkpointc3bdb1ccf39373cbb5a94a7a5964ab954f466e33. NOT merged/deployed in C20. Existing News worker activation, request-ledger/config/DB/single-owner proof and old May/June homepage selection remain as C19 blockers.

For restart/recovery: fresh-read this record, latest issues6/8 and actual main/master first. Do NOT reapply C18/News01/02/C20 patches over current source or restore an older snapshot. All C20 runtime is committed. If rollback is necessary, use a reviewed forward revert limited to five C20 collector files, preserving DB rows and alias pointers and C19/C18/C17 guards. Do not reverse the successful row links or reset the database.

No Railway Agent, new subscription/service, configuration changes, manual score edits, data deletion/reset, force push or unrelated staged environment change was used. Keep issues6/8 open; this is a deployed bounded repair with explicitly incomplete coverage acceptance.
