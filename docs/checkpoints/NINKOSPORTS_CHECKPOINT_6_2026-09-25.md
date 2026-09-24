# NinkoSports checkpoint #6 — 25 September 2026 (Australia/Sydney)

## READ FIRST: recovery is still OPEN
This supersedes the optimistic football-complete interpretation of earlier chat summaries. Preserve completed work, but do not label the entire football system fixed. This is a checkpoint-only branch; do not merge it into main or deploy it. Saving this checkpoint does not change production or the database.

## Verified repository refs at checkpoint creation
- Backend `macamala/allball-backend`, `main`: `8a17ffa57a2227392d3ff1211fc630f22c2981fd`.
- Frontend `macamala/allball-frontend`, `master` (NOT main): `93dd66e65231cb36967dcfe43e6355784ae3e8fd`.
- Last observed backend deployments at 23:17 UTC on 24 September: API `72759d4c-d791-4c78-bd9f-54280edfb707`, worker `755c57a3-0344-486a-b399-feb854f6df1f`, both SUCCESS. Deployment success is not data acceptance.
- Do not roll back to checkpoint #5 or replace current source from an old chat. Fetch current refs first and reconcile any newer changes.

## Work already committed; preserve it
1. Bounded score-processing/priority-cycle recovery, canonical score update routing and fetch-time provenance are in backend history. Do not re-implement from memory.
2. Nations League group-specific standings and table links are in frontend `93dd66e...`, backend `c6e0497...` ancestry. Frontend regression run `36067773072` passed with production build; backend phase-2 run `36066783469` passed. These are code/test evidence, not a claim that all current production data is correct.
3. Old-link resolution is now deployed in backend `8a17ffa...`; its regression gate `36070758620` passed (release recorded 206 regressions). It does NOT by itself close the Andorra-Malta data/visibility regression.

## Latest archived PUBLIC acceptance — FAILED
Run `36070058979`, newest inspected artifact `10839135620`, checked `2026-09-24T23:20:51.557282+00:00`:
- Football list: 55; football rows in all-sport list: 55; count after detail navigation: 55.
- Verified final scores: 7/8, NOT 8/8.
- Andorra-Malta finished keeper `ninko-evt-6d8bf3121dc158b647e1` is missing from the board. Expected source-verified final score 1-2.
- Legacy alias `ninko-evt-86345b6cb47a7c4b8524` does not resolve correctly in that acceptance run.
- Earlier snapshot at `2026-09-24T22:55:47.104875+00:00` had 8/8 finals. That evidence is historical and superseded by the failed recheck.
- Equal row counts alone do NOT prove event identity, scores, or alias correctness. Compare event IDs and payloads, not merely counts.

## Saved but NOT deployed work
### Frontend mobile standings and tabs
`mobile-responsive.patch`, base frontend `93dd66e...`, SHA-256 `80865fce8c15ccfd255face6a7975a12fb4d3c8fe097830f45a67217a49d5f1e`.
Six files: StandingsTable.jsx, standingsResponsive.css, StandingsResponsive.test.jsx, scores/MatchCentre.jsx, scores/MatchSectionTabs.jsx, scores/MatchSectionTabs.test.jsx.
Eight focused LOCAL tests and local production build passed. Full updated frontend suite and actual mobile/desktop acceptance remain pending. Original modified-file blob hashes match the production baseline: StandingsTable `bc689caf08811b1efa31bdb53a1ef9ff1359cf1d`; MatchCentre `e0ccb50a9347f4483ad7787be1f1c2e282788573`.

### Backend lineage/maintenance reproductions
`backend-lineage-wip.patch`, base backend `8a17ffa...`, SHA-256 `f4ba5bee209ac4f7c25ece4face118a3f42aa96faf9560c94465dc38aa614bca`.
Only adds `tests/test_maintenance_lineage.py`. Eight selected reproductions FAIL; nine cases were deselected in the saved run. No backend implementation changes were present in the workspace when checkpointed. In particular, the planned `collector.maintenance_policy` module does NOT yet exist. Do not claim startup maintenance has already been removed.
Reproduced issues: a retired newer observation can quarantine its finished keeper; orphan recovery can restore retired/manually blocked rows; name repair can re-enable a child; flag synchronization can leave slim list metadata inconsistent.

## Resume order (before changing production)
1. Read this checkpoint and its issue's latest comments. Fetch both repository heads and deployment metadata. Do not redeploy merely because the chat restarted.
2. Restore the saved WIP bundle to an isolated directory, verify its SHA-256 and every member hash, then inspect patches against their stated base commits. Do not apply blindly to a changed branch.
3. Implement and test lifecycle guards for retired/canonical observations in integrity, orphan recovery, source-native revalidation and canonical collapse. Synchronize row/extra/slim-list visibility. Make startup historical mutations explicitly opt-in, after reviewing app lifespan. Preserve manual_hidden/do_not_restore.
4. Run new reproductions plus existing score/source/identity/group regression suites. Then a reviewed release, and public acceptance of all eight known finals, old/new aliases, list-detail agreement, and persistence across repeated reads/controlled restart validation.
5. Only after score stability, finish the saved mobile change, full frontend suite/build and browser QA; then real missing competition logos/flags; then remaining football detail features. Other sports remain backlog, not forgotten.

## Mandatory interruption/release discipline
- Before each production-affecting release: save base/head SHAs, patch/commit, tests actually run, pre-change public snapshot, intended scope and a safe rollback plan. Code rollback is NOT a database backup.
- After verification: append timestamped evidence and the next exact action to the checkpoint issue. Keep old evidence and label it historical if superseded.
- Persist WIP on a NON-production branch even when tests fail, explicitly marked NOT DEPLOYED. Never leave the only copy in chat or temporary files.
- Never force-push production, reset all visibility flags, infer LIVE from kickoff alone, or fabricate scores/logos. Keep TheSportsDB artwork-only where previously agreed.
- Do not use Railway Agent for routine work. One bounded read-only attempt found DATABASE_URL unavailable; do not repeat that attempt or create diagnostic services. Use direct tools and public/read-only evidence.
- This file records workflow rules, not an already-installed automated deployment blocker. It cannot guarantee the chat never disconnects.

## Railway scope for recovery
Backend project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, production environment `cb27d851-9198-47c8-a733-8356e8b6cf63`; API `c08822c6-e602-4f32-a2bc-87aedbbe9b05`, results worker `2c89eecf-b094-428a-8f7c-9642605a6baa`.
Frontend project `d2187a78-90d0-437a-871b-10e16ba8d07c`, environment `52ceaa71-df43-4275-9ebe-6c19d4437461`, service `df4b231a-fcbc-4d89-bef8-d9028d03b473`.
Do not use the empty project named allball-backend (`28adfc10...`). Do not accept unrelated staged changes; a deletion for accidental audit-scheduler-lease was staged, not committed, at last inspection.
