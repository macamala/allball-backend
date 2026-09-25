# NinkoSports checkpoint 15 — 25 September 2026

## Resume here, not checkpoint 14

User requested: TABLE from Football Live Scores must show only the selected competition/group, never open its first match; fill missing football tables/details; inspect live Bangladesh–Malaysia; keep future matches/player/club/transfer data updating automatically. This checkpoint records deployed improvements, measured results and remaining gaps. It is NOT complete global football, all-transfer coverage or Rezultati.com parity.

**Backend main/deployed: `2c69cc00bdede9b1735e38d162bceaecdd6e73e6`.**
**Frontend master/deployed: `35906e1bde4f5bdba3eb79d6c4c9854093339cd9`.**
**Required worker-only variable: `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=15`. Preserve it.**

Latest terminal SUCCESS deployments, exact hashes observed:
- API `eabcd174-c2b6-44d4-9a9b-f8cbefd359e7`, 10:48:42.581 UTC, backend 2c69cc00.
- Results-worker `6c62e058-d1bb-4532-9acf-ad9d09980267`, 11:01:13.800 UTC, same backend 2c69cc00, with the new drain window.
- Frontend `d1f1a620-5b8b-4351-a469-188a9b555041`, 10:27:27.534 UTC, frontend 35906e1b.

Backend project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`; API service `c08822c6-e602-4f32-a2bc-87aedbbe9b05`, worker service `2c89eecf-b094-428a-8f7c-9642605a6baa`. Frontend project `d2187a78-90d0-437a-871b-10e16ba8d07c`, environment `52ceaa71-df43-4275-9ebe-6c19d4437461`, service `df4b231a-fcbc-4d89-bef8-d9028d03b473`.

All C10–C14 final-status, public alias, source identity, manual/retired visibility, polling/cursor, responsive standings, rich match, player profile, news-only HOME and competition ordering improvements remain. No Railway Agent, new service/scheduler, manual database/score correction, reset, forcepush or unrelated staged configuration acceptance. There WAS exactly one necessary worker-only variable change, documented below; do not repeat the earlier code-only preflight's 'no variable changes' as the final state.

## Recovery and release chain

The interrupted prior execution had already deployed C15 core although the last complete chat response named C14. Recovery verified backend `c7710745a2e1599eea045b6e760dec45887eb93d` and frontend `a8a1a28dbbc94e0dee72fd21c6a5a287fe1f5bad`, all three services SUCCESS. The original C15 preflight is `docs/checkpoints/CHECKPOINT_15_RELEASE_PREFLIGHT.md`.

This session then deployed, without replaying old patches:
1. Backend `7ee4f7647cb169ad0d1de214d7b19a52f41e756f`: guarded seasonal-to-stable parent tables; frontend 35906e1b: duplicate leaf header / correct table selector. Backend API 77a26d44-7234-475e-9421-b45edb9d98c2 and worker 6346dec6-303d-4b43-88a5-c604ecbeef85 were SUCCESS.
2. Backend 2c69cc00: graceful owner-safe shutdown. First worker deployment 13795dee-9be3-4e94-9e39-2e0957d93f42 was SUCCESS at 10:47:42.640 UTC, then superseded by the worker-only drain setting deployment.
3. Native Railway set-variables applied only the drain window to results-worker. Source code stayed 2c69cc00; API/frontend were not redeployed by that setting.

Preflights saved before writes on this audit branch:
- `CHECKPOINT_15_FORWARD_PREFLIGHT.md`, commit `929f192821b7bb5a899bbaba6243b9cb6cb6c347`.
- `CHECKPOINT_15_HANDOFF_PREFLIGHT.md`, commit `6c15aaf607dd8dc8527c80db8e58488e98d48add`.
- `CHECKPOINT_15_DRAIN_WINDOW_PREFLIGHT.md`, commit `c03bba347ac42008a695bb38cc923723a3459c5c`.

Exact recovered source archive: run 36122469774, artifact 10858442962, SHA256 `fd9d37e5c3c18a07c3a6c2d98e1872a72edd68029b380c12cab06d04c8dc0e9d`. Recovery included source refs and archive hashes, not assumptions from chat text.

## Standalone tables and layout

The public route is `/scores/competition/:competitionKey/standings`. TABLE links no longer route to an arbitrary event. Parent competitions retain exact group selection in URL; changing a group and reloading preserves it. A canonical leaf already scopes its table, so a redundant full display label is not passed as a parent-group selector. This fixes native group-label prefixes making otherwise valid leaf tables look empty.

The initial C15 browser check exposed a genuine duplicate header: one ASEAN leaf row had group=null and another had the full group label. The forward frontend fix reconciles ONLY an exact full label observed as an explicit group within the SAME canonical competition key. It does not assign unknown parent rows to the first group, merge separate groups or sports, change event IDs, or mutate source payloads. The previously failing unique ASEAN selector was retained, not weakened with first().

Actual deployed checks passed on 1440, 390 and 320 pixel widths:
- UEFA and ASEAN TABLE clicks open standalone competition tables, with no match hero and no arbitrary `/sports-data/matches/` request.
- UEFA starts in the chosen group; switching to B Group 3 shows its teams instead of Serbia's group and persists after reload.
- ASEAN Group A has exactly Bangladesh, Malaysia, Indonesia and Singapore.
- Main league tables use full desktop columns and compact mobile columns with the existing full-table control; no page overflow or JS exceptions.
- Three ordinary English leagues also passed nine direct standalone table browser checks, each with 24 teams.

Actual desktop and mobile table screenshots were visually inspected. Existing desktop header navigation overflow beyond Predictions remains a separate known UX follow-up; this checkpoint did not remove the Live Scores route.

## Table data progress — same measured cohort

Four Sydney-local days, 25–28 September, corresponding to UTC 2026-09-24T14:00:00Z through 2026-09-28T13:59:59Z:

| Metric | Before C15 | Core C15 | Forward C15 |
|---|---:|---:|---:|
| Competition/group keys in cohort | 152 | 152 | 152 |
| Nonempty table scopes | 28 | 93 | 114 |
| Public event IDs | 912 | 912 | 912 |

Latest wide table audit timestamp: **10:30:27.888925 UTC**. **86 additional populated table scopes versus the baseline, 21 beyond core C15, zero previously populated tables lost.** These are league/group keys, not 114 distinct world leagues and not an all-world denominator. Exact event-ID comparison retained all 912 rows, zero removed and zero added. Another comparison after the final code deployment at approximately 10:53 retained the same 912 IDs.

The forward 21 include League One, League Two, English National League, Israeli Leumit, Nigerian NPFL, Danish 2. Division, Irish First Division, Japan J2, NWSL, Chinese second tier, Mexico Expansion, Northern Ireland, Welsh Premier, Scotland Championship/Challenge Cup and several others. The original core additions include UEFA/CONCACAF/AFCON/U21/ASEAN group scopes.

Cause fixed: daily boards can use a seasonal league ID while an ordinary league table carries its stable parent ID. The fallback now requires a single noncomposite parent table, explicit current season, a unique known match in that same returned season, oriented numeric team IDs, kickoff within 60 seconds and both table members. It does not authorize a league from its name/logo, borrow composite groups or switch to an unproven old season. No event score/identity writes were part of that change.

Seven independently compared current native tables passed exact team-ID, position, points, played, win/draw/loss and goal-difference checks: League One 24, League Two 24, National League 24, Leumit 16, NPFL 20, Danish 2. Division 12, Irish First Division 10.

**Toppserien is still genuinely missing: 0 public rows versus 12 native rows.** Its inclusion made the expanded eight-table test fail; that failure was retained, not waived. It remained empty in the later 10:53 read. The separate navigation and code regression gates passed; do not describe the entire expanded coverage run as successful.

## Bangladesh–Malaysia: actual data and timing

Canonical event `ninko-evt-0f0c8b1216525d84d854`, native match 6232978, canonical competition `football-fifa-asean-cup-premier-division-grp-a`; native leaf 943302 / parent 13287. Teams 95797 and 5823. Kickoff 09:00 UTC.

Final source and public detail both show **FT 0–3**. Public lineups have **11 starters plus 12 bench players per side**, with supplied 4-2-3-1 formations. Final public timeline has **17 incidents: 3 goals, 9 named substitutions and 5 yellow cards**. Public statistics are empty because the checked native detail has no statistics; native shotmap also contains no shots. Do not manufacture possession, xG, shots or ratings to make this lower-coverage match look complete. Some participant country_id fields in the score payload are null despite source crests/name-based flag presentation; do not claim all underlying asset metadata was fully audited or filled in this pass.

The recovered core C15 corrected long-lived empty-detail caching after kickoff, uses short live empty-cache retry and status-transition invalidation, normalizes bidirectional marks in minute strings and carries supplied native clock seconds. The lightweight score path remains independent of expensive rich details.

Measured actual source/public observations, not synthetic fixtures:
- Seven parallel samples 10:10:07–10:11:10, all HTTP200: native 0–3 first observed at 10:10:59.907; public changed from 0–2 to 0–3 in the next sample at 10:11:10.769, about **10.9 seconds between sampled observations**. This is not the exact on-field goal time or direct Rezultati.com latency.
- Actual browser clock advanced approximately71:45→72:51 over14 samples at10:30:44–10:31:49, with12 lightweight score responses. Another final-code browser sequence showed91:08→92:13 at10:50:06–10:51:11. This is bounded, explicitly estimated clock interpolation, not proof that a score change is instant.
- Final paired run captured28 samples10:49:13–10:52:59, all HTTP200. Native FT first observed10:52:26.095; public FT first observed10:52:42.782, about **16.7 seconds between sampled observations**. The final score0–3 was stable in three terminal samples.
- Final actual browser at10:57 verifiedFT0–3 on1440/390/320: timer removed, no subsequent live score polling after6.2 seconds, correct four-team standalone table, no overflow/JS errors.

Do not claim uniform five-second source-to-screen latency. Five seconds is the visible browser's score polling interval. Accepted-observation age in the final paired sample ranged7.6–123.7 seconds during live status, median35.9; startup transition accounted for the first107–124 second ages, and another live observation interval approached86 seconds. Accepted-observation age is not identical to goal latency. No direct concurrent Rezultati.com measurement was obtained.

## Deployment handoff defect found and fixed

A real delay was exposed during the 10:26 forward rollout: public clock stayed67:23 with observation10:26:20 while native advanced68:25→70:08, catching up around10:29:26. Standby log10:26:52 showed the new worker waiting for the previous row lease. The older worker lacked orderly signal cleanup and waited45 seconds between standby attempts. Existing scheduler/write TTLs90/180 were deliberately NOT shortened or stolen.

New code installs main-thread SIGTERM/SIGINT handling, rolls back interrupted processing before existing finalizers can commit, then uses a new transaction with an atomic conditional UPDATE restricted to this exact owner. A different writer or successor remains untouched. Standby retry is5 seconds. SIGKILL, failed cleanup and host loss retain fail-closed TTL behavior.

A platform setting was also necessary: Railway documentation specifies default SIGTERM-to-SIGKILL buffer0 seconds. Before the native worker-only variable write, get-service-config showed staged=null, direct `python -m collector.worker`, one replica, and no drain variable. Only `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=15` was set, ordinary worker deployment enabled; no secrets/other variable values were read and no other service/config fields changed.

**Actual production handoff was then observed, after the Bangladesh match was finished:**
- Old worker13795dee log at **11:01:15.061280913 UTC**: `WORKER_SHUTDOWN_RELEASE ... leases=1`.
- New worker6c62e058 log at **11:01:19.499919517 UTC**: `RESULTS_SCHEDULER acquired`.
- About **4.44 seconds from logged release to logged acquisition**, instead of waiting through the old TTL. Both timestamps are production log evidence, not subprocess timings. The successful cleanup/acquisition does not guarantee zero downtime in every crash scenario.

Official references checked25Sep2026: https://docs.railway.com/deployments/reference and https://docs.railway.com/variables/reference . The worker-only preflight records this intentional exception to earlier code-only/no-variable-change preflights.

## Automatic future enrichment: actual scope

C15 adds a small enrichment share under the SAME existing scheduler lease: current football and upcoming48 hours (plus previous12 hours), up to1200 candidate rows, two detail attempts and one table attempt per due cycle with a6-second total fetch budget. Durable cursor and alternating urgent/fair slots avoid always restarting at the first league. It uses existing validated detail/table readers, source permissions and backoffs; no new scheduler or manually written fixture results.

This automatically revisits currently eligible matches/tables rather than fixing only today's named fixture. It is not an assertion that future official lineups are knowable before publication or every competition supplies every detail. C14 player club/value/career enrichment remains on-demand with its6-hour cache and identity checks. It is NOT a complete global transfer feed or fully prepopulated history of every player/club. Those remain feature/data work.

## Regression gates and artifact evidence

All artifacts listed below were downloaded, ZIP integrity checked, and relevant JSON/JUnit or exact source hashes inspected in the working container. Debug archives are evidence, not the user's preferred backup format; durable recovery is this GitHub record.

Code gates:
- Frontend leaf grouping: run36123439449, **270 tests, zero failures/errors plus build**. Artifact10857434677 SHA256 `6386068431de91566538d13821f15d7cdbe2391c66873be7cb924f2d9ba686b5`. Exact reviewed patch SHA `3705f58da9aa0d145f68bd65be29d319e85ad2b0ebac338423953994ccbf8cd7`.
- Backend parent tables: run36123670780, **860 tests**, zero failures/errors/skips, plus captured native replay. Artifact10859020438 SHA256 `4b2b300d972531c4d46bc80494208dc16387900d241fc4ba9dd1847d402496a9`; patch SHA `1cd264c6b20758c0280bcb054714652e2a58ee6837c109a855f727982c8eb77a`. Replay40 contexts includes already-supported groups; not40 new production tables.
- Backend final handoff: run36125459891, **866 tests, zero failures/errors/skips**; all860 retained plus6 new, including four real subprocess termination/rollback/foreign-owner cases. Artifact10859122561 SHA256 `785875dd8329a70862bb19c93f8a2a5d8c4e83eeecbd74b0747b63dcc65363aa`. Rawpatch SHA `4e72cef2c3f45249e23c7a6aadb4ecccd334f2c6d7ce897aea99525dc665907c`; all3 post-apply source/test file hashes independently matched local review. Full real requirements installed in CI, not stubs.

Production evidence:
- Initial core coverage10858536487: SHA `608810453f47b90cd6a808502f021528bb5f0a082c11c1dea538f4805c4c7cb9`.
- Forward coverage10859256562/run36121382147: SHA `8cf6583dd17fa4d2c0211b36b5ca703ab35414e142eafff3b1b70a3f425e6bda`, 28→114/912 retained.
- Native remaining-table probe10858268553/run36122750101: SHA `febf7de7d002bccb9af4af8bd30a6cf2563c9cee84d0bbc142cfd184bcc4cea7`; logo IDs were discovery hints only, not runtime authorization.
- Early real goal timing10857428533/run36122469774: SHA `080faa389722368a3bef4afa32a2332fe448a15e2c6a10fbec4a833c14a2378b`.
- Forward navigation/expanded tables10859586749/run36124267849: SHA `61d5e681abf97429534e534ba3f73681d82c5a77ca489c4dbb5cc4c4bcbd412b`; navigation passes, Toppserien comparison genuinely fails, seven other native tables and nine English league browser cases pass.
- Retained rich match/player/home10858851091/run36124267849: SHA `3f478a17587c6cef52a635f2ce334f7ead12d45312f57e475f73d989e5b107a7`. Actual Sligo rich match still10 substitutions/37 statistics/22 shots/22 positions; all3 browser journeys and prior player profiles/current-club links pass. HOME remains news-only on all3 widths. This was actually rerun, not a carried old artifact.
- Prior final scores/mobile10859730774/run36114622778 rerun: SHA `05eb4a693a1bb1804f0e9e29813902ea1a161339b708aadfb68129967bc71088`. Ten earlier finals, old Andorra, future Havelse scheduled/no falseLIVE, actual55-second delta/full refresh and8 responsive phases pass. Mobile compact/full standings and correct group switching pass. Sydney25/26Sept football56/272, not world coverage.
- Final-code navigation/live browser10859639733/run36126017633: SHA `3ee6879ab0a140bf2a7cdbe033d99dce9fd80888fc4d5e31b25a0ef7f6eed14a`; all3 widths/table navigation/22 starters/actual live requests pass.
- Final paired source timing10859673405/run36126017633: SHA `c0b4b0a26007d2127f7f56729c14e9582db99fc6b9ac5f29c7410e169fe8a663`;28 paired samples, FT0–3 and912IDs retained; Toppserien still0.
- Final FT browser10860600848/run36126731258: SHA `75448cbcb7fc6a6b079fb76a14431118f1bfe0d87a10a9275437e2a8ac02ebc8`; all3 widths showFT0–3, stop timer/polling and preserve correct table.

Initial core browser artifact10857557153 SHA `39820649e287cd584f36915e8c839e048147913e0a0eada12c48f8bc54d5e4e9` remains as evidence of the duplicate ASEAN header failure. Do not rewrite it as a successful run. Likewise preserve the expanded Toppserien failure rather than loosening table identity guards.

Future backend gates must retain the permanent football_test_selection.txt PLUS hidden_football_aliases, fotmob_match_centre, entity_profile_navigation, c14_live_player, canonical_detail, fiba_rich_detail, sofa_rich_detail, c15_live_tables, c15_parent_league_tables and worker_shutdown_handoff test files. Frontend must run the whole suite/build. Do not accidentally drop older tests when adding a new gate.

## Still open / next priorities

1. Investigate the **38 empty table scopes** from the same cohort. Not all are classic league-table gaps: friendlies and some knockout stages need honest applicability/bracket handling, not invented standings. But several are genuine unresolved league tables, including Toppserien. Prove the actual stored mapping/context before changing parent/group identity.
2. Remaining empty keys: football-friendlies; football-club-friendlies; football-par-cup; football-mar-botola-pro; football-chi-cup; football-asian-games; football-fin-ykk-sliiga; football-nor-toppserien; football-sco-highland-league; football-arg-primera-b-metropolitana; football-bra-s-rie-b; football-col-cup; football-usa-usl-super-league; mexico-liga-mx; football-can-premier-league; football-pan-lpf-apertura; football-fin-kansallinen-liiga-championship-group; football-eng-wsl-2; football-den-a-liga; football-nor-1-division-kvinner; football-sco-lowland-league-east; football-sco-lowland-league-west; football-uefa-women-s-europa-cup-2nd-qualifying-round; football-chi-primera-b; spain-copa-del-rey; football-women-s-world-cup-u20; usa-usl-league-one; football-can-northern-super-league; football-arg-primera-nacional; football-arg-supercopa-internacional; football-col-primera-b; football-bra-s-rie-c; football-bra-copa-paulista-semi-finals; football-nor-nm-kvinner; football-sco-swpl-1; football-por-taca-de-portugal; football-irl-fai-women-s-cup; football-arg-copa-argentina-quarter-finals.
3. Myanmar–Timor-Leste `ninko-evt-d807549bf94203765dd7` / source6233017 and old Sligo link `ninko-evt-bb4071086c3ea042f6e9` are NOT fixed by this pass. Correct Sligo canonical `ninko-evt-8ea488bb6f0bcf5038b7` remains richFT0–1. Preserve exact source/manual protections, no static score override.
4. Complete secondary-source detail coverage, transfers/fees/valuation history, squads, club/player histories, competition brackets, real shotmap, remaining identity assets and other sports. Bangladesh native statistics are absent; this is an actual data gap, not a UI bug that was magically filled.
5. Investigate possible mixed source scopes in generic LigaMX catalog before assigning a men's table to every row. No gender/competition mutation was made from logo hints. Current metadata was evidence for investigation only.
6. Continue real latency measurements across active fixtures, separate source delay from accepted observation age and browser interpolation, and retain the now-proven orderly restart handoff. No blanket5-second guarantee or measured Rezultati.com parity.
7. HOME news-only is preserved, but old thumbnails/article freshness and desktop primary-nav visibility still need their own focused work. No public launch until core end-to-end experience is stable, complete and tested.

Resume by reading this and any newer issue6 comments; verify live main/master/deployed refs. Never reset DB or blindly reapply old staging patches. User prefers durable GitHub checkpoints, not downloadable backup bundles.
