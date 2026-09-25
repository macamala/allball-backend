# NinkoSports checkpoint #7 — 25 September 2026

## Status and release boundary

Continues checkpoint #6 without resetting repositories or production data. Two bounded packages are now DEPLOYED and publicly verified: backend maintenance lifecycle/visibility guards and frontend mobile standings/match-section tabs. Whole football is NOT complete. Missing competition artwork, wider results coverage/freshness, and rich match details remain open; do not reinterpret the limited acceptance below as all-football or all-sport success.

### Exact deployed revisions

| Component | Repository / branch | Commit | Railway deployment |
|---|---|---|---|
| API | macamala/allball-backend / main | 82f139f2dd915e13a8faebc1de941046d155fbf6 | 8d144722-5399-430c-a693-fe057e09f151 — SUCCESS |
| Results worker | same backend revision | 82f139f2dd915e13a8faebc1de941046d155fbf6 | 442c1234-34e5-4d66-a20c-0773a3917b5e — SUCCESS |
| Frontend | macamala/allball-frontend / master | d0db12fe066fba328e86e9e8a80b313c20d3d2df | 7130a1c6-4bac-49a9-8bcf-bc036c2c8158 — SUCCESS |

Backend base before this turn: 8a17ffa57a2227392d3ff1211fc630f22c2981fd. Frontend base: 93dd66e65231cb36967dcfe43e6355784ae3e8fd. Both releases used normal non-force fast-forwards after tests. No direct Railway mutation, Railway Agent, new runtime service, score rewrite, database reset, or service-variable change was used. Unrelated staged Railway patch db7eb99e-400a-4e62-ba03-c10610fea2f4 remains untouched.

## 1. Backend maintenance stability — deployed

Runtime files: collector/maintenance_policy.py (new), collector/integrity.py, collector/source_native_reconcile.py, collector/canonical_collapse.py, app.py.

A retired duplicate/observation cannot become a public keeper or quarantine its existing keeper merely because its timestamp is newer. Canonical pointers, observation_only, manual_hidden, and do_not_restore restrictions are inspected independently in row/rich/slim representations. Visibility is synchronized across the physical flag, extra_json, and list_extra_json. Source revalidation, attribution, orphan restoration and collapse preserve these restrictions. Valid orphan roots can still recover; retired children cannot be promoted by automatic repair.

Historical startup integrity now requires explicit NINKO_RUN_STARTUP_INTEGRITY_BACKFILL=1 and remains disabled if NINKO_SKIP_INTEGRITY_BACKFILL=1. This prevents ordinary restarts from automatically running broad historical repair. The misplaced asynccontextmanager decorator was corrected: lifespan is the async context manager, the index-thread target is a normal synchronous function. No score is synthesized by these guards.

Repair branch: fix/maintenance-lineage-20260925. Commit chain: da80dae49021c0e12b971190076f6270817e7cf6 -> 523b6840492307c7d6da118a5f7117fdd670fd4b -> 6c396cf37714cf45241bdcaa19e1a455011fe18a -> 82f139f2dd915e13a8faebc1de941046d155fbf6.

Final exact-source regression run 36075858537, job 107886776779: **241 passed, 0 failures, 0 skipped**. Includes repeated actual FastAPI TestClient lifespan checks, source/group/score/identity/legacy-link regressions and maintenance policy cases. An intermediate test failure was a newly authored fixture missing required event_family; the fixture was corrected without weakening assertions. Initial policy run had 237 passing cases.

Final JUnit artifact 10840297100, SHA256 abc59610191e2d4389a0242d1bd2e78ef9fdc0728255e66305d76a191d7d46d3. Initial source-patch/JUnit artifact 10840380621, SHA256 c38d4f1a2a2e3209745af7ad2db086e925d63c1d4d8bc081d2e5b369514e3243. The old patch artifact alone omits the already-tracked new policy module; use the full repository revision or checkpoint source snapshot, not that patch alone, for restoration.

## 2. Mobile standings and match tabs — deployed

Restored the exact six-file mobile WIP from checkpoint #6, SHA256 80865fce8c15ccfd255face6a7975a12fb4d3c8fe097830f45a67217a49d5f1e. It was not recreated from memory. Source files: StandingsTable.jsx, standingsResponsive.css, StandingsResponsive.test.jsx, scores/MatchCentre.jsx, scores/MatchSectionTabs.jsx and scores/MatchSectionTabs.test.jsx.

Phone default football table shows position, team, played, goal difference and points without horizontal overflow. Full table remains available; it keeps all actual source statistics with sticky team names and resets horizontal scroll when returning to compact mode. Desktop retains all columns. Group switching retains the correct group. The active match tab scrolls into view within its rail, not by moving the whole page; keyboard tab navigation is supported.

Repair branch fix/mobile-standings-20260925: staging d276f873a11678d1580f2fc08d436c4a71840283, tested/published source d0db12fe066fba328e86e9e8a80b313c20d3d2df. Full run 36076221807: **151/151 frontend tests passed, 0 failed or pending**, production build passed. Browser acceptance of built bundle passed at 320, 390 and 1440 px. Artifact 10839748190, SHA256 f11b943f20bbd56a3b4aebcba2f5cb73895e8fa1e261a857c8cb2564c95b2e05. Its source.patch matches the original saved patch byte-for-byte.

Post-deployment browser acceptance against actual ninkosports.com, run 36076749961, audit branch audit/checkpoint7-production-20260925, audit commit 89a9e97ff873e536b0ee578840b933b348233573: **320/390/1440 all PASS**, 00:16:39–00:16:46 UTC on 25 September. Compact/full view, sticky names, correct A2 -> B3 -> A2 group switch, active Standings tab visibility, no page overflow or JavaScript errors. Production 320px screenshot personally inspected. Artifact 10839783577, SHA256 e32977826ce07eb9f9add991859d7e0bd614b8a75a6b79bc8c3ab321e0e63a15.

## 3. Public football acceptance after BOTH releases

Latest checked_at: **2026-09-25T00:16:44.389770+00:00** (10:16:44 Sydney).

Backend audit run 36070058979, latest job 107889585342: SUCCESS. Artifact 10840303496, SHA256 97c5dd5ebe2fcc7a1a6fa8b7ab3601419bf6dee2db00d67ceec938452fe0eac4. Extracted JSON and archive hash verified, not merely the green job status.

- Dated Sydney 25 September board: **55 football rows**, including 47 scheduled and 8 finished.
- Football-only board, all-sport board and reread after match detail all retain **55** football rows.
- **8/8 reference final scores correct**, all retained on the second board read, correct finished status and groups.
- Andorra–Malta keeper ninko-evt-6d8bf3121dc158b647e1 returns **1–2 finished**. Legacy alias ninko-evt-86345b6cb47a7c4b8524 remains functional.
- Desktop/mobile main board both 55 rows, correct Nations League group table and switching, no tested page/match overflow or JS errors.

Important attribution: checkpoint #6's 7/8 failure had already recovered to 8/8 in the fresh PRE-release snapshot at 23:55:32 UTC. Do not claim the new guard created that recovery. It addresses a demonstrated recurrence path. Post-backend acceptance at 00:10:05 and post-both acceptance at 00:16:44 remained 8/8. Finite repeated checks and one deployment cycle do not prove that future data can never regress.

This is a reference-set regression test, NOT proof that all 55 fixtures have current/correct results or that every worldwide fixture is present. The 47 scheduled rows need time/freshness/coverage checks, especially when kickoffs are in the past. In-play football score/goal-update latency was not independently verified in this pass; do not call all LIVE behavior closed.

## 4. Next priority: artwork correction — diagnosed, NOT implemented

Actual browser still shows 16 competition-logo fallback headers. These are not merely null API fields: nonempty URLs are failing. Some below-fold images are lazy-loaded, so 16 is an observed set, not a guarantee that all other artwork is correct.

Read-only official FotMob board/CDN diagnostics ran at 00:16:15 UTC, same production audit run 36076749961. Both date boards (20260924 and 20260925) returned HTTP 200 JSON. Fifteen wrong group/season badge IDs returned HTTP 403 XML; all nine corresponding actual parent/primary competition IDs returned HTTP 200 and real PNG bytes. Artifact 10840675645, SHA256 ebe641b868e60f24463b49d9adc97f3cdb53700d23a2e57f6e36e15178c0c696, contains upstream nodes, request status, image hashes and real PNGs.

Verified relationships from the SAME upstream league nodes (not name guesses):

| Existing bad badge ID | Actual parent/primary badge ID | Scope |
|---|---|---|
| 914609 | 114 | Friendlies |
| 915708 | 489 | Club Friendlies |
| 943878, 943880, 943881, 943882, 943883 | 10608 | AFCON qualifying groups C/E/F/G/H |
| 941120, 941122 | 9821 | CONCACAF Nations League A1/B1 |
| 946196 | 9091 | Chile Cup |
| 897723, 897724 | 10437 | EURO U21 qualifying A/I |
| 943993 | 329 | Gulf Cup B |
| 938187 | 128 | Israel Leumit |
| 943368 | 533 | Nigeria NPFL |

Further source inspection at deployed backend82f: collector/adapters_fotmob.py already prefers parentLeagueId -> primaryId -> id in _league_logo and preserves these fields in _board_league. Do not replace this correct rule with a hardcoded giant ID map. match_to_event emits competition_logo with that rule. collector/fotmob_crosswalk.py::_fill_identity_assets ONLY fills competition_logo when absent; it does NOT replace an existing wrong nonempty URL. That is a concrete repair gap, but serializer/merge precedence and any other writer still need tracing before release.

Proposed bounded next package: source-native artwork-only replacement where exact event identity and the same upstream node prove the correct parent badge; retain source competition/group IDs for fixtures and tables. Preserve correct alternate-provider logos and manual overrides. Test wrong-group-URL correction, unknown/unrelated URL preservation, no event/status/score/group/alias changes, rich/slim synchronization and cache invalidation. Verify real PNG loading across the full scrolled board after publication. Do not mark closed because URLs merely exist.

Also seen in the saved all-sport sidebar: some NHL names stringify a dictionary, e.g. {'default': 'Hurricanes'}. Record this secondary issue, but finish football priorities first.

## 5. Resume and persistence rules

This record lives on backend checkpoint/recovery-20260925-07, not a production branch. Backend issue #6 retains the chronological evidence and release comments. All released code and tests are committed to the exact revisions above. The checkpoint snapshot workflow is read-only: it packages exact changed-source overlays plus full binary-capable git patches and a per-file SHA256 manifest for both releases. It does not deploy, mutate production, or make recurring requests.

The original checkpoint #6 Library backup /NinkoSports/Checkpoints/NinkoSports_Checkpoint_6_Backup.zip was recovered and verified (SHA256 f77a93bae634800ab7d1299975c1d248c69f43bf6b8d8cc6e84d63ace12b3fb6). No new Library upload has been performed at this checkpoint record. Do not claim otherwise. Conversation backup creation/download and GitHub persistence are separate from Library upload.

Before new writes, reread current main/master and compare to recorded releases; do not overwrite a newer user's change. Tests and status must be checked again before any next release. Never clear a score or restore an alias just to increase fixture count. No Railway Agent unless indispensable and explicitly bounded. Leave staged patch db7eb99e-400a-4e62-ba03-c10610fea2f4 alone.

Rollback is a scoped forward revert of the affected runtime changes, tested first; never a force-reset or database rollback. Preserve earlier source-priority, score-integrity, canonical aliases, group and artwork work. Archived acceptance is historical evidence, not a substitute for fresh production checks on resume.
