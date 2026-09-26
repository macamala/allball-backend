# NinkoSports checkpoint 17 — WIP handoff, 26 September 2026

## User requested a new chat; stop feature work here

The user asks to continue missing football details, tables, old links, transfers, top scorers and brackets, and reports men's/women's football mixed on Live Scores. Latest interruption: move to a new chat because this conversation is slow. Preserve the work and resume safely, do NOT claim C17 is released or fixes are already live.

**Last completed/deployed checkpoint remains C16. C17 is an UNRELEASED WORKING DRAFT.**
Fresh GitHub reads at handoff verified:
- Backend main: `52272139d4ecaffbe84cc4709e25c0b0ed3abb56`.
- Frontend master: `0b26a18f5a1d0a5b8ccc8adc57b8c9d5d17d2f13`.
- Backend candidate branch `fix/football-categories-scorers-c17-20260926` still points at the same C16 backend SHA: no candidate source has been published there yet.
No production refs, database rows or Railway configuration were changed in this C17 handoff. Preserve worker-only `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=15` and all C15/C16 source/identity/manual/retired/clock/group protections. No RailwayAgent/newservices/reset/forcepush/unrelated staged changes.
Read C16 full checkpoint from `audit/football-recovery-20260925-10`, record `b797f3344874cbdf76c897ced20432e695b9965c`, path `docs/checkpoints/NINKOSPORTS_CHECKPOINT_16_2026-09-25.md`, and issue6 comment5833049717 for prior production proof and exact regression requirements.

## Exact code drafts are durably saved, not just described

On THIS branch, commit `023e73a50ec1244c506a4d3ef2a457c2669722f1`, directory `audit/c17-handoff/`:
- `backend.0.b64`, `backend.1.b64`, `backend.2.b64`: concatenate in numeric order, base64 decode then gzip decompress. Result is the complete backend diff against C16, 51,267 bytes, SHA256 `cb4d62f05d88eac703ac4eb375ad3e1de514f55bf9b5130098414b5936996bb0`.
- `frontend.0.b64`, `frontend.1.b64`: same procedure. Result is the complete frontend diff against C16, 25,624 bytes, SHA256 `b7f01962d89daefcf4f5657ffc277a94cfd6d8f07f576f5a9f8916dc9d39a67a`.

All five remote blob SHAs and byte counts were read back and match the actual local files:
- backend.0: 5700 bytes /154d36b70cf2856d59f9137fcd5455c4422bbeba
- backend.1: 5700 bytes /7c3d514932760fc161b2549514016addf302c503
- backend.2: 5700 bytes /8b8c2cda2d1ae4b568157ec3cbeb9d7b91a90d7e
- frontend.0: 5700 bytes /29cd6f45ac8545ab334d88748f940b2b33de8e00
- frontend.1: 5384 bytes /05427bb9ef88d112ae11df13e722031a52ad3407

Both decoded patches were checked equal to actual current `git diff --binary` in the working repositories. Both passed `git apply --check` against newly extracted exact C16 source archives. That proves recoverability, NOT functional correctness or release readiness.

An earlier interrupted attempt to create `audit/c17_backend.b64` did not change the candidate branch. Do not reconstruct its oversized/incomplete chat payload or assume it exists. Use ONLY the five verified saved chunks above and patch hashes. No blind patch replay onto already-modified code.

Restoration example, in an isolated workspace only:
```python
import base64, gzip, hashlib
from pathlib import Path
p = Path('audit/c17-handoff')
for side, count, expected in [
    ('backend', 3, 'cb4d62f05d88eac703ac4eb375ad3e1de514f55bf9b5130098414b5936996bb0'),
    ('frontend', 2, 'b7f01962d89daefcf4f5657ffc277a94cfd6d8f07f576f5a9f8916dc9d39a67a'),
]:
    encoded = ''.join((p / f'{side}.{i}.b64').read_text().strip() for i in range(count))
    patch = gzip.decompress(base64.b64decode(encoded, validate=True))
    assert hashlib.sha256(patch).hexdigest() == expected
    Path(f'{side}.patch').write_bytes(patch)
```
Fetch exact bases, inspect diffs and run `git apply --check` first; apply only to the matching isolated repository. Do not apply to production through a read-only audit workflow.

## Draft content and findings to verify further

Backend draft14 files: app.py, audit/c17_native_replay.py, collector/cache.py, competition_hub.py, competition_identity.py, football_board_refresh.py, NEW football_category.py, NEW football_category_catalog.json, NEW football_scorers.py, football_table_identity.py, fotmob_crosswalk.py, fotmob_rich.py, provider.py, tests/test_c17_categories_scorers.py.

Frontend draft9 files: CompetitionHubPanels.jsx, EventList.jsx, NEW TopScorersPanel.jsx and its test, sportsData.js, NEW FootballCategory.test.jsx, LiveScoresPage.jsx, styles.css, styles/competitionHub.css.

Draft goals:
1. Prevent women's competition labels (e.g. Liga MX Femenil / Women's FA Cup) matching a men's substring canonical. Use checked native parent identity and explicit category metadata; unknown remains unknown, never silently male. Keep the same event ID, score and retired/manual restrictions while the regular collector repairs a wrongly bucketed row. Add category to public rows and UI filtering/grouping without hiding women from the all-football view.
2. Toppserien strict detail identity rejects a '(W)' name decoration despite matching numeric team IDs. Draft permits only this decoration with verified female context and equal oriented native IDs; must not strip ages/reserves or merge men's/women's squads from names.
3. Add verified top-scorer endpoint and tab with season/parent identity, registered source rules, bounded caching, goals/penalties/appearances/player and club links. Do not claim a complete transfer feed or whole global coverage.

The checked local category catalog has101 parent competitions,23 female. Captured local native replay has294 category cases,2 detail cases and6 scorer samples. Scorer parsed row counts: Ireland126=139; LigaMXFemenil9906=121; LigaMX230=121;9907=59; Toppserien331=118; LeagueOne108=139. These are LOCAL REPLAY artifacts on fetched native samples, not proof that production endpoints/UI now show them.

## Actual testing state — not a green release gate

Local full backend attempt STOPPED during collection with8 errors caused by missing `feedparser` (incremental_scheduler, collector_architecture, fotmob_breadth, live_watch, stale_live, scheduler_safety, pass3, pass5). No full backend pass, frontend full pass/build or real C17 browser/deployment acceptance has been established. Saved tests and replay code must be rerun with the real dependencies in CI. Do not stub missing dependencies or infer overall success from a few replay samples. The original local full log is `/mnt/data/c17work/local-backend.log` if runtime survives; the outcome is recorded here even if it does not.

## Native research already saved — do not redo all discovery

All native fetch workflows are on THIS audit branch and were read-only. Download through GitHub Actions artifacts; the old tool URLs expire, the artifact IDs are the durable retrieval handles while retained:
- Exact C16 source, four-day public football baseline and native boards: run36205878806, artifact10892589996 `c17-exact-source-categories`, ZIP SHA256 `181c7e755df52d99fb1668b9633f8e7066582e1879b25a7c49945428fef26958`. Contains backend.tar.gz, frontend.tar.gz, previous audit archive, exact source refs and public/native JSON with timestamps.
- Native league metadata: run36206124825, artifact10892924813 `c17-native-competition-identities`, ZIP SHA256 `7b190b006f32880b2d87fe7a19c58fa37c18739e075eade6a205550b9948a0b9`. Native detail witnesses5105421 and5977364 included. Logo IDs were discovery hints, not authority for runtime mapping.
- Actual gzip-decoded scorer feeds: run36207063952, artifact10894560682 `c17-decoded-scorers`, ZIP SHA256 `fd146732ac439c25904c51e5818d059c2aa54017f37394a89386b38dd27f7a62`.
- Earlier scorer attempt36206808913 failed because the trusted URL whitelist omitted the observed Apertura/Clausura segment. Next run36206900777 completed but its JSON held gzip decode errors; artifact10894885170 is NOT usable successful scorer data. Corrected36207063952 decoded actual gzip bytes. Preserve those distinctions.

## Next action in the new chat

Read this WIP record and the latest issue6 comments, verify current main/master before changes. Restore the exact five chunks, review especially public category projection, source/native context ownership, stable IDs/aliases and women's table scopes. Run every retained C16 backend regression plus C17 tests/replay and complete frontend suite/build on isolated branches. Publish only after those pass and after saving a release preflight. Then verify men's/women's list/detail/table/H2H consistency, Toppserien, top scorers and all retained canonical IDs on real production at1440/390/320px; log actual errors and remaining limits. Persist a final C17 checkpoint only when the release and public acceptance actually finish.

The rest of C16 backlog remains OPEN: source-only season records/full MatchCentre linking,38 historically empty table scopes including applicability, old Myanmar–Timor and Sligo alias, transfers/fees/value history/squads, top scorers until this draft is verified, brackets and shotmap, remaining logos/flags, other sports, desktop nav and news freshness. Do not silently drop this backlog or switch to AI subscription/community before core completion.
