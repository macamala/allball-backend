# NinkoSports combined release checkpoint 19 — 26 September 2026

## Current state and ownership

**Combined application code DEPLOYED. News ingestion activation BLOCKED. Production browser acceptance PARTIAL, not a whole-product signoff.** This primary chat remains the sole merge/deploy owner for Live Scores and News. Issues6 and8 remain open. This checkpoint supersedes C17/C18-WIP as the current source/deployment state, but does not erase their evidence or declare all football/news complete.

The user explicitly requested integration of latest Live Scores plus News01/02, joint tests rather than reusing separate passes, bounded spending, preservation of production data/guards, direct Railway investigation first, and a safe partial release if News activation cannot be verified. That boundary was retained.

## Exact deployed source and services

| Component | Deployed commit | Actual deployment |
| --- | --- | --- |
| Backend API | `9db4b7cd3b83aac57981cd2769fec089d7786b1f` | `a962e707-916f-42ac-9988-30f9175eb94c` SUCCESS at2026-09-26T06:46:45.578Z |
| Results worker | same backend commit | `3b49e467-8ce2-4eb2-a10e-158fc59dc574` SUCCESS at2026-09-26T06:46:32.722Z |
| Frontend | `7183733e5eed7dae566aeaf1632fc757c547cc4c` | `eb8f55ff-64b5-47da-9d5f-99ef218df5ef` SUCCESS at2026-09-26T06:48:57.525Z |

Backend repository macamala/allball-backend main; frontend macamala/allball-frontend master. Both release candidates also remain on integration/c18-news-20260926 in their respective repositories. Production updates were nonforce fast-forwards, never resets.

Pre-release refs are preserved on rollback/pre-combined-20260926:
- Backend `cf192f22da637b9b54495cd5fc2ba238abbfbee3`.
- Frontend `9a9d1cc996f746a63d4716043b849a7b12e57538`.

Release preflight was saved BEFORE main/master updates in this audit branch, document NINKOSPORTS_COMBINED_19_PREFLIGHT_2026-09-26.md at e8a28d43ec59a31e1e2ec9448f5827db405f2838. These branches/documents are source rollback records, **not DB backups**. No rollback was executed. If rollback becomes necessary, diagnose first and create a forward revert limited to this release's runtime changes, preserving current data and all C17 protections. Never force-reset or reapply old full-file snapshots.

## What was integrated

### Live Scores C18 reviewed recovery

The original and additive C18 v2 patches were restored from checkpoint0a4cbd967764247db2458a4f17642d99e2e65a22 with exact SHA checks. Every resulting changed file on BOTH archived tested candidates matched the prior per-file byte/SHA256 manifest.

Backend runtime scope: collector/detail_enrich.py, football_detail_retry.py, football_enrichment_cycle.py and provider.py. Recent played finals remain eligible for bounded recovery through72h from verified kickoff; shortened partial/empty retry caching, fair first-slot scheduling under the existing owner lease/cadence/time budget, already-linked supported detail families, per-family/component failure isolation, retained good partial sections and stored-match identity checks even for initially empty caches. Nonplayed records are excluded from recovery slots, not deleted/hidden from the board. Private retry metadata stays out of public payloads.

Frontend scope: MatchPage plus matchRefresh/matchRequestGate. Visible recent finished football pages keep60-second rich-detail polling without restarting fast score polling or a live clock; route-token ownership prevents initial/poll overlaps and stale-route release. Five new React integration cases now actually ran in the full combined suite.

This does not create unavailable upstream lineups, verify every source-only season identity or guarantee a72h completion/delay. Existing scores, gender/category IDs, exact player/club IDs, manual-hidden/retired/source rules and scheduler protections remain.

### News01 frontend

Exact tested News01 candidate808f5133db9945c8036992f3b846bd97a62a6cf8 remains an ancestor of the integrated frontend; no stale shared files overwrite Live Scores. ArticlePage/newsArticleState enforce opened slug/title identity, bounded loading/error handling, targeted retry, empty-body handling and prevention of late responses showing a different article. Homepage, navigation, global CSS and shared api.js were not changed.

### News02 backend

Exact tested News02 candidate24714028a8e3a1e3b6ac679bd6db703beeddffea remains an ancestor of the integrated backend. bot/extract.py prioritizes original publication timestamps over later modification timestamps. The new nested deploy/news/Dockerfile and guarded preflight are present in source, **but are NOT selected or running on hopeful-blessing**. Existing News02 runtime files remained byte-identical to the separately downloaded verified candidate. No historical publication dates were rewritten.

Exact integrated compare: backend ahead5/behind0 from old main,13 changed files (7 runtime/deployment files,4 tests,2 isolated workflows); frontend ahead11/behind0,14 files including runtime/tests/audits/workflows. The preflight's tentative phrase about five score files should be read as four collector runtime files; this list is definitive. No database/schema migration, API bootstrap or root deployment recipe change.

## Joint tests actually completed on integrated source

| Gate | Actual result | Evidence |
| --- | --- | --- |
| Backend combined retained selection | **1160 passed,0 failed,0 errors,0 skipped** | run36224259466, artifact10900226165 |
| Frontend complete suite | **329 passed,0 failed,0 errors,0 skipped** | run36224285554, artifact10900286079 |
| C18 JavaScript policies |24 polling +6 request-ownership checks passed | frontend artifact logs |
| News responsive Chromium with LOCAL fixtures |1440/390/320 passed reader error/retry, next-article identity and empty-response flows | news-browser.json and screenshots |
| Builds | local-fixture and production-API-target frontend builds passed | frontend run |
| Real Python News container | build/preflight/import smoke passed; default unconfigured execution exits78 BEFORE scheduler | backend artifact |

Backend suite includes retained football, existing News,62 News02 cases and41 C18 cases. It is a selected combined backend suite, not every unrelated repository test. Container test execution used network disabled and ephemeral data; Docker dependency installation during build was normal. No real AI/News ingestion/production database call occurred in the gates.

Downloaded ZIP SHA256 values were independently verified, ZIP integrity checked, actual JUnit and candidate markers parsed, source/per-file hashes matched and representative mobile screenshot inspected:
- Backend artifact10900226165: `00c03f964bdb7524704e44ecd41b71b162dc4522ec0b252a2bef333607f042c8`.
- Frontend artifact10900286079: `f1c1acd8fda862fa99f04033212bfca32877e50819e192cd843db45e9a7269cb`.

Initial backend workflow referenced the wrong review-test filename; it was corrected to tests/test_c18_review_safety.py. Only corrected run36224259466 is the accepted backend gate. Earlier C18 missing-dependency runs remain failed/incomplete historically, not retroactively relabeled passed. Artifacts retain30days; source/tests/checkpoints remain in GitHub. No permanent artifact or DB-backup service is claimed.

## Actual post-deploy runtime and website observations

### Worker/API runtime

Direct logs from NEW results deployment show the scheduler processing jobs and persisting events. At2026-09-26T06:49:02.078746097Z:
FOOTBALL_CURRENT_ENRICHMENT reported2detail attempts, IDs ninko-evt-ab94a8b7261b97dea191 and ninko-evt-44803592b9d4516d1611, table football-gulf-cup-grp-b with4rows,998candidates. This proves the new recovery path executes in the deployed worker, **not that all missing sections are filled or every attempt succeeded**. Logs also retain source_identity_conflict rejections; do not disable these guards to improve counts. INFO messages on stderr are tagged error by Railway and are not automatically application exceptions.

New API logs returnHTTP200 for the sampled Jamaica–Guatemala match and its standings, and article/detail/comment routes. This is stronger than deploymentSUCCESS alone, but not broad coverage or freshness proof.

### Actual public browser, no private accounts

TinyFish was confirmed connected. Three bounded public sessions used no profile/vault, logins, passwords or administrator sites;44total observed steps (17+23+4), no subscription/top-up/auto-reload change. No Railway Agent was used.

Pre-release session22f94c93-74eb-49e0-a8ff-bbc75f073006 visited the match and article. Post-release session80ec8fec-9597-48cb-b081-2a5db0846195 and focused lineup sessiona51c2838-af63-43fe-8c85-e666094a1609 observed:

- Exact match route `/scores/event/ninko-evt-7e1e5af03b232f24ef0e`: Jamaica–Guatemala remained **3-2 FT**.
- Statistics displayed actual two-team values, including possession58/42, totalshots13/17, shotsontarget4/3, corners1/2. This is display proof, not independent validation against a separate live score supplier.
- CONCACAF Nations League A Grp2 standings displayed six populated team rows: ElSalvador,Jamaica,Suriname,Guatemala,Honduras,Martinique, with points3,3,3,0,0,0.
- Focused lineup visit enumerated11 named starting players on each pitch. Jamaica: AndreBlake,JoelLatibeaudiere,RichardKing,DamionLowe,RonaldoWebster,IsaacHayden,KaroyAnderson,TyreeceCampbell,JavonEast,KaseyPalmer,RumarnBurrell. Guatemala: KendersonNavarro,AaronHerrera,AllenYanes,NicolasSamayoa,JoseMorales,OscarSantis,JoseRosales,JorgeAparicio,RudyMunoz,RubioRubin,DarwinLom. Bench entries were separate. The tool's preliminary prose said10 but its enumeration and final summary are11; do not perpetuate the initial arithmetic slip.
- The first baseline reported one visible starter and no away starters; the focused visit now enumerates22. **Do not claim a proven before/after DB repair or attribute the difference solely to C18**, because initial tab expansion/scrolling was incomplete and no raw before payload was obtained.
- Live Scores board and Men/Women controls were accessible. This visit did not validate every event or prove full gender-filter partition integrity anew.
- Public article `/article/nottingham-forest-stadium-expansion-approved-so-what-now` opened with matching title, body and stadium image, still showing original **19Sept2026**. No fresh publication or re-dating is claimed. Image observed at BBCichef path ending f4bbffc0-b2a7-11f1-819c-176371125270.jpg.

### Explicit QA limitations

**Real production1440/390/320 acceptance was NOT completed.** TinyFish could not reliably set requested widths; these are default-browser observations. The1440/390/320 passing screenshots are controlled LOCAL News fixtures only. A proposed bounded production-view audit script creation was blocked because its safety status could not be determined. It was not retried under another file, encoded, triggered via another path or deployed. No claim of a successful production Playwright job or measured65-second public polling trace is made.

TinyFish asset descriptions conflicted across visits: one reported loaded Jamaica/Guatemala crests, another did not observe individual crest images in its DOM view. It also mislabeled the website's brand logo as a competition logo. **Do not use those statements as proof that competition logos/all crests are complete.** Full asset QA remains open. Date labels differed25/26Sept across sessions without a controlled timezone; no kickoff was changed based on that. Public API fetch_content returned no usable body, so those attempts are not raw-data evidence.

No new full-window912-ID retention or ten-finals sweep was performed; those counts belong to C17 historical acceptance. No manual deletion/reset/result override was performed; normal existing collector and page-view/cache operations continue.

## News service activation — deliberately not performed

Existing service **hopeful-blessing / be857be7-a029-4663-81c7-bcde75efc482** remains at deployment79f761eb-3afc-457a-b222-15c1a5c63088 from20Sept, freshly rechecked after the combined release. Source binding/root/approved running revision are not verified. Direct get-service-config contains no source stanza; builderRAILPACK and startpython -m bot.scheduler remain. Existing build logs show frontend/Node/Vite; runtime logs repeat **python: command not found**. The SUCCESS label does not prove a working News process.

list-variables explicitly returns **valuesRedacted=true**. Thus DBidentity, actual worker/results flags, Newsenable/interval/budget and no-other-active-News-owner condition are not verified. No request to reveal credentials and no alternative tool used to evade that access boundary. No replacement service was created. The nested News Dockerfile/preflight was not applied to API/results-worker or to the unverified News service.

Reviewed cost/write hazards in unchanged legacy scheduler:
- startup immediately callsjob(); repair_summary_only defaults80rows/page,8pages,8successful rewrites before new ingestion;
- `_ai_story` can ask for a second rewrite when too short; `_call_openai` can make a second HTTPattempt on429;
- new-article cap counts accepted rewrites, not all APIcalls/dollars;
- later index_missing loop and repair_contaminated can affect historical rows independently.

**NEWS_LEGACY_REPAIR_ACK was NOT set**, no new Newsenable/DBsettings/start command was imposed and no real source→DB→new-story run was started. Actual new-News end-to-end freshness remains BLOCKED. Existing May/June homepage age/selection policy was not changed and is not marked fixed. Original dates must remain original.

Unrelated staged Railway patchdb7eb99e-400a-4e62-ba03-c10610fea2f4 still targets audit-scheduler-lease; untouched. Other old diagnostic services remain as found. No environment-wide staged changes accepted; no service/settings/volume deletion, reset or forcepush.

## Resume safely / outstanding work

Fresh-read this checkpoint, issue6/8 and current main/master before changing anything. Do not reapply C18 patches or News01/02 over this integrated code; both are already in production. No unpublished C18 runtime patch remains required.

1. Resolve News service source/root and real non-secret settings/DBidentity/single-process ownership through authorized access, then implement/verify explicit request and legacy-repair controls before guarded activation. Correct recipe is deploy/news/Dockerfile and intended startpython deploy/news/preflight.py --run, but no acknowledgement should bypass unresolved hazards. Only existing News service may be configured.
2. Complete actual production desktop/mobile and asset QA through an authorized available route. Respect blocked actions; keep controlled-fixture and real-production evidence distinct. Do not infer full global fix from one match.
3. Continue football source-only rich details, incomplete/group tables, old Myanmar/Sligo links, potential Waterford duplication, full transfers/fees/squads, scorer coverage/brackets/assets and previously18unknown categories. Those are not closed by this recovery/integration release.
4. Prove fresh News source dates/images/categories in persisted and public data only after safe real ingestion, and separately review shared homepage age selection without altering dates.

Production source has advanced safely; lack of Newsactivation/fullbrowserQA is NOT a reason to reset completed Live Scores. Issues6/8 remain the coordinated handoff. This document is a combined release record with explicit blockers, not a public launch claim.
