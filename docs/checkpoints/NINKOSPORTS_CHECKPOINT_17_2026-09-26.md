# NinkoSports checkpoint #17 — 26 September 2026

## Status and scope

**This is the latest completed handoff.** It supersedes checkpoint16 and C17 WIP/preflights as the current-state record. The bounded category/scorer/profile work below is deployed and has passed actual production acceptance. **Football as a whole is NOT complete; this is not a public-launch signoff.** Keep issue6 open.

User requested continuation of unfinished football rich details, tables, old links, transfers, scorers and brackets, and specifically reported mixed men's/women's football. This pass addressed the category incident and implemented verified season scorers with working player/club navigation, while preserving prior score and identity protections.

## Exact production refs — actually deployed

- Backend `macamala/allball-backend`, main: `cf192f22da637b9b54495cd5fc2ba238abbfbee3`.
- Frontend `macamala/allball-frontend`, master: `9a9d1cc996f746a63d4716043b849a7b12e57538`.
- Backend API deployment `7a1b9c48-d901-49b9-afbe-fe5aa7d16c4b`: SUCCESS, 2026-09-26T04:17:22.138Z, exact backend SHA.
- Results-worker deployment `895c2984-96b8-4bf5-8b3a-5fbbbeca68ad`: SUCCESS, 2026-09-26T04:16:53.146Z, exact backend SHA.
- Frontend deployment `99ecb805-db14-4af8-9316-3074aeaa5a22`: SUCCESS, 2026-09-26T03:46:03.417Z, exact frontend SHA; freshly rechecked after final acceptance.

Backend Railway project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`, API service `c08822c6-e602-4f32-a2bc-87aedbbe9b05`, worker `2c89eecf-b094-428a-8f7c-9642605a6baa`. Frontend project `d2187a78-90d0-437a-871b-10e16ba8d07c`, environment `52ceaa71-df43-4275-9ebe-6c19d4437461`, service `df4b231a-fcbc-4d89-bef8-d9028d03b473`.

All production updates were reviewed normal nonforce GitHub fast-forwards after isolated gates. No Railway Agent, unrelated staged changes, service/settings creation, DB reset, manual score mutation or force push. Existing worker-only draining15 seconds and owner-safe scheduler shutdown remain intact.

## What changed and is actually verified

### Men's/women's identity and board controls

Football board now provides All football, Men, Women and Unclassified controls. All deliberately includes both known categories; it is not evidence of incorrect league assignment. Selection persists through the URL/reload. Unknown evidence is not guessed to be male.

Verified category metadata is carried consistently through list/detail/public live deltas and competition identity. Female label variants such as Femenil cannot silently resolve to a men's competition. Existing records with old male competition keys are handled by guarded read-side projection/scope candidates, not broad destructive relabeling. Three season hub comparisons now tolerate the (W) decoration only with verified female context and oriented native identities.

Actual production example: `football-mex-liga-mx-femenil-apertura` now returns18 records; previously its board was separated but its hub was empty due old stored keys. Male `mexico-liga-mx` hub returns151 records. The six women's events in the control window occur in the women's hub and none in the men's hub. This is not a claim of complete worldwide women's coverage or complete femaleMX table/scorers.

Norway `football-nor-toppserien` retains132 source season records,10 canonical detail links and all6 control-window canonical links. These are existing season records retained/correctly linked, not132 newly created full-detail matches. Known detail `ninko-evt-20117688e59bd5e8ef68` remains the same female event and competition.

### Verified season scorers and navigation

A season/group-scoped scorer endpoint and competition Top scorers tab are deployed. The UI supports team filtering, show-more pagination, player photos/club logos, player links and appropriate return navigation. Wrong/unsupported seasons or unverified group scopes do not silently receive another season/group's leaderboard.

Actual public rows were compared one by one against separately fetched native league/leaderboard data, including season, playerID/name, teamID, goals and penalties:

| Competition | Season | Verified rows |
| --- | --- | ---: |
| Ireland Premier Division | 2026 | 139 |
| England League One | 2026/2027 | 139 |
| Norway Toppserien, women | 2026 | 118 |
| Mexico Liga MX, men | 2026/2027 - Apertura | 124 |

FemaleMX composite scorer scope remains unavailable (`verified_scorers_not_available`); no male/group substitution. Do not call global scorers complete.

Previously unrepresented scorer players can resolve only through exact verified competition/season leaderboard identity, not an arbitrary numericID or name. Match appearances are not fabricated from season totals. Frontend carries that competition/season into player navigation and returns to the same scorer tab/season.

Actual end-to-end journeys: Tom Lonergan1263510 -> Waterford6042 -> same Ireland season leaderboard, and Katarina Dybvik Sunde1090170 -> Aalesund4500 -> same Toppserien season leaderboard. Native/current public clubs, names, IDs and categories all match. Both new profiles legitimately have0 locally recorded match appearances; their verified season/career facts remain separate.

### Player dates and same-name club safety

Actual female player data contained Unix millisecond career dates, which caused string slicing TypeError and discarded otherwise valid profile facts. Optional date normalization now handles explicit ISO/Unix seconds/milliseconds, leaves invalid/missing values null, and preserves actual club/birthdate/position/career/season fields. Katarina's three career entries now survive, including Aalesund start2025-01-01 and Åsane2021-03-01 to2024-12-31. This is not a completed transfers/fees system.

Actual women's club4500 had been merging a men's Aalesund8404 result by shared name. Club histories now use verified exact-ID category anchors, exclude opposite-category namesakes, fail closed on contradictory anchors and preserve unknown rows only when exact IDs support them. Same-category multi-provider joins remain supported.

Final Aalesund(W) public profile is female/Toppserien only, with exact events `ninko-evt-502d99d773c36f1850cd` and `ninko-evt-99b63e4a2de717c9139b`. Male result `ninko-evt-ec2a4f24cf1238071ecd` is excluded from that profile, not deleted from storage.

A final actual API check found Waterford6042's merged team dictionary could carry alternate-provider ID138034. A two-line correction retains a requested ID only when that ID was actually observed on an allowed participant. It does not invent an ID for name-only fallbacks. Final native/API exactID6042 matches and existing histories remain.

## Final completed gates and downloaded evidence

Final backend retained football regression selection: **1008 tests, zero failures/errors/skips**, actual gate `36217227062` SUCCESS plus exact captured Waterford fixture replay. Artifact10897917662, ZIP SHA256 `72f9898156d89e2d2d11e67fb3bc096207bc87804a2863911b8f1df15ed4b983`. Actual JUnit, candidate and runtime/test checksums inspected; source patch SHA256 `0d4a1f1bb14da43671e7ea7ac788d0b9cc915a2868a834a9c48ce5b0cf829c29`. This is the retained regression selection, not a claim that every unrelated repository test was run.

Final frontend full suite: **296 tests, zero failures/errors/skips, production build passed**. Gate `36215479867`, artifact10896859278, ZIP SHA256 `bf0d1f6121d3935e4038bcc8d6049bbea31e605c164f4fc34cd3e924f6e0db36`. Exact frontend unchanged afterward.

Final actual production workflow **`36217353717`**, audit head `8fbbe8965c55a129bac9819223e1f91a322a8d24`: all three jobs terminalSUCCESS — categories/scorers/profiles, retained live/mobile, retained rich/home/player. No mocked browser/API responses.

| Actual final artifact | ID | ZIP SHA256 |
| --- | --- | --- |
| c17-final-categories-scorers-profiles | 10897168511 | 3b45074b73e2862ae39493c537d42375e8a628ff038e93846200cdb48e37f655 |
| c17-final-retained-live | 10897253483 | 513a7dd3a762da07917cc16b8c4118abf705e5862cbc6e756d3a872f4ffba624 |
| c17-final-retained-rich | 10898052619 | d3621a04f88369df40ee3da800f10de5f6bbd9febf545c006adea0f66e4fd744 |

All ZIP hashes/integrity checked, actual reports parsed and representative desktop/mobile screenshots inspected. Category acceptance.json SHA256 `4d74edffdbccf8fa0fa47c984ea9552edcac18873b755fcaf870c80bf39c4a28`.

### What final public acceptance proves

- Fresh pre-release control snapshot at2026-09-26T03:19:07.753293Z, SydneySept25–28: **912 canonical IDs before,912 after,0 removed,0 added** at final category snapshot04:17:37.222465Z. This proves ID retention for that window, not correctness of every historical score.
- Categories:777 men,117 women,18 unknown. Separately captured native oriented identities matched838 events (725 men/113 women), with no category mismatches. Unknowns remain an explicit unfinished classification item.
- Actual Chromium widths1440,390,320 all passed category filtering, reload persistence, scorer pagination/team filtering, player->club->same season return, and women's fixture->correct match ID/header. No JS errors or page horizontal overflow. Women's fixture navigation is not a claim that every such match has full rich data.
- Final category UI day snapshot:276 rows total,226 men,46 women,4 unclassified. The retained score audit's earlier/cached day snapshot has271; do not substitute either day count for the invariant four-day912-ID proof.
- Retained live API:57 Friday and271 Saturday rows at that audit snapshot;10 expected finals verified; Andorra alias correct; Havelse source-verifiedFT1-3;136 delta rows, one page, not truncated. Eight real browser snapshots passed, including actual55-second status-delta and authoritative events polling200 on both checked dates. No JS errors.
- Retained Nations League standings at320/390/1440: proper group switch, active tab visibility, compact mobile/full desktop columns and no page overflow.
- Retained Sligo rich example:37 statistics,10 substitutions,22 positions,22 shots;0-1 score unchanged after repeat detail reads. Existing player navigation, profiles, home rail and responsive checks passed. These are regression witnesses, not new global rich-detail completion.

## Earlier findings/failures retained honestly

See `CHECKPOINT_17_RELEASE_PREFLIGHT.md`, `CHECKPOINT_17_FOLLOWUP_PREFLIGHT.md`, `CHECKPOINT_17_IDENTITY_PREFLIGHT.md`, `CHECKPOINT_17_EXACT_ID_PREFLIGHT.md` for exact intermediate refs/artifacts. C17A public QA found empty femaleMX hub/new scorer profiles; C17B found numeric career dates; C17D found exact club dictionary ID mismatch. Each was reproduced, corrected, gated and then passed final public QA. Do not treat earlier failed runs as successes.

Harness corrections: old retained scripts had to be restored from saved audit.tar.gz; actual-row waits replaced skeleton waits; obsolete future-Havelse assertions were replaced by independently verified native final and pre-release snapshot proof; full-season women's fixture links use full hub rather than four-day cohort; club headings use native club name/ID rather than assuming player's short club label is identical.

Exact-ID first gate36217040631 had1008 tests passing but replay omitted stored source provenance and failed. Replay correction requires native league126 fixture5100970 to match oriented IDs4131/6042, kickoff2026-09-18T19:00Z and3-2 before restoring only witnessed provenance. No production mutation or relaxed category check.

Havelse `ninko-evt-d0203f3635ffe7d1db45`, native5905914, kickoff2026-09-25T17:00Z, was alreadyFT1-3 before C17. Never reset it to scheduled because an old test expected03:00. Existing future-precreated-result unit guards remain intact.

## Still open — do not relabel complete

1. Full match-centre linkage, lineups/statistics/timeline and sport-appropriate details for source-only season records. A schedule/result/H2H or route/header alone is not rich-detail completion.
2. Remaining empty/composite tables and old incorrect match links, especially Myanmar `ninko-evt-d807549bf94203765dd7` and Sligo `ninko-evt-bb4071086c3ea042f6e9`; keep correct Sligo `ninko-evt-8ea488bb6f0bcf5038b7`. Recheck source/time/score before retiring aliases, never blanket hide/restore.
3. Complete transfers/fees, value history, full squads, global season scorer/group coverage, knockout brackets and remaining real asset gaps. FemaleMX unverified scorer/table groups must not borrow male data. Eighteen unclassified control-window events need actual category evidence.
4. Additional duplicate/source-link audit: Waterford profile still retains records `ninko-evt-8e5a5f6946d1e7930160` and `ninko-evt-9d143a2da705ba814e14` under two competition aliases; their potential duplication needs separate exact kickoff/source reconciliation. C17 fixed the profile ID/category, not global record dedupe. Do not silently delete either from a name-only inference.
5. Other sports coverage, global logo/flag completion, news freshness/desktop navigation and the rest of earlier backlog. AI subscriptions/community/fantasy remain later phases; core completeness and tested end-to-end release gate stand.

## Exact resume procedure

Read this checkpoint and issue6 latest comment; fresh-read main/master and actual deployments first. Do not restore oldC16/C17A source over accepted C17E. All actual runtime changes are committed; no hidden local WIP is required to reproduce this state.

Keep football first. Next group: remaining wrong source/old links and season-only match-detail joins, with exact source identity/time/score proofs, then missing group tables/brackets/transfers/global scorers. Preserve all prior category, explicit-ID, result, retired/manual-hidden, date snapshot/delta and scheduler guards. Review broadly but release bounded tested changes. Record failed witnesses and exact candidate SHAs before any production ref update.

Final QA lives on this audit branch: `audit/c17_public_acceptance.py`, `audit/c17_final_acceptance_prepare.py`, `audit/c17_final_identity_acceptance_prepare.py`, `.github/workflows/c17-final-public.yml`. Preparation order is categories then identity extension; live preparation independently restores the native final witness. Existing retained scripts are in run36205878806 artifact10892589996 audit.tar.gz. Baseline run36214428569 artifact10896807899; native categories run36205878806 artifact10892589996. Artifacts expire after30 days, while committed source/tests/checkpoint and exact evidence summaries remain durable. Do not promise archival retention beyond that or claim a DB backup was taken.
