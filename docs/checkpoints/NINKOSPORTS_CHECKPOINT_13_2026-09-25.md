# NinkoSports checkpoint 13 — 25 September 2026

## Resume from these deployed revisions

User requested the functional depth of a serious live-results service in original NinkoSports design, not disconnected widgets. C13 implements and verifies a connected football Match Centre improvement. It is NOT a declaration of full Rezultati.com parity, full football coverage, or all-sports completion.

Backend main/deployed: **43bf5a54d280ee7bb2b07f75bd8fe7ba7c62f7c9**.
Frontend master/deployed: **1889513abda991fd836f4e8dee08f2ef8da9c179**.
Preserved chain: C12 backend50cad8107e23ee9e830f730b18c13a32f4ce7575 -> initial C13 6252e64af7e06659909c402e36636a5de386b31b -> final43bf5a54; frontend4355aa22a26036376fa86f018b6c838424b7eff2 -> initial50e90628178e4ef1cdb242d7fca4b798fa525d31 -> final1889513a.

Final Railway terminal SUCCESS and exact hashes observed:
- API b94c2093-fde4-4eda-bbe5-7c3cd0f394a5 at07:19:49.682Z.
- Results-worker166085ae-271c-4801-b5c5-0051e84c7625 at07:19:41.716Z.
- Frontend429a9108-980c-4242-9dcc-dc9c57f36c85 at07:19:55.766Z.
Backend project17f6ebff-0f6b-42dd-be86-35ca9ca40301/envcb27d851-9198-47c8-a733-8356e8b6cf63/APIservicec08822c6-e602-4f32-a2bc-87aedbbe9b05/workerservice2c89eecf-b094-428a-8f7c-9642605a6baa. Frontend projectd2187a78-90d0-437a-871b-10e16ba8d07c/env52ceaa71-df43-4275-9ebe-6c19d4437461/servicedf4b231a-fcbc-4d89-bef8-d9028d03b473.
Only reviewed non-force fast-forwards through existing integration. No RailwayAgent, DB reset/manual score commands, new service/scheduler, variable/config changes, forcepush or unrelated stagedpatch acceptance. Earlier score/visibility/alias/manual restrictions, group tables, artwork and live sidebar preserved.

## Implemented, connected improvements

Native detail parsing now retains actual incoming/outgoing substitution names and player identifiers, supplied added time, and AFTER-goal scores from newScore rather than prior homeScore/awayScore. Period statistics drop empty section headings and duplicate metrics without dropping real zero. Individual supplied shots are retained instead of reduced to an integer; shot xG zero remains distinct from unavailable. Native verticalLayout supplies player positioning; numeric formation-slot IDs are not displayed as invented position names. Unknown formations remain rosters, not guessed4-4-2. No false confirmed-XI inference.

Previously cached rich detail can refresh through existing on-demand enrichment. Replacement requires exact match ID, oriented literal names and kickoff within60s; only supplied nonempty verified fields replace prior content. Targeted detail revision1 and15-minute failed-check backoff avoid a global parser reset or new schedule. Failed/empty requests retain rich cache. No scoreboard status/score/visibility/fingerprint/publicID changes are made by this enrichment patch.

Match UI has a chronological football story, all/key-event filter, real substitution names, player links, correct90+4 added time and post-goal scores. Statistics switch match/first/second half using supplied rows. Shots show the complete supplied list with team and goals-only filters, outcome, time, player and xG; this is NOT a graphical shot map. Supplied formations/positions guide the pitch. Tabs persist in the URL; opening a player and returning restores the same tab. The explicit request envelope permits a valid canonical old-link response while contradictory/stale wrong-match envelopes remain rejected.

An actual player click exposed an existing backend NameError: __names_equivalent was defined, while callers used _names_equivalent. One function rename repaired team/player fallback without broadening identity matching. Eight new positive/negative tests cover literal names/IDs, unknown names and hidden/alias exclusion.

Visual inspection exposed roster names at0px width because nested grids squeezed the whole player button into34px.43 scopedCSS lines give each button full row width, readable wrapped names, visible kit numbers/ratings, proper48px desktop/40px mobile headercrests and a centered1100px desktop Match Centre. Overview groups timeline and match facts deliberately; scorehub styles are unchanged.

## Exact code gates and source verification

Initial backend gate36104191331 passed796 tests; initial frontend final gate36104709746 passed234 tests plus build. Their independently downloaded source patches and file hashes matched reviewed local code; detailed records are in CHECKPOINT_13_RELEASE_PREFLIGHT.md at44003e2ce39a010034c7b976664633400437e59f.

Final backend forward gate36105897098: **804 tests,0failures/errors/skips**. Artifact10851136331 ZIP SHA2564fca07135319050a23c1f768ad1eea6c14d69279ed2e7954c9b59d8f740a3e22. ZIP/JUnit checked; source.patch byte-identical to local82ec65057e7ad282c06e41c9ef6bfa7e15cc107a6026b52ed7240eccadf641ae, both runtime/test filehashes match. Candidate43bf5a54 was freshly ahead3/behind0 against initialC13 before release. Branchfix/entity-navigation-c13-20260925.

Final frontend forward gate36106721185: **234 tests,0failures/errors, production build and measured candidate Chromium checks at1440/390/320px**. Artifact10851322055 ZIP SHA256f8e876631ae8cc6602ef5d20ff8179885160796910d9f41f41c187d67e6f6a7b. Exact source patch86b5a0610d29732bba797cfe2874180a98ea974daa5c6d3f1d284e5fbe94422f equals local; CSS hashca97e5a4189fe8571bc5490d662e2cf4c87c99732662d17b05675406eb9435dd matches. Candidate1889513a freshly ahead5/behind0. Branchfix/match-layout-c13-20260925.
Candidate CSS was injected only into a read-only browser BEFORE release; final acceptance below tests genuinely deployed CSS with no injection. The forward preflight was saved before production changes at8ea6928b2de694aa82d504d9b0f8c7068bb329d5: CHECKPOINT_13_FORWARD_PREFLIGHT.md. Do not replay staging scripts on already patched refs. Future backend gates must include C13 detail/entity tests as well as prior selection; do not assume the old permanent selection automatically includes newly added test files.

## Actual final production acceptance

**Run36107167149, both jobs SUCCESS**, audit commit0302a64fde579d530afab19349951cdcb11b5398, workflow .github/workflows/c13-final-acceptance.yml. Executed acceptance scripts are saved inside artifacts, including stricter geometry and network checks. This is a read-only public verification workflow, not a deployment blocker or background monitoring promise.

### Match data, navigation and presentation
Artifact **10851487541 c13-final-detail**, ZIP SHA256 **86dd6789debacf8155aa330fe4610b879b64cf74d6f7bee2ca929e9620a8ed03**. Downloaded, ZIP checked, actual JSON and desktop/mobile screenshots reviewed. Snapshot07:21:23.826737UTC.
Sligo canonical ninko-evt-8ea488bb6f0bcf5038b7 versus fresh native source5100971: **10 named substitutions,37 unique statistics,22 individual shots,22 supplied pitch positions, correct goal-after0–1**, repeated public score/identity unchanged. Both half-stat switches show the corresponding37 supplied rows, not duplicate headings. Actual desktop and390/320px tests passed timeline filters,90+4,all22shots/team/goals filters,22pitchplayers,tab URL/reload and no tested overflow/JS errors.
Desktop actual player route Aidan Keena from shot event returns a populated player page and Back returns to the original #mc-shots tab. This is a proven specific journey, not every player history being complete. Team API no longer raises NameError and returns Sligo identity, but the sample reported results0: **team history is NOT complete**.
Actual deployed roster name minimum widths **382.5px desktop,218px at390,172.375px at320**, replacing the observed0px baseline. Desktop page width1100,left/right170px at1440; crest48px desktop/40px mobile. No CSS injection used in final checks. Delivered bundle **index-DyC7UGIr.js**.
Andorra old URL ninko-evt-86345b6cb47a7c4b8524 now actually renders the canonical FT1–2 Match Centre on mobile, including rich sections; original alias lookup was already correct and C13 fixes frontend acceptance of it.

### Previous scores, polling and tables preserved
Artifact **10851996560 c13-final-preservation**, ZIP SHA256 **21dc2521aa3c2efd84b22caeb67597901529bc5438a9bf6b397763faf60ae754**. Downloaded/ZIP/JSON checked. API07:21:32UTC: **all10 previously checked finals correct**, Andorra oldlink correct, futureHavelse present scheduled03:00Sydney with nullscore/notHT/live. SydneySep25football56/Sep26football271, identical football-only and all-sport football ID subsets. Compared with initialC13 preservation snapshots: exactly same56/271 IDs,0removed/0added in those two tested date windows.
**All8 actual browser phases pass**: initial and after55seconds at1440 plus390/320 for both dates. Friday observed6successfuldelta polls and1successfulfullrefresh; Saturday4delta polls and1fullrefresh. NoJSerrors/overflow. Full board counts remained56/271 during checks. These are snapshots, not world completeness or zero upstream latency. Final delta sample26rows/onepage/nottruncated, no retirement observed; multipage/tombstone correctness remains unit-tested rather than claimed observed here.
Existing mobile standings/group-switch/active-tab checks passed320/390/1440 through07:23:46.821483UTC, compact/full columns and correct group switching retained.

## Failed checks retained and corrected honestly

Initial UI gate had a syntax error in a NEW test setup; corrected without removing its assertions. Initial deployed detail run36105122497 passed native data and mobile interactions but FAILED the desktop player page; fixed by the actual NameError repair above.
Initial visual gate36106176306 waited for the known zero-width name to become visible before candidateCSS. Readiness changed to actual loaded pitchplayer, preserving all geometric assertions. Subsequent candidate and actual production tests passed.
**Correction to preliminary forward-preflight wording:** actual initial score-preservation JSON in c13-preservation-first.zip reports **6/8 browser phases**, not7/8: both initial desktop snapshots failed while placeholders were loading, both after-poll and all mobile phases passed. Friday's screenshot directly confirmed skeletons; Saturday initial also failed and remains recorded. All10 API checks passed. Final test replaces both .score-row readiness selectors with actual .score-row-link and adds mandatory successfuldelta/fullrefresh checks; no score/identity assertions removed. Final8/8 result above supersedes these failures. Do not repeat the preliminary7/8 count.

## Still open and next work

- Myanmar–Timor-Leste d807549bf94203765dd7/source6233017 still publicly scheduled1–0 versus known sourceFT2–0. This exact public defect was rechecked07:21 and is not fixed by detail parsing. Resolve parent/group cross-provider identity with evidence, not a static score override.
- Sligo OLDbb4071086c3ea042f6e9 still scheduled/null; canonical8ea488bb6f0bcf5038b7 isFT0–1 and is the rich Match Centre tested here. Its unresolved DB alias is distinct from the fixed valid-canonical frontend envelope handling. Do not call oldSligo resolved.
- Latest broad11-date metrics were C12 historical06:10:2698public/198strictunresolved/84agedscheduled; C13 did NOT rerun that entire coverage audit. Never present these as current or equate strict-unresolved with missingfixtures.
- Team histories/squads, complete player histories, competition season/group depth, broader source-rich detail, real shot-map geometry/orientation and other-sport-specific views remain open. Review small text polish such as provider-prefixed assist descriptions; current change is not final UX perfection everywhere.
- Broader assets/coverage remain subject to prior gates. Do not hide missing data with invented results, badges or formations. No new paid services/agents without approval.

Full coherent product completion requirements are saved at docs/NINKOSPORTS_PRODUCT_COMPLETION_STANDARD.md (296bc721f206c62b853ed30bc40442ca3ff9e567): one connected date/filter/match/team/player journey, sport-specific data, original consistent design and genuine source->API->browser acceptance. It is a roadmap, not implemented-everything evidence. User wants GitHub checkpoints, not downloadable backup bundles. Next session read this and later issue6 comments, verify refs/deployments, preserve completed work and prioritize remaining score identities before expanding claims. No public launch declaration until stable complete tested core.
