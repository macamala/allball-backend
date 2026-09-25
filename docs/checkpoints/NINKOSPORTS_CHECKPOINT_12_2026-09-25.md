# NinkoSports checkpoint 12 — 25 September 2026

## Resume here; do not revert to checkpoint10 or11

User asked to continue missing-data completion and fixes after the interrupted C11 pass. C11 source, successful follow-up deployment and completed production checks were recovered. This pass adds C12 tested runtime changes and actual post-deployment acceptance. It is NOT a whole-football/all-sports launch or completion declaration.

Backend main/deployed **50cad8107e23ee9e830f730b18c13a32f4ce7575**.
Frontend master/deployed **4355aa22a26036376fa86f018b6c838424b7eff2**.
Bases retained: backend2f5108c7d5394bc4c87743a885f39e9472e7ebe2 (including17315 native evidence/artwork, explicit psycopg2 startup driver, deterministic list representative); frontend9a18f3ec91610356304fc614b9a10b621792291f (actual PNG flags/FIFA template correction). Both retain all C10 stream/final-status/false-future-LIVE/mobile standings/group repairs.

Railway observed terminalSUCCESS with exact hashes:
- API2b10f13c-6594-41e1-b1a5-9d7846215a3a at06:08:30.763Z.
- Results-worker ae5b2277-4a19-483d-aee0-64ab2fb94df8 at06:07:54.286Z.
- Frontend f041c611-3afd-49a7-b5a3-50f571c5f25c at06:07:55.816Z.
Backend project17f6ebff-0f6b-42dd-be86-35ca9ca40301/envcb27d851-9198-47c8-a733-8356e8b6cf63, APIservicec08822c6-e602-4f32-a2bc-87aedbbe9b05, workerservice2c89eecf-b094-428a-8f7c-9642605a6baa. Frontend projectd2187a78-90d0-437a-871b-10e16ba8d07c/env52ceaa71-df43-4275-9ebe-6c19d4437461/servicedf4b231a-fcbc-4d89-bef8-d9028d03b473.

No RailwayAgent, DB/manualscore commands, newservice/scheduler, variable/config changes, unrelated stagedpatch acceptance, forcepush or reset. Only reviewed non-force fast-forwards through existing integrations. Do not replay saved patch application against already-patched heads.

## What C12 changes

Backend isolated branch fix/hidden-aliases-c12-20260925; one runtimefile collector/football_fixture_linkage.py plus19 new testcases. Automatically quarantined duplicates with fresh same typed FotMob matchID, same competition, oriented literal names and compatible time/provider IDs/final result can attach as aliases of an already visible accepted keeper. Hidden rows cannot become replacement public keepers. Manual/rich/slim/retired restrictions, unknown quality/disposition, conflicting result/provider IDs, independent child trees and writes-disabled remain blockers. Alias merge has a nested savepoint and invariant requiring the previously accepted status and score to remain unchanged; accidental score modification rolls back. LINKAGE_REVISION4 adds only an existing bounded deferred retry; policy revision, historical cursors and request budgets stay intact.

Frontend isolated branch fix/live-sidebar-c12-20260925. LiveNow, global live number and top competitions now follow selected sport, including MySports and esports children; MySports badge is counted. Compact sidebar gives names full pair width and wraps instead of clipping to two letters; per-set/period columns stay on the main scoreboard, omitted only in compact sidebar. Main polling, day boundaries, scores and standings unchanged.

## Independently verified code gates

Backend run36101039156 SUCCESS: **770 tests, zero failures/errors/skips**. Artifact10849541369 SHA256365dcdcc728777aa0b56deb3247ea97a2fa24e13a6ff896ea94769ce709b1a5d downloaded and ZIP/JUnit checked. Exact14232byte source.patch SHA256efd2c77aee2a827aabd99cd54b119d6e82262e2dd5494541cf466b7609555e99 byte-identical to reviewed local source; both file hashes match. Baseline new19cases had3fails/16pass; focused94 passed after implementation. Real backend requirements installed in CI, not stubbed.

Frontend run36101146531 SUCCESS: **217 tests, zero failures/errors/skips, plus production build**. Artifact10848983137 SHA256438e8d8a11e85ab5d439ee036d4b274b8aeb464df3191298f0f44fc93a619062 ZIP/JUnit checked. Exact10698byte source.patch SHA2564a4b8c3e14879145302f8ec6bbdbf87d2c27a727aea65d2c4e37e4c287d7fef5 equals reviewed local patch, all four file hashes match. Both fresh branch compares were ahead3/behind0 before release.

Preflight saved before main/master changes at928b32bdadfaf6d947f6742f4b2fb9f1f9c86646: docs/checkpoints/CHECKPOINT_12_RELEASE_PREFLIGHT.md on this audit branch. It also records recovered C11 failures and successful follow-up honestly.

## Actual football data progress, not inferred from green deploys

Same broad audit11UTCdates September18–28. Previous05:42:26UTC C11 artifact10848581865:2662public,2607source,2375strictmatches,1509playedagreements,2playedmismatches,232strict-unresolved,0exactduplicatepairs,85agedscheduled.

Latest measured **2026-09-25T06:10:02.412925Z**: **2698public football events,2601upstream observations,2403strict matches,1543played agreements,1played mismatch,198strict-unresolved identities,0exactduplicate pairs,84agedscheduled**. Source1695finished/905scheduled/1live. Source total changed by6, so do not frame the counters as a fixed-denominator all-world coverage percentage. The ongoing collector was advancing before C12; these observations alone do not establish that every new row was caused specifically by this code patch.

Exact public-ID comparison: **all2662 prior public IDs retained;36 additional IDs; zero prior IDs removed**. Added36 cover Portuguese cup8, Cyprus2.Division5, Uruguay Segunda4 and Primera3, Finnish divisions/groups6, GreeceSuperLeague2 two, HondurasLigaNacional2, SpainSegundaFederacion3, Icelandplayoff1, ScotlandLowland1, Bangladesh1. All36 have supplied home/away logoURLs, competition logoURL and countryID. URL presence does not prove every image loaded or every match-detail feature is complete.

TPS–Ilves ninko-evt-5c9f97c091957c442eb3/source6145904 now **finished0–3**, in public detail and broad source comparison; it was scheduled/null at05:42. No manualscore edits. A production FOOTBALL_VERIFIED_LINK log for the change was not captured, so do not invent exact causality.
Laos–Brunei oldf150e48ad644076a2b20 now resolves2a126bf1f0d121be8fb7 with **finished3–1**, C11 repair retained. Andorra old86345b6cb47a7c4b8524 still resolves6d8bf3121dc158b647e1 with **finished1–2**.

Broad run36087724592 rerun scores job, artifact10849308336 SHA256922d93f08859397329ac5f064bc8ba21fa778f260d740a6f95527baa1763e090 downloaded, ZIP and actual acceptance/public JSON checked. Its embedded legacy source archive is pinned828193d from the old audit workflow, NOT the deployed C12 source; raw public/source HTTP snapshots are current. C12 code proof is the separate gate artifacts above.

## Actual UI, refresh, artwork and regressions

New public Chromium run36101606971 SUCCESS, audit8de7ca1c64746f212d96b49691797c1d2fe1d49b, artifact10849740851 SHA25606a68fd7e6befa415047c15e32b10ba3dbc49fc966dd225ae1729ddd84e03980 verified and parsed. **Nine checks**: football/tennis/all at1440/390/320px pass sport scope, live count, top competition exclusion and no page overflow/errors. Desktop had actual live football and tennis: football sidebar contained only UzbekistanU23–SaudiArabiaU23, tennis only KatieVolynets–KimberlyBirrell; all had both. Desktop name widths105px with normal wrapping/noellipsis; full text/title retained. Sidebar remains intentionally hidden in mobile layout, so mobile checks prove page/nooverflow/scope, not a visible mobile sidebar. Main scoreboard retains sets by regression test. Actual football1440 screenshot visually inspected. New delivered bundle index-BWwINCfp.js.

Existing screenshot acceptance rerun36098752465 after C12: artifact10849123645 SHA256a18dd8baaf58f4afac6c12524e0e408d190557acc0f10ae8d20092e6f9e696b4 verified. API06:10:11UTC: SydneySep25football56/Sep26football268, **all10 earlierfinal checks pass**, oldAndorra correct, futureHavelse scheduled notHT/LIVE. Eight initial/after55sec/mobile320/390/desktop1440 phases passed with actual successful status-delta and full refresh; noJSerrors. Previously repaired compact/full standings and group-switch/tab tests passed320/390/1440 through06:12:35UTC. These counts are snapshots, not world coverage.

Artwork job rerun separately after C12, latest jobs107966012291/assets and107966013568/carried successful previous-screenshot; refresh jobIDs before rerunning. Artifact10849741378 SHA256bacaca57626c3cd5c00c24acc191e4574dde474f431f424500c7782f5f095881 verified. At06:14:06UTC SydneySep25all202/football56, Sep26all314/football268. In both football subsets zero missing home/away logoURL, competition logoURL or countryID fields and zero unexpanded FIFA URL templates. Six responsive visible-flag checks passed; six official FIFAflag/crest responsesHTTP200 image/png with decoded valid image bytes. This does not verify every offscreen football image. Allsport raw blankparticipant slots205/30 and competitionlogo slots33/13 remain; race pseudo-home/away fields mean these counts are not all applicable club-logo gaps. Do not fake race participant crests to zero them.

## Still open; exact next work

1. **Myanmar–Timor-Leste** ninko-evt-d807549bf94203765dd7/source6233017 remains scheduled1–0 versus fresh upstreamfinished2–0. It is the ONE mismatch among strictly matched played observations in this sample, NOT the only remaining defect. Parent FIFA row and FotMob group roots require proven cross-provider parent/group linkage. Preserve group boundaries, existing URLs and all source identity/manual guards; no static score override.
2. **Sligo oldlink** bb4071086c3ea042f6e9 still scheduled/null, canonical8ea488bb6f0bcf5038b7 isfinished0–1. New hidden-alias policy was tested/deployed, but this specific oldlink did NOT converge in post-release public checks. Read actual stored proof before extending; do not call missing list duplicate a fixed oldlink.
3.198 strict unresolved identities and84agedscheduled in broad snapshot need classification into name/time changes, source identity conflicts, missing coverage or intentional policy. They are not automatically198 missing matches. Preserve all2698currentpublicIDs and earlieraliases.
4. Whole match-detail coverage (statistics, lineups, player links/photos, timeline, sport-specific sections), standings/artwork beyond tested scopes and other sports remain open. Tennis sidebar has one raw competition slug tennis-wta-1152-singapore; national/country values and mixed doubles need provider-specific identity validation, not guessed flags. Keep football stability first.

Next session: read this checkpoint and newer issue6 comments; verify current main/master/deployedrefs. Do not run stage/apply scripts on already-patched heads. Use ordinary accepted ingestion and small independently tested forward changes, preserving manual/retired policies and database state. User wants durable GitHub records, not downloadable backups. No public launch before stable complete tested core.
