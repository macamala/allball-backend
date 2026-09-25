# NinkoSports checkpoint 16 — 25 September 2026

## Resume here; preserve checkpoint15 and all earlier protections

User requested that the competition standings page also contain future fixtures, past results and head-to-head between the clubs playing, with related football features comparable in function to Rezultati.com but original coherent NinkoSports presentation. This pass implements and verifies that connected competition centre. It is NOT full worldwide football coverage, a new import of every season fixture into the canonical scoreboard, complete transfers or full Rezultati.com parity.

**Backend main/deployed: `52272139d4ecaffbe84cc4709e25c0b0ed3abb56`.**
**Frontend master/deployed: `0b26a18f5a1d0a5b8ccc8adc57b8c9d5d17d2f13`.**
Preserve worker-only **`RAILWAY_DEPLOYMENT_DRAINING_SECONDS=15`** and the C15 owner-safe shutdown. No configuration/variable changes were made in C16.

Latest actual Railway terminal SUCCESS deployments with matching hashes:
- API `533968e7-64dc-489a-80f9-7b7836069fdb`, 12:58:03.475 UTC, backend52272139.
- Results-worker `d5707add-c5b2-45ad-b95a-112620add780`, 12:57:58.657 UTC, same backend52272139.
- Final frontend `dd9ee4d3-71d3-4eef-a04c-ae07d35f7b87`, 13:08:34.010 UTC, frontend0b26a18f.

Backend project17f6ebff-0f6b-42dd-be86-35ca9ca40301 / environmentcb27d851-9198-47c8-a733-8356e8b6cf63; APIservicec08822c6-e602-4f32-a2bc-87aedbbe9b05; workerservice2c89eecf-b094-428a-8f7c-9642605a6baa. Frontend projectd2187a78-90d0-437a-871b-10e16ba8d07c / environment52ceaa71-df43-4275-9ebe-6c19d4437461 / servicedf4b231a-fcbc-4d89-bef8-d9028d03b473.

Only reviewed nonforce fast-forwards through the existing integrations. No RailwayAgent, new service/scheduler, production DB commands, score or visibility edits, reset, forcepush, migration/index creation, paid provider purchase or unrelated staged changes. Existing canonical score/source/manual/retired policies, approximate clock, short score polling, group isolation, player profiles and news-only HOME remain.

## Delivered functionality

The existing `/scores/competition/:competitionKey/standings` route is now a connected competition centre:
- **Standings / Fixtures / Results / Head-to-head** tabs, with selected tab, group, season and chosen duel in URL.
- Default table remains a competition resource: it does not automatically open or select the first match. Beneath it are three next fixtures and three latest results, with explicit view-all and H2H actions.
- Fixtures/results show date, kickoff or final status, round, opponents, supplied crests and confirmed scores. Filter by team and round, then load more records. Cancelled/abandoned/unconfirmed matches are not manufactured as played results.
- Supplied **Overall / Home / Away** standings are available when verified native splits exist; no calculated substitute from incomplete fixtures.
- Explicit H2H selection shows available-record wins/draws/losses, oriented goal totals, previous meetings with dates/opponents/results, last five results per team and a home-venue filter. Prior meetings load10 initially, then15 more.
- The football match-detail H2H tab reuses the same comparison panel. Other sports retain their previous renderer.
- Desktop uses a centred competition layout and two-column previews/form; mobile stacks the cards. The final one-file CSS polish moves historical competition names below the match pair rather than squeezing them into40px. Recent-form W/D/L badges remain separate.

Actual final browser journeys on1440/390/320px verify table/previews, no implicit match HTTP, home standings, team/round filters, explicit H2H, correct win/draw totals,10 form records, load-more, venue selection, reload preserving the duel, and the original match H2H tab. No JS exceptions or page overflow were observed in these checks. Final mobile competition-label width242px at390 and172px at320, height16.8px, below the pair; actual screenshots were visually inspected.

## Actual public data added to the competition view

Final measured source/public comparisons at **13:10:43 UTC**:

| Competition view | Verified season records | Played results | Fixtures | Linked canonical match records | Home/away table rows |
|---|---:|---:|---:|---:|---:|
| England League One,2026/2027 |552|83|469|21|24 per split|
| Ireland Premier Division,2026 |180|158|22|6|10 per split|

These totals match the checked native season responses. Source-only supplementary records have `id=null`, a scoped reference key and no invented full-match link. Their dates, oriented teams and final scores were checked against native data. Existing accepted canonical records take precedence. The extra season display is a READ-ONLY supplement, not a claim that705 new canonical event rows were inserted or that all732 matches have full lineups/statistics/player details.

Every listed pair has an explicit H2H action. A future supplementary match was also tested in production, not only an already linked old match:
- **Dundalk–Bohemian FC**, native5100973 / `reference:5100973`, scheduled2026-10-02T18:45:00Z, round33. Public H2H has57 verified prior meetings, **26 Dundalk wins /13 draws /18 Bohemian wins**, five recent results for each team.
- All returned prior meeting pair/date/score values were checked against its actual native match response. The three actual browser widths navigated from Fixtures through its H2H button, showed the same totals, did not open a match hero or fake full-match link, and had no overflow/errors.

For the linked Sligo–St.Patrick's match `ninko-evt-8ea488bb6f0bcf5038b7` / native5100971, H2H has **57 prior meetings:14 Sligo wins,17 draws,26 St.Patrick's wins, goals48:73**, with five prior results per team. This is the available verified history BEFORE the selected match, not an asserted complete all-time record.

Bangladesh–Malaysia `ninko-evt-0f0c8b1216525d84d854` /6232978 has the one supplied prior meeting plus five recent results per team. Its already verified FT0–3, lineups and incidents are preserved; absent native statistics/shots were not invented.

Selected UEFA AGroup2 retains2 available fixtures; the broader canonical UEFA view retains44 and the ASEAN GroupA leaf4. Native9806 is only LeagueA, and parent13287 contains multiple divisions/groups. A partial composite source that cannot prove a complete scoped schedule MUST NOT impose a season and erase previously accepted groups. Explicit oldseason1900 returns empty rather than silently substituting current matches. An arbitrary unverified comparison key returns no selected event.

## Existing scoreboard data was not lost

Exact same C15 four-day cohort: **912 IDs before and912 after**, zero removed or added, checked after the final backend and again after final frontend. These are main-board canonical IDs, distinct from the new read-only season supplements.

Retained actual production checks at13:00–13:03:
- Ten earlier finals, Andorra's old canonical link, future Havelse scheduled/no falseHT orLIVE.
- SydneySept25 football56 andSept26 football272, with successful actual status-delta and full-board refresh after55 seconds and8 responsive phases.
- Existing compact/full mobile standings, correct group switching and active tabs at320/390/1440.
- Original Sligo rich details:10 named substitutions,37 statistics,22 shots,22 pitch positions; all3 detail/player-return journeys pass.
- News-only HOME and prior player facts/current-club navigation:9 home/player/order UI checks plus6 profile/club journeys pass. This does not declare old news thumbnails/freshness or desktop navigation overflow fixed.

The proper Sligo canonical record is now reachable in the new competition result view/H2H. **Its separate old scheduled `bb4071086c3ea042f6e9` database alias was NOT repaired.** Do not confuse a correct read-only competition representation with an underlying alias mutation.

## Data safety and automatic updates

New runtime endpoints: `/sports-data/competitions/{key}/hub` and `/sports-data/competitions/{key}/comparison?match=...`. Public views follow registered/enabled source permissions and exact stored native identities. A native season requires the expected parent/selectedseason and a known oriented pair/kickoff witness, expected members and explicit group evidence. Names/logos alone cannot authorize a league mapping.

Known hidden/manual/retired/conflicting records, including other raw competition keys and pre-observation legacy metadata, still block source-only reappearance. Proper differing storage keys may enter only after exact native pair/time comparison and the existing public competition/visibility resolver. No source-only record gets a fabricated canonicalID.

History parsing excludes current/future/unplayed/cancelled/awarded/contradictory records and validates pair identities. Private source references/history fields stay out of public payloads. Existing source backoffs and canonical results remain authoritative.

Visible competition refresh is30seconds; comparison refresh is5minutes. Native schedule cache has120second positive/60second negative intervals,48entries,4inflight limit and9second total network budget, with bounded1hour stale data fallback. These are policies, not guaranteed end-to-end latency. Future lineups/details still depend on actual published source coverage. C15 bounded future enrichment and C14 player/value/career enrichment remain; no global transfer worker was added here.

## Production performance regression found and corrected

The first C16 release passed smaller unit/native replay gates but failed real public acceptance: full-season reads and H2H timed out after45seconds. This was a genuine regression, not hidden by raising the timeout. Mainboard IDs stayed intact.

Initial identity lookup repeatedly applied many rich-TEXT replace/LIKE predicates in80-ID batches. The first correction consolidated the queries but used a full-season regex alternation; isolated PostgreSQL scale improved, yet real LeagueOne still timed out and Ireland took17.5seconds. A second correction uses constant PostgreSQL global regexp extraction of candidate IDs followed by set membership, then the unchanged exact typed-ID authority. It retains multiple legacy layouts/hidden restrictions and has no stale permissions cache or DB migration.

Final real API samples:
- At13:00:29: LeagueOne552records6.08seconds; Ireland180records5.80seconds; Sligo comparison4.53seconds.
- At13:10:43: LeagueOne5.19seconds; Ireland3.41seconds, all season data and browser checks pass.

These are observed request durations, not guaranteed instant loading. Further optimization of the global rich-metadata scan is possible; do not claim sub-second whole-season responses. A slow lookup WARN diagnostic records counts/timings without secrets.

An isolated PostgreSQL17 test (ephemeral CI credentials, never the production DB) used4000rows/96,248,000metadata bytes and552 requested IDs. The previous union-regex read took2.092seconds; constant extraction0.676seconds. Eleven PostgreSQL legacy/multiple-reference cases plus wrong-family/prefix cases passed. These synthetic scale numbers are not production latency claims.

A canonical-label acceptance fallback was added to preserve exact pre-C16 public records rather than forcing an existing Waterford label to become WaterfordFC just for a new native comparison. Final actual tests used this fallback ZERO times: all returned season rows matched native observations after public-key reconciliation. No canonical score/name was rewritten to satisfy the audit.

## Exact tested sources and release chain

C15 bases: backend2c69cc00bdede9b1735e38d162bceaecdd6e73e6, frontend35906e1bde4f5bdba3eb79d6c4c9854093339cd9.
Backend chain: initialC16d9912fd619ff23d0702aa946ee03424f7fbbbc59 -> firstreadfixd253c71a9f3d63909aaf3c40355aa345334be609 -> final52272139d4ecaffbe84cc4709e25c0b0ed3abb56.
Frontend chain: C16c86f6656bf7d40e9e7b2d0ec10b136896d6814f1 -> finalmobileCSS0b26a18f5a1d0a5b8ccc8adc57b8c9d5d17d2f13.

Preflights saved BEFORE each corresponding write:
- `CHECKPOINT_16_RELEASE_PREFLIGHT.md`, commit2f3bac0c1dad097d05332014eb059b82cc57c5f4.
- `CHECKPOINT_16_READ_PERFORMANCE_PREFLIGHT.md`, commit401b2c49701fdb59514f3d134d51c739a6cfd330.
- `CHECKPOINT_16_FINAL_READ_PREFLIGHT.md`, commit66ced7389a1e8d23be879f3cf54b2e487edf0c4e.
- `CHECKPOINT_16_MOBILE_LABEL_PREFLIGHT.md`, commita40eb800662fdcf65cb1b3783f0dfe75f7b4c306.

Core backend runtimefiles: app.py, collector/competition_hub.py, football_history.py, provider.py, detail_enrich.py, fotmob_rich.py. Core frontendruntimefiles: CompetitionHubPanels, HeadToHeadPanel, competitionHub.js, useScopedResource, CompetitionStandingsPage, MatchCentre, competitionHub.css. Later lookup and mobile fixes are limited to these already reviewed areas.

Final backend full gate **36137624264:921tests,0failures/errors/skips**, all866C15 cases retained plus55new, actual native replay and PostgreSQL-specific scale/legacy checks. Artifact10864758041 ZIP SHA256 `09c2b77deef9719f8e0fce62bf1044cd7657bd2de6128b7420bfe65bacc8f740`; exact6483byte final forward patch SHA256 `2bdabec07272b17f97f240dff38bf9adda8c7fffa9e1a67702af370d029e009b`. ZIP/JUnit/source/per-file hashes independently checked.

Frontend full core gate36132871079 **288tests/buildPASS**, artifact10862266922 ZIP `f809824c6742f3aa1e9fe31e8b3355a66031df60a9f49106ca14989366263ee4`; full corrected source.patch `050912e9dcaf3a0140dcff9f2f2ed8ccb2bbab5134c41974dee5097d21c8618c`. All270C15 cases retained plus18new.
Final mobile gate **36138707352:288tests,0failures/errors/skips+buildPASS**; artifact10866135377 ZIP `10270d7f873f30ee683f6a70c4c33c7a6210daf9191038fea785ee984ecd923f`. Exact mobile patch `54d04b8e160fd0647d791062b05fa686d2fc00307ad2d8badeb393fa9fe8e899`; final CSS `28c35558d6a1ec710eda1db6ff129b6d54637deaa45d7094132da2c8efd4ff04` matched independently.

All full gates installed real requirements. Local full backend collection lackedfeedparser and local offline npm lacked a cached dependency; no stubs were used or local full-suite success claimed. Focused local tests and full actual CI results are distinct.

## Final production evidence

All listed final artifacts were downloaded, ZIP integrity/hash checked and actual JSON/screens inspected. Browser tests use real deployed site/API, no mocked response interception.

Run **36138186962**, auditheadf78ffaa345eb90fa365dbdf6f0a6dc3940a914ef, **all3jobsSUCCESS**:
- Competition/history10865469504 SHA `3c88aaad379d6dc983dfa50e6e40f2921e971fe0c5ebeb44edbb24bbe24c90ea`:6APIchecks and3full responsive journeysPASS;552/180seasonrecords,57/1H2H,912IDs retained.
- Live/mobile10865519919 SHA `773998cf5541344c70b1c9d910bb58654d75b916b00e394a3771e21aeb694353`: previous10finals,56/272,8actualrefreshphases andmobiletablesPASS.
- Rich/home/player10865244842 SHA `d5ef4ca3d65439ab39755dc28c2a38c2d9fbdbd373b10e6c1aeb1a343f918beb`: priorrichmatch/home/player/club journeysPASS.

Run **36139252404**, auditheadf4552f13c1bec442aed05eeebc94c4645a54606d, AFTER finalmobiledeploy, **bothjobsSUCCESS**:
- Polishedfullcompetition/history10866291626 SHA `617f22e38ab5056e32575d69926605eba6c316e6352ccbfbac43ab88baa73fc8`: full6API/3UI journeys repeatedPASS, explicit measuredmobilelabelgeometry andscreens, same552/180/57/1/912 results.
- Actualfuturecomparison10866600352 SHA `49ec812c6d1249e4a1939f0fc5dd9598d8f02f43a86951925e0add8369e4a72b`: futureDundalk/Bohemian57prior/form5each,26/13/18, all3Fixtures->H2H journeysPASS with no fakefullmatch navigation.

Captured original native source evidence36129893421/artifact10861511746 SHA `6e276903be4fdb212d6a8b59a31133af57f2bf1cbef1ff85df26e5a734ea5e55` remains available. Isolated replay of those bytes is not substituted for the final live-site checks above.

## Failed checks retained honestly

Initial frontend36132640567 failed two NEW cancelled-match assertions. The general finished-status helper includescancelled; runtime bucket/status rendering was corrected before publication, without weakening tests. Failedartifact10862596896 SHA `35692889d19a8701d7a5f9c2a0b520104d6b44f24a4317c7bc6142460cd0a65e`.

Initial actualC16run36133968162 failedseason/history timeouts; artifact10863435018 SHA `f6222a3f17c2134d2c3a3daa67f0dd171534d3a0182bffbc3512c8259ace1ca5`. Previous-score artifact10862904841 SHA `5ecb3f9426f4c7b8f5615630047b23d11f0573220a6bd8045378d6cbe0d44503` includesone richdetailtimeout and a loading-skeleton readiness problem. Mainboard912 was not erased. Final readiness requires an actualhrefanchor, retains score assertions.

Firstretry36135730558 started12:35:12 beforeAPIreplacementSUCCESS12:35:28, causinginitial502s; artifact10863832365 SHA `01e2175d6a10fe8f4bfd8cfa6b133634b09dba59abd63c899720e3cef860aa11` retained. Laterretryafterdeploy stillfailedLeagueOne45sectimeout andSligomatchscope; artifact10864441373 SHA `a38b093ca8be02a09009880e4389e381153b7958fd94bdf46b838f9e44150aaf`. These failures were resolved by the finalconstant-query/public-key code and rechecked, not called successful at the time.

Intermediate backend905testgate36133321339 artifact10862608126 SHA `0d2613b2ab7fba2c95b78ab3560f40f092a1e68a3535955a1e4b8dff6ac8b977`; firstperformance919testgate36135197194 artifact10863381646 SHA `4a1dc5134908dbdcf42cce6db492a5af82ab6416a21c24eb2545c4610b5a0b7f`. InitialsyntheticPGimprovement was insufficient inproduction; finalactualnumbers above supersede it.

## Remaining work / exact next steps

1. This generic centre exposes validated available schedules/history; complete native season coverage for every league/group is NOT proven. Composite divisions need explicit source-scoped fixtures, not guessed A/B labels. Continue expanding verified examples beyond the two complete seasons and currently retained UEFA/ASEAN groups.
2. Supplemental fixtures do not yet all have canonical MatchCentre records. Keep explicitH2H working, but do not fabricate full-match links. Any future accepted import must use the ordinary identity/score pipeline, preserve manual/retired restrictions and current912mainboardIDs.
3. The38 empty table scopes/Toppserien and mixed LigaMX scope remain C15 backlog; C16 did not perform a new152-competition table-count audit. Do not relabel the historical114/38 counters as freshly measured coverage.
4. OldSligobb407 alias and Myanmar d807549bf94203765dd7/source6233017 remain open. ProperSligo8ea's newcentrelink is working; underlyingoldaliasisnotfixed. Readactualproofbeforechangingidentity.
5. Transfers/fees/valuationhistory, squads, fullplayer/clubhistories, competitiontopscorers, knockoutbrackets, realshotmap andsecondary-source missingdetails remain. Existingplayerfacts/marketvalues are preserved, not expanded into a globaltransferfeed here.
6. Continue performance work ifneeded: currentwhole-season requests were3.4–6.1sec inmeasuredsamples,notinstant. Preserve constantPGextraction andcompletehidden/legacychecks; do not reintroduce per-ID rich-TEXTscans or cache stalevisibilitypermissions. Maintain real source-to-screen latency audits separately; C16 is not a new guarantee of five-second sports results.
7. Newsfreshness/thumbnails and desktopprimarynavoverflow remain known; homepage stays news-only. Assetsnotgloballyauditedinthispass. No publiclaunchuntilcorecomplete/stable/end-to-endtested.

Next session: read this and newerissue6comments, verifycurrentmain/masteranddeployedhashes, retainworkerdrain15, fullC15testselection PLUS test_c16_competition_hub.py and test_c16_identity_lookup.py. Do not blindly replay audit patches or reset data. User prefers durableGitHub checkpoints, not downloadablebackupbundles.
