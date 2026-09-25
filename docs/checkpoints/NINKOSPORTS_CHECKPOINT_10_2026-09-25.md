# NinkoSports checkpoint 10 — 25 September 2026

## Resume here; do not reset to checkpoint 9

The user's three screenshot faults are fixed in deployed code and passed repeat actual public API/Chromium checks. This is NOT a declaration that every competition, historical score or detail feature is complete.

**Backend main/deployed: 9759bbee2f829f995119799f305f917f73497835.** Preserves c2f5b5d610718cc43b6205296444387ea3b6df7c and the entire earlier maintenance/source identity chain.
**Frontend master/deployed: 99653b3e9af022cfedc430b43e94466720783d57.** Preserves d0db12fe066fba328e86e9e8a80b313c20d3d2df mobile standings/group/tab repairs.
Both moved by reviewed non-force fast-forwards only. Never reapply old stage scripts on these already-patched refs.

## What actually failed and was repaired

1. Finished matches remained visually LIVE92–99min because frontend CONFIRMED_LIVE overrode the new finished status. Final/non-live status now wins; explicit false/null clears old live metadata. Older partial updates cannot overwrite newer rows.
2. Raw status deltas bypassed canonical visibility and could resurrect Andorra–Malta's scheduled alias. Deltas now use public normalization, enforce row/rich/slim/manual/retired restrictions and issue retirement tombstones. Sparse unknown aliases cannot be appended in the client. Complete date-bounded public DB snapshots reconcile exact current rows; session snapshots v2 expire after5min. Network/legacy partial shrink protection remains.
3. Future Havelse–Fortuna was HT0–0 because OpenLiga preallocated HalfTime/After90Minutes0–0 slots were treated as played phases. Empty result slots no longer prove kickoff/HT/FT. Explicit finished/goals remain supported. Future football live/break/stale is rejected before kickoff, with copied public score/periods/incidents cleared; no manual DB score or fabricated result.
4. Status changes beyond the old400-row limit could be skipped by client timestamp advancement. Public delta paging now uses exact microsecond timestamp+ID cursors and overlap. Client single-flight/request-generation guards consume pages safely. Full board refresh30s while activity exists,45s idle, rather than120s live. This is client refresh policy, NOT proof of upstream latency for all sports.

## Verified production outcome

Final read-only acceptance run **36095562985 SUCCESS**, audit head55a113a330199a7550c798973b1c67ef54f6e3af. Artifact **10847386910**, ZIP SHA256 **3e0c70e37ff5f7afb4d0568d18c8c51245c62f34228ec276ce242f9234008be4**, downloaded, ZIP checked and JSON independently reviewed. API read04:43:38UTC; browser checks through04:45:47UTC (Sydney14:45).

All10 checked finals match in list and detail: Everton CD–Universidad de Chile0–1; Dominican Republic–Nicaragua3–2; Cayman Islands–Dominica0–0; Haiti–Trinidad and Tobago3–2; Atletico Nacional–Millonarios1–1; Alebrijes Oaxaca–Atletico La Paz1–3; Mineros–Piratas3–0; Costa Rica–Curacao3–4; Andorra–Malta1–2; Kosovo–Ireland1–0. The eight formerly frozen games now render FT, not LIVE. Andorra appears once in its proper group; old86345b6cb47a7c4b8524 link returns the canonical1–2 final.

Havelse canonical d0203f3635ffe7d1db45 remains present as scheduled, public scores null, no HT/LIVE NOW, kickoff2026-09-25T17:00UTC = **Sep26 03:00 Sydney**. The fixture is not hidden/deleted to make LIVE disappear.

Sydney Sep25 public football count **56**; Sep26 **267**. Football-only and all-sport football subsets have identical ID sets. These counts are snapshots, NOT claims of complete world coverage.

Eight real browser checks passed: both dates initial/after55seconds at1440px and responsive390/320px. Friday saw7 actual successful status-delta polls plus1 full refresh; Saturday4 status polls plus1 full refresh. No target returned to falseLIVE or duplicate state. Zero JS errors/page overflow in tested scopes. Delivered bundle index-6FYaTW1A.js. Status delta30rows/1page/no truncation in final live sample; equal-timestamp multipage/no-loss behavior is covered by regression tests, not claimed as observed in this one-page sample. No retirements happened in this last sample; tombstone policy is unit-tested.

Existing production mobile standings/browser also passed320/390/1440px: compact/full columns, sticky names, group switching Serbia/Germany/Netherlands/Greece to Austria group and back, visible active tab, no page overflow.

### First browser run honestly retained
Run36095253012/artifact10847416481 SHA256269a51ec3014a5496b5932603dc2cf3db6288a8ed700c71d71ac8af66de6dfc4 had all API checks and7/8browser checks pass, but initialSaturday check ran against loading skeletons because skeletons also carry .score-row. Screenshot confirms skeleton-only state, not wrong scores. Audit readiness changed to wait for actual .score-row-link; no product or score assertions removed. Added hard assertions that real delta and full refresh HTTP200 occurred. Repeated finalrun above passed all checks; deployed source was unchanged between these runs.

## Tests and deployment evidence

Backend gate36094756065: **701 tests,0failures/errors/skips**. Artifact10847216558 SHA256933b8623caee3d4ca8c6567a028839ac5c2e02ca4235e3823a6945f3804ef248. Exact21428byte patch SHA256b14e648068f53b23266ee757afebeeb00a17777e2cf15e4978a09b9511a15ece equals reviewed local bytes. Actual requirements installed in CI; no feedparser stubs.
Frontend gate36094588197: **175 tests,0failures/errors/skips plus build**. Artifact10847320590 SHA2563a0aab5559b93c612ce9dab42ab2bf6604bd6f2beeaed1fd1d5e7e35a39596d0. Exact6731byte follow-up patch SHA256370fb0a8eed44071450b5908f7ffa62438469e1e9427402334c456febc3bf811 equals reviewed local bytes. First frontend gate36094167985 also passed tests/build.

Railway terminal SUCCESS verified with correct commit hashes: API bca2254a-4028-4c9a-9803-5c7cf0f002ed at04:37:21Z; results-worker507d3da8-57af-4347-ae2b-829cd71360f0 at04:36:52Z; frontend a84fce58-b743-4e64-a234-626d96f84a64 at04:36:57Z.
Backend project17f6ebff-0f6b-42dd-be86-35ca9ca40301/envcb27d851-9198-47c8-a733-8356e8b6cf63; APIc08822c6-e602-4f32-a2bc-87aedbbe9b05, worker2c89eecf-b094-428a-8f7c-9642605a6baa. Frontend projectd2187a78-90d0-437a-871b-10e16ba8d07c/env52ceaa71-df43-4275-9ebe-6c19d4437461/servicedf4b231a-fcbc-4d89-bef8-d9028d03b473.
Worker logs through04:44:27 show continuing date cursor work and preserved explicit deferred identities, not a crashed/stopped collector. Sep24 still4deferred; Sep25 still5; source identity backlog remains.

## Open work — must not be silently marked solved

- Last broad pre-change04:03:55UTC audit had18played mismatches,799strict-unresolved identities,94agedscheduled over11UTC dates. This pass did NOT rerun that entire audit; those are historical measurements, not current guaranteed counters.
- Sligo oldbb4071086c3ea042f6e9 detail was still scheduled while8ea488bb6f0bcf5038b7 showed0–1; actual persisted alias convergence remains open.
- ASEAN same-source renamed roots carry old AMBIGUOUS verdicts. Prior local evidence-revalidation experiment is NOT in this release. Requires narrow current typed-match+leaf proof, preservation of manual/unknown-quality/contradictory finals/independent trees, and full tests before another release. Do not blanket allow ambiguous rows.
- Broad logos/flags, player/detail/statistics/lineup and whole-football coverage remain unfinished. The Live Now sidebar currently has global-sport scope even when football selected; cramped names for period-grid sports are a follow-up UX issue observed in screenshots, not closed by this score patch.

## Resume and rollback rules

Read this record and later issue6 comments, then recheck source refs/deployments. Continue historical identities/remaining football gaps from deployed9759/9965; do not revert to c2/d0 merely because context changed. Keep all repaired scores/aliases, source identities, manual restrictions and mobile UI.
No RailwayAgent, diagnostic services, direct DB/manual score commands, new scheduler, force pushes, source/variable changes or unrelated stagedpatch acceptance. TSDB artwork-only policy and disabled legacy worker remain. Do not touch stagedpatchdb7eb99e-400a-4e62-ba03-c10610fea2f4.
Preflight and scoped forward-revert plan are in CHECKPOINT_10_SCREENSHOT_RELEASE_PREFLIGHT.md (saved before production). Code rollback, if genuinely required, is a tested scoped forward revert of this patch, not DB rollback. User prefers durable GitHub records, not downloadable backup bundles. Existing browser tabs require one reload to load new JS; do not use repeated refreshes as a substitute for fixing data.
