# NinkoSports checkpoint 18 — WIP, NOT DEPLOYED

## Current status

User reports that some matches played today contain no details and requires an automatic durable fix. This became the first priority over further transfers/brackets work. No exact match examples were supplied. Fresh production API inspection did not succeed in this attempt, so none of today's specific missing matches is claimed repaired.

**Last completed and accepted production remains checkpoint 17.** Fresh GitHub reads at the beginning verified backend main `cf192f22da637b9b54495cd5fc2ba238abbfbee3` and frontend master `9a9d1cc996f746a63d4716043b849a7b12e57538`. This pass did not move either production ref or change Railway services/settings, database records, scores, source restrictions or visibility. No Railway Agent, new scheduler, reset or force push.

## Confirmed code defects and local draft

Existing finished detail had a seven-day positive cache even for a response with only venue/history; missing statistics/incidents/lineups did not distinguish it from complete detail. The existing automatic enrichment window ended 12 hours after kickoff. MatchPage stopped detail polling at finished status. The worker always offered the first slot to live matches and accepted only a FotMob identity, so a slow live request could consume the entire six-second budget and leave recent finals or already-linked alternative providers waiting.

The local draft implements:

- Automatic football final-detail recovery through 72 hours measured from verified kickoff. Positive cache caps are five minutes during the first 24 hours and 15 minutes through 72 hours. Recent negative/empty attempts have a two-minute cap. Existing host backoffs remain authoritative. Historical known-partial detail has a one-hour on-demand cap. These are policies, not production delay guarantees.
- First-slot rotation across live/final/upcoming, still under the existing owner lease, 30-second job cadence, maximum six-second fetch budget and two-attempt limit. A persisted bounded candidate cursor prevents a busy window permanently hiding later event IDs. Additional urgent live candidates remain bounded. Existing retired/manual-hidden/canonical/source rules remain.
- Already-linked supported football IDs from FotMob, Sofascore and OpenLigaDB can enter the existing validated detail path. No new provider discovery or name-based identity guesses.
- Transport/parser failure handled per football family without erasing good stored sections or aborting all other families. Internal attempt state distinguishes last attempt from last success and counts actual stored incidents, statistics and starters. Only exception class names are recorded; no private messages/URLs. The state is excluded from public payloads. Cache-only reads do not renew upstream timestamps.
- Visible recent finished football pages continue rich-detail polling every 60 seconds, without restarting fast score polling or a live clock. Slow detail requests do not overlap; route-generation and last-good-data protections remain. Old finals, nonplayed terminal states and other sports retain their terminal policy.

No guarantee is made that an upstream supplies every section. Missing source-only season identities and genuinely absent upstream content require separate verified coverage work.

## Exact saved patches — these are inert archive text, not applied runtime files

All parts are on `audit/football-detail-c18-20260926`, directory `audit/c18-handoff/`, complete corrected archive revision `39c1c7a6c8f3a5daed58dc681bbde99c46a3e436`.

Concatenate backend.0.txt, backend.1.txt, backend.2.txt, backend.3.txt in numeric order with NO extra separators and NO stripping of whitespace. frontend.0.txt is already the entire frontend patch.

| Part | Bytes | Git blob SHA |
| --- | ---: | --- |
| backend.0.txt | 8136 | 9e5240bb796d15b8e747fec0c08077db4dc72c96 |
| backend.1.txt | 9114 | 883e7eb10aa1c2ff4c7bdb275abc71ee414e3ba0 |
| backend.2.txt | 8079 | 87d3359a0f60679ebb2b93b9c6f034e48609f8e3 |
| backend.3.txt | 8856 | 9857c3929b6c7ef1749324386bbd38c06312d1bf |
| frontend.0.txt | 10835 | 1b65716668a08977cdfea38dbd2a8aa591b0ffa9 |

All remote blob hashes and sizes match the actual local parts. Original backend part0 had one extra leading space before a diff header; revision39c1c7a corrects only that transport error and returns the exact expected blob hash. Use corrected revision, not the earlier corrupt part0.

Combined backend patch:34185 bytes, SHA256 `954b4ec7ce3b2906c58de38476e043772766e8970656d04a87c0127544d3bd18`.
Frontend patch:10835 bytes, SHA256 `7cc9f19ed92bc02786160639f41dbf2adaf814a83611dedf8877965e03730ed8`.

Backend changed files: collector/detail_enrich.py, collector/football_detail_retry.py (new), collector/football_enrichment_cycle.py, collector/provider.py, tests/test_c18_finished_detail_recovery.py (new,27 cases).
Frontend changed files: src/lib/matchRefresh.js (new), src/pages/MatchPage.jsx, src/pages/MatchFinalRecovery.test.jsx (new,3 cases), audit/c18_match_refresh_policy.mjs (new,24 executable policy cases).

The conversation also has a generated ZIP `NinkoSports_C18_Finished_Match_Recovery_WIP.zip` (17320 bytes), SHA256 `19d61d0adcc5154af5d659f4c297db08a983bd2eadd4e421d1f5ed07f0554f67`, containing README, both patches, per-file manifest, test summary and native replay summary. It is not a database backup or a Library upload.

## Actual tests — not a green release gate

- Initial new reproductions on unmodified C17:11 failed,1 passed.
- Final focused backend suite:86 passed, zero failures/errors/skips. Includes post-match retry, original rich detail, C15 tables, owner shutdown and C17 category/exact-ID tests.
- Full attempted retained backend selection:930 passed,12 failed,8 collection errors. The actual failure records show8 failed cases and8 collection errors missing feedparser, plus4 failed cases missing psycopg2. No stubs were used. Local pytest9.0.2 also differs from the project's specified less-than9 environment. Full gate is NOT passed.
- Exact JavaScript polling policy executed in Node:24 passed,0 failed. Three new React integration cases are written but not executed. npm ci --offline returned ENOTCACHED, so the complete frontend suite, production build and real browser acceptance were NOT run.
- Python compile checks and git diff --check passed. Both patches passed reverse apply-check on edited trees and forward apply-check/application on isolated exact-base files. Every resulting file matched the per-file manifest.
- Offline replay of actual captured native Sligo5100971 response into an isolated partial cache filled37 statistics,15 incidents and11 starters per side, preserved event identity and score, and made only one source call including immediate second read. This is NOT a fresh production repair. Source artifact10898052619, member c13-public/native-sligo.json SHA256 `c00db2f10eeecd295a42d5bf3a2ac4a0bef3686383331d6297a26bc087f75cbe`. The initial replay harness assumed an envelope and raised KeyError; inspecting the raw file corrected that harness assumption, not the runtime data.

Local evidence paths, if runtime survives: /mnt/data/c18/focused-tests.xml, retained-tests.xml, reproduction-before.log, frontend-policy-tests.log, native-replay.json, manifest.json. Do not confuse930 passing cases with an overall pass or24 Node policy cases with frontend acceptance.

## Blockers and authorized continuation

A new read-only baseline workflow creation was blocked by a safety check. No substitute workflow, alternate trigger or production release was attempted. Requirements installation could not complete in this environment. Do not bypass that blocked action. This audit branch contains only saved text patches/documentation, not a runnable C18 deployment.

Resume by fresh-reading current production refs and this record, restore exact patches only in isolated matching C17 checkouts, verify hashes, and review them. Complete backend tests with real required dependencies, all frontend tests/build, and actual 1440/390/320 browser checks through an authorized test path. Obtain real production examples of today's missing details and compare upstream identity/coverage before claiming specific matches fixed. Save a release preflight and only then consider any production update. Keep C17 category/results/source/retirement/manual guards and worker draining15.

The earlier global backlog is still OPEN: source-only season MatchCentres, missing/group tables, old Myanmar/Sligo links, complete transfers/fees/squads, global scorers/brackets/assets,18 prior unclassified matches, other sports/news. This WIP does not supersede C17 as a completed production checkpoint.
