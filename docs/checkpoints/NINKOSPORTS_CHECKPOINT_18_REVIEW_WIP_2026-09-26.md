# NinkoSports C18 — recovery review v2, 26 September 2026

**WORKING DRAFT — NOT DEPLOYED. C17 remains the last completed production checkpoint.**
This record supersedes the earlier C18 WIP only as the latest saved draft. It does not supersede C17 as an accepted release. The user's priority is still finished matches with missing lineups/statistics/events, and durable automatic recovery rather than one-off edits.

## Production and coordination

Fresh reads at the start of this continuation confirmed backend main `cf192f22da637b9b54495cd5fc2ba238abbfbee3` and frontend master `9a9d1cc996f746a63d4716043b849a7b12e57538`. This continuation made no production ref, database, score, visibility, Railway configuration or scheduler deployment changes. No Railway Agent, new service, reset or force push.

Issue #6 remains the primary Live Scores handoff; parallel News work is isolated under issue #8 and must not be overwritten. This branch contains inert patch archives and documentation, not applied C18 runtime code or a new test workflow.

The earlier safety-blocked baseline workflow was not retried, replaced or invoked through another trigger. Fresh site/API inspection was unsuccessful. No specific currently empty match is claimed repaired in production. TinyFish was suggested for interactive browser checks but was not connected; a browser connection would not itself supply missing backend/frontend dependencies.

## Additional defects reproduced and corrected in this draft

The original C18 draft already introduced bounded final-detail retries through 72 hours from verified kickoff, fair worker scheduling under the existing lease/budget, and visible recent-final detail polling every 60 seconds. This review added:

1. **Wrong match data cannot fill an empty FotMob football cache.** Existing stored oriented pair/kickoff identity must pass before parsing context-bound football detail, not only before replacing an already populated section. Direct parser-only calls without stored context and other sports keep their prior policy. Invalid identity remains unavailable rather than borrowing another match's data.
2. **A partial final lineup cannot erase the other side.** Absent/empty sections retain previously observed data. A nonempty corrected player list replaces its predecessor; lists are not concatenated, so withdrawn starters are not retained merely because they existed before. Inputs are deep-copied and explicit false flags remain meaningful.
3. **One Sofa component failure does not discard other successful football components.** Individual transport exceptions become component failures; only exception class names are retained. This is not a new complete Sofa identity authorizer. Other sports' exception policy is unchanged.
4. **Nonplayed records do not consume final-repair slots.** Cancelled/canceled, postponed, abandoned and awarded rows are excluded from that recovery candidate queue. This does not delete or hide them from storage or the scoreboard.
5. **Initial loading and detail polling share request ownership.** MatchPage uses a per-route token gate so a visible board preview cannot cause a poll to overlap the initial request. An older route or StrictMode cleanup cannot release a newer request. Recovery expiry is rechecked at each tick, including after repeated failed requests with no successful render. Fast score polling and final/live status policies are preserved.

These changes are recovery safeguards, not a promise that every upstream publishes every section or a guarantee of end-to-end delay. Missing source identities and genuinely absent source coverage remain separate work.

## Exact source restoration

Local source was reconstructed from previously retained source artifacts and patches. Original C17 file Git blob IDs were checked against the recorded accepted versions before applying C18. Local reconstructed git commit IDs are not the original remote commit graph.

Original C18 patch archive remains at revision `39c1c7a6c8f3a5daed58dc681bbde99c46a3e436` on this branch:
- `audit/c18-handoff/backend.{0,1,2,3}.txt`, concatenated byte-for-byte without extra separators or trimming: 34,185 bytes, SHA256 `954b4ec7ce3b2906c58de38476e043772766e8970656d04a87c0127544d3bd18`.
- `audit/c18-handoff/frontend.0.txt`: 10,835 bytes, SHA256 `7cc9f19ed92bc02786160639f41dbf2adaf814a83611dedf8877965e03730ed8`.

New ADDITIVE review patches are saved at revision `6d87ce9161c0ce208a01a4a0e3bcf592c78b89cd`:

| Path | Bytes | SHA256 | Git blob SHA |
| --- | ---: | --- | --- |
| audit/c18-review/backend.patch.txt | 11640 | b48b1507b626d14d43d4afbe833f45ac709de23ee855e789638c49e1e5a15329 | 8847b67ad97086aaf542dd6a40715cdedee5a630 |
| audit/c18-review/frontend.patch.txt | 8912 | d996afedf3ef191daf078a605eec858612ba14c313aa06c7703c0248b7492b71 | bc439cd3c2eaecfd3768e79d2b660345dcffb210 |

Both remote blob SHAs and byte counts were read back and exactly matched the local review patches.

Full combined patches, included in the conversation ZIP, apply directly to exact C17 bases:
- Backend: 44,421 bytes, SHA256 `f500df1b1c9bd3a3e71e7524d23d0df163705800283274920cbe3a06ffde53d8`.
- Frontend: 16,857 bytes, SHA256 `23c724f9b074b77016773a787227248cd0bc16db9695afc7f1464ee4c44dcf98`.

Use EITHER the full patch on C17 OR original C18 followed by its additive review. Do not apply both methods. All four patches passed forward check/application on isolated matching base trees, per-file comparison with the reviewed working tree, and reverse apply-check. The full changes affect six backend and six frontend files. Per-file SHA256 values are in the package's restoration-verification.json.

## Actual test outcomes — not a green release gate

- Initial new review reproductions: 11 failures before the fixes.
- Final expanded focused backend suite: **251 passed, zero failures/errors/skips**, across 15 named regression files. Includes all 27 original C18 cases, 14 new review cases, retained rich detail, C15/C16 tables/hub, C17 categories/club IDs and worker shutdown guards. Actual JUnit was inspected. This is not the full repository suite.
- JavaScript in Node: **24 polling-policy cases and 6 request-gate cases passed**, zero failures. These are pure policy/ownership checks, not React integration or browser acceptance.
- **Five React integration cases are written but have not run.** Full frontend suite, production build and actual desktop/mobile acceptance have not run.
- Full retained backend selection has 62 test files. Collection-only completed with **956 collected cases and 8 collection errors due missing feedparser**. Full execution attempts with 45-second and 180-second tool limits timed out and produced no completed full-suite JUnit. Partial progress/failure characters are not reported as completed counts or dismissed as dependency-only failures.
- Environment audit found missing required packages including psycopg2-binary, python-slugify, APScheduler, OpenAI and feedparser. Local pytest9.0.2 is outside the project's specified >=8.3,<9 range. Required dependencies could not be installed. No stub dependencies or modified requirements were used.
- Python compilation and git diff whitespace checks passed.

### Actual captured-source replay

An unmodified historical Sligo native response for match5100971, kickoff **2026-09-19T18:45:00Z**, was replayed into isolated SQLite with a stale partial cache. It filled 37 statistics,15 incidents and11 starters per side; stored identity, kickoff, participants,0-1score,status and visibility remained unchanged. The immediate second read caused no second source call.

Source: retained c17-accepted-rich.zip, member c13-public/native-sligo.json, SHA256 `c00db2f10eeecd295a42d5bf3a2ac4a0bef3686383331d6297a26bc087f75cbe`. This is offline historical replay, **not** evidence that today's production matches are now filled or that the worker's real 72-hour recovery has been verified.

## Downloadable recovery package

Conversation artifact `NinkoSports_C18_Recovery_Review_v2_WIP.zip`: **66,501 bytes**,21 members, SHA256 `6682fdaf6b1eb6c8e76d2e46d3feeee6169aed6378413ce9b05437cb3047134b`. ZIP integrity and every manifest member hash were verified. Contains full and additive patches, README, reproduction/focused JUnit and logs,30 JavaScript check logs, collection/partial full-run logs, dependency audit, source replay and per-file restoration proof. This is not a database backup or a Library upload.

Runtime paths if the container survives: `/mnt/data/c18-resume/` for repositories/evidence; `/mnt/data/NinkoSports_C18_Recovery_Review_v2_WIP.zip` for the package. The original historical replay script retains its runtime paths and requires its separately retained source fixture; it is not claimed portable without path adjustment.

## Authorized next steps and remaining work

Fresh-read current main/master and issue6/8 before any future change. Restore only into isolated matching source trees and verify hashes. Complete the real dependency-compatible backend gate, all frontend tests/build and actual1440/390/320 browser checks through an authorized test environment. Obtain current empty-match examples, verify exact native identity/coverage, then compare sections and scores before/after. Save a release preflight before any production update; do not bypass the earlier blocked workflow.

C17 category/results/source/retirement/manual-hidden/delta/date-snapshot safeguards and worker draining15 remain mandatory. No production completion is claimed. Global football backlog remains open: full MatchCentre for source-only season records, empty/group tables, old Myanmar/Sligo links and potential duplicates, complete transfers/fees/squads, global scorers/brackets/assets, unclassified events and other sports/news.
