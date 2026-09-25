# NinkoSports checkpoint 14 — 25 September 2026

## Resume here; preserve C13 and all earlier fixes

User requested football player clubs/market values/career and substitutions; faster live results and visible advancing match time; Nations League groups adjacent with major competitions first; HOME NEWS ONLY, particularly on mobile. This pass implements these bounded improvements and tests the deployed site. It does not establish full Rezultati.com parity, complete global/player coverage, or that the user's particular four-minute delay is eliminated.

**Backend main/deployed: 0a73c89653d24ca4c84da43b91dae3bfd08f7030.**
**Frontend master/deployed: 5e65eca2a43939859e010182ba187f68ea74e3bc.**
Preserved backend C13base43bf5a54d280ee7bb2b07f75bd8fe7ba7c62f7c9; frontend C13base1889513abda991fd836f4e8dee08f2ef8da9c179 -> C14core39604cfc6caa051e934d8d6a97dfa0fd92280807 -> finalprofile5e65eca2. Do not replay integration/staging patches against already applied heads.

Railway terminal SUCCESS and matching hashes observed:
- API8e46ff8f-f6a5-4716-b068-f8c6ec90fd1f at08:16:41.762Z, backend0a73c896.
- Workera57c84b7-dde9-47ca-b56a-8982a834ecb1 at08:17:10.489Z, backend0a73c896.
- Finalfrontend2e621b07-61c3-4c97-bdc9-7240d51eb6e5 at08:45:16.569Z, frontend5e65eca2.
Earlier C14corefrontendb56e11b4-aae6-466e-8945-7cc9320a560a/39604cfc SUCCESS08:16:54.510Z, superseded by profile polish.
Backend project17f6ebff-0f6b-42dd-be86-35ca9ca40301/envcb27d851-9198-47c8-a733-8356e8b6cf63/APIservicec08822c6-e602-4f32-a2bc-87aedbbe9b05/workerservice2c89eecf-b094-428a-8f7c-9642605a6baa. Frontendprojectd2187a78-90d0-437a-871b-10e16ba8d07c/env52ceaa71-df43-4275-9ebe-6c19d4437461/servicedf4b231a-fcbc-4d89-bef8-d9028d03b473.

Only reviewed nonforce fast-forwards through existing integration. No RailwayAgent, DB/manualscore/reset commands, new services/schedulers, paid providers, config/variable changes, or unrelated stagedpatch acceptance. Shared scheduler lease, source backoffs, manual/retired visibility restrictions, canonical IDs and all earlier score/group/mobile policies remain.

## Implemented scope

### Home and competition ordering
HomePage removes the score widget and extra live-score HTTP requests on desktop and mobile. News modules remain; dedicated /live-scores route and existing navigation configuration remain. This does NOT declare article freshness/image completeness resolved.
Competition ordering now prioritizes favorites and editorially significant competitions, with all UEFA Nations League groups adjacent as one sorting family. Group event IDs, competition keys and separate standings are NOT merged. CONCACAF remains separate; English National League is not confused with Nations League. Lower live fixtures do not split major competition families. Group ordering and important-league ordering are covered by regression tests, including input-order independence.

### True update processing and visible clock
The changed-result queue previously missed minute-only changes when score/status were unchanged. Verified live minute changes now enter the existing bounded priority path; hidden/conflicting identities retain cooldown/acceptance restrictions. Hot football refresh runs before slower sport/detail lanes under the SAME scheduler/write lease, and hot-page eligibility is15seconds rather than30. This is eligibility, NOT a guaranteed15second source-to-screen delay. Existing cold/history work remains.
New public GET /sports-data/matches/{id}/score uses the same canonical/source/visibility checks but skips external rich-detail enrichment and history work. Source observation timestamp is exposed as score_observed_at, not guessed browser-fetch time. Internal profile_ref stays private. An open visible live match checks this lightweight score path every5seconds independently of30second rich-detail requests; scheduled nonfinal checks15seconds; finished stops. Request singleflight, visit-generation and older-response guards preserve new finals and reject obsolete A->B->A visit responses. Live detail TTL45->20seconds uses existing network/backoff controls.
The displayed advancing football clock is explicitly approximate (e.g. approx60:02 from a supplied whole-minute anchor), not an exact referee seconds feed. It does not invent kickoff/score/status, is bounded90seconds, stops on halftime/final/suspension, and labels delayed updates rather than running indefinitely on stale data. Clock animation alone is NOT evidence that actual results are fresh.

### Verified player facts and coherent profiles
On-demand player enrichment uses an already verified football native numericID and matching literalname, not broad name search. Namesakes cannot overwrite the selected ID. Currentclub is separate from club at match time. Added supplied contract, birthdate/age, height, position, nationality, preferredfoot, season summary and senior club/career moves. Market values require explicit currency and are labeled estimates, not fees; zero remains valid, future chart dates rejected, unknown valuation dates remain unknown.6hour cache,10minute negativebackoff,256entry cap,6second fetch timeout and in-flight reservation limit cost. Private linkage not exposed.
Team history candidate filtering now happens before the1200row cap, preserving exact final identity checks. Sligo sample returns1historical match, not a complete club history.
Final profile presentation uses3runtimefiles only (PlayerPage,TeamPage,scopedentityProfiles.css): centered1100px desktop, consistent darkcards, readable player/club identity, value immediately beside/below identity, season and career separated from single-match figures. All new value and club controls are visible near the top on mobile. Shared team styling preserves navigation.

## Exact code gates, preserved source and preflights

Core preflight saved BEFORE release: commitb70bef446ee8deafaa48deb883ace99631f86e8c docs/checkpoints/CHECKPOINT_14_RELEASE_PREFLIGHT.md on this auditbranch.
Profile preflight saved BEFORE its release: commit7d30d05af2c9cd95ce1dc40c6f71c14fc6efb7d3 docs/checkpoints/CHECKPOINT_14_PROFILE_PREFLIGHT.md.

Backend complete gate36111726914 SUCCESS **816tests,0failures/errors/skips**. Every C13case retained plus12C14cases. The first805test selection omitted11older canonical/FIBA/Sofa tests; these were detected and added BEFORE release, not waived. Artifact10852859110 ZIP SHA2567f36a6b7e856c867eeaf20443a3300c75d757425a96bde62911c939530ba6b9e independently downloaded/ZIP/JUnit verified.27310byte fullsource.patch SHA256addac8a3a40902018bc2e6d7f388d0187ef5f8ec6b011c569cbb671a7d52a094 equals reviewed local source. Actual requirements installed, no feedparser stubs. Branchfix/football-live-player-c14-20260925. Future gates need the permanent selection PLUS hidden_football_aliases, fotmob_match_centre, entity_profile_navigation, c14_live_player, canonical_detail, fiba_rich_detail, sofa_rich_detail testfiles; do not drop earlier cases accidentally.

Frontend core gate36111518820 SUCCESS **251tests,0failures/errors/skips+build**. Artifact10853148065 ZIP55c023044dfd91775a69686db2cdfaf603256c368983f1afa8a706a34b4b2d15 checked.34436byte source.patch SHA256f937689868f615ecebbda6cdcdde0dd49601a7ac9373dde73503f6960b1e4260 exactlymatches reviewed source,15filehashes checked. Branchfix/news-live-player-c14-20260925.

Final profile gate36114153275/job108004170762 SUCCESS **251tests,0failures/errors/skips+build+6candidatebrowserchecks**. Artifact10854118314 ZIP272dc16b65be7d913ad93420fcc89519611917815a5dace14761ab172fa87de7 checked.11471byte source.patch SHA2563bf0a098bf6cc3991a4eb20eb9b12239a66db6131041b26bd8c993549bb7b341 exactlymatches local code; all3runtimefilehashes match. Branchfix/profile-layout-c14-20260925; candidate5e65eca2 freshahead6/behind0 before FF. Read-only preview used real public API response bytes with only test-local CORS response headers for localhost4173. Production CORS/config was never changed. Candidate is NOT the final production evidence; actual no-interception acceptance follows.

## Final actual production acceptance

**Run36114622778, all4jobs SUCCESS**; audithead ef00a660f1eae121c18974213fb5e90306235976; .github/workflows/c14-final-acceptance.yml. All final artifacts downloaded, ZIP checked and actual JSON reviewed. Final delivered bundle **index-CG-Ytw3Z.js**.

### Profiles, clubs, home and competition order
Artifact **10855125376**, ZIP SHA256 **4089e13c4694d847cdad46e92127ee7345c1015740a014045f3706149e3805dd**. Actual deployed profile test has no response interception/CORS shim.6checks at1440/390/320: player topvalue/career/season/layout plus actual currentclub click, allpass. Desktop profile1100px,left/right170px; mobilecontent366/296px,left/right12. Marketcardbottom335.28desktop/415.28mobile, inside firstscreen;0JSerrors/overflow. Note report player's width field holds contentwidth; paired teamcheck and filenames identify viewport. Desktop/mobile finalscreenshots visually reviewed.
Separate actual UI acceptance08:45:48UTC: **9/9home/player/football-orderchecks PASS**, both nativeplayerfactscomparisons and3lightscorechecksPASS. HOME: no scorewidget,0scoresendpointrequests in everyviewport. FOOTBALL: first5groups adjacent UEFA AGrp2,AGrp4,BGrp3,DGrp1,DGrp2, followed by CONCACAF; separate real56fixtureIDs retained. Native data can change; earlier intermediate snapshot's group labels are historical, not canonical evergreen facts.
Player825815 AidanKeena: currentclub1854 St.Patrick'sAthletic, estimated **EUR62697**, suppliedvaluationdate2026-09-01,13careerentries,8seasonmetrics. Source/public fields agree; rounded UI EUR62.7K. Player1234030 LiamHughes: currentclub6361 SligoRovers, estimatedEUR110988,date2026-09-01,7careerentries; season summaryverified. These are native-source estimates, not transfer prices or an allplayer completeness claim. Clubclick opens /teams/1854 correctly on all3viewports.
Lightscore actual finalmatch reads approx0.35–0.44seconds for thissample; this is HTTPresponse duration on a finishedgame, NOT live delay. OldAndorra score endpoint preserves canonical1–2final.
Controlled clock test is isolated synthetic response data in a separate browser, never persisted:60:00->60:02,3lightrequests approx5seconds apart, thenFT and no furtherlivepoll. This proves display/request lifecycle, NOT real live-latency improvement.

### Rich match journey preserved
Artifact **10854686617**, ZIP SHA256 **3aff2d0ee10e305d86e0b3924980a746a6401dc29702391cdeebb612009fd075**. Actual08:45:36UTC Sligo canonical8ea488bb6f0bcf5038b7/native5100971:10namedsubstitutions,37unique statistics,22shots,22pitchpositions,correctgoal-after0–1,repeatedscore/IDpreserved. All3desktop/mobilejourneysPASS, halfstatrows37/37/37, shotfilters, lineup, playerpage andBack-to-originaltab pass;0JSerrors/overflow. Actual validAndorraoldURL renderscanonical1–2FT. This re-ran after finalprofile deploy rather than relying on the carriedC13 artifact.

### Previous finals, automatic refreshing and mobile tables preserved
Artifact **10854801847**, ZIP SHA256 **7ff42908c0b9a11400c227089f2e933abb3e58f245999403638681228d5ee975**. ActualAPI08:45:50UTC:10previousfinalsPASS,Andorraoldaliascorrect,Havelsepresentfuture scheduled03:00Sydney/nullscore/notHT/LIVE. **SydneySep25football56/Sep26football272**, same football-only and allsportfootball IDsets. Exact comparison with earlyC14pre-polish snapshot retains all56/272IDs,0removed/0added. Not whole-world coverage.
**8/8browserphasesPASS**, initial and after55secondsdesktop1440 plus390/320bothdates. Friday observed7successfulstatus-deltapolls+1fullrefresh, Saturday4+1. Actualanchor readiness excludes skeletons; successfulpoll/fullrefreshmandatory.0JSerrors/overflow. Finaldeltasample14rows1page/nottruncated,0retirementsobserved; do not claim multipage/tombstoneobserved from thissample. Existing compact/full tables, correctgroupswitching, active tabs pass320/390/1440 through08:48:09.826642UTC.

### Actual source timing — important unresolved limit
Artifact **10855090989**, ZIP SHA256 **f85a7ebe744bd11d728976dd18af58a0bed10455e567f0386b615b797dac9692**. Three simultaneous native/public samples08:45:13.928890,08:45:39.459016,08:46:05.225280UTC: allHTTP200 and **ZERO active football fixtures in either source or public sample**. Earlier07:49–07:50 and08:19–08:20 samples also had0activefootball. Therefore the reported4minute live delay is **not empirically verified fixed**. Ask which match the user compared; measure source minute/score/observation timestamp, worker receipt, lightendpoint and actualbrowser on that activefixture.5secondbrowserpoll and15secondhoteligibility are policies, not latency guarantees.

## Failed checks retained honestly

Initialcorepublic36112245797/artifact10854085016 failed3orderingchecks because readiness accepted a div.score-row-link skeleton (emptyheadings); screenshots confirmed loading placeholders. Final script requires actualheading+Andorraanchor andHTTP200, retains order/identity assertions. Corrected36112763873 passed; finalrun above passes again.
Firstprofile36113178459 and second36113702313 passedtests/build but failedbeforeisolatedcandidatepublication. Verifiedfirstartifact10854206328 ZIPd32f7a157554f21f0299c8a6da12a8ccd2d5403c308ddcaf84c70fb63992bd3a contained onlysource.patch/tests.xml, actualfirstlog timedout atinitialprofilevalue. Do not repeat an earlier unverified claim of StringNameError; the harmless page.url->str(page.url) audit edit did not fix it. Finalcandidate adapted only localpreview responseCORSheaders (4173 is absent from configuredallowedbrowserorigins) and addeddiagnostics; identicalruntimepatchpassed. Actualproductionacceptance usesnointerception andpasses.

## Still open and exact continuation

- User's4min comparison needs a named activefixture and real end-to-endmeasurement; no fabricatedseconds/status/score or blanketshorterbackoffs. Source responses and applicationqueueing must be distinguished.
- Myanmar–Timor-Leste d807549bf94203765dd7/source6233017 rechecked08:45 stillscheduled1–0 versus priorverifiedupstreamFT2–0; source-parent/groupidentityfix remainsopen, no manualscoreoverride.
- Sligo OLDbb4071086c3ea042f6e9 rechecked08:45 stillschedulednull; richcanonical8ea488bb6f0bcf5038b7 isFT0–1. Validaliasfrontendhandling isfixed but thisDBaliasisnot. Preserveexistingproof/manualrestrictions.
- Wholeplayer/clubhistory, squads, transferfees/valuationhistorychart, broadsport/competitiondataandrealshotmap remainunfinished. Someprofileslackupstreamfacts; do not substitute inventedamounts/fees/photos. Matchsubstitutionsrichparser preserved andverifiedonSligo, not claimedcompleteeverywhere.
- Latestwide11daycoverageaudit remainshistoricalC12:2698public/198strictunresolved/84agedscheduled at06:10; C14didNOnewwideaudit.198unresolvedisnot198missingfixtures. PreserveallcurrentpublicIDs.
- Finalhomephoto shows several editorial thumbnails blank and datedarticles; news-onlystructureisdone, not fullnewsfreshness/mediaQA.
- Desktop1440profile screenshot has existing horizontalheadernav overflowing beyond Predictions; /live-scores remainsin getPrimaryNav and mobilebottomnav, but desktopvisibilitywithoutscroll needsfollow-up. ThispassdidnotchangeSiteHeader/config; do not confusehomewidgetremovalwithremovingtheLiveScoresroute. Keep coreentryeasytofind in nextUXpass.
- npm audit warnings from existingdependencies were not addressed; do not claimsecurityclean. No publiclaunchuntil stablecomplete testedcore.

Resume by reading this and newer issue6comments, verifycurrentmain/master/deploymentrefs, use small reviewedforwardchanges and fullpreservedtests. Sourcebranches+readablepatches+preflights persist onGitHub; userdoesnotwant downloadablebackupbundles. Never resetproductionbecausechatinterrupted.
