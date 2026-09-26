# C20 result recovery — release preflight, 26 September 2026

This is PRE-RELEASE, not completed production acceptance. User priority: still-missing Live Scores/results; no TinyFish pictures or user interaction burden; do not spend Railway Agent on routine work. No Railway Agent used. No News activation/settings work in this pass.

## Fresh source and coordination

Backend main freshly read at `9db4b7cd3b83aac57981cd2769fec089d7786b1f`, the combined C19 release. Frontend master `7183733e5eed7dae566aeaf1632fc757c547cc4c` remains unchanged. C19 checkpoint at audit/combined-release-20260926-19 /6f1c4441688d8e608cfcbd87deaf693b0770ddcd and issue6 comment5844072158 read. Issue8 latest13th comment5844137533 read: News03 exists separately at f08633d0221fbf9d9850f291dbab4ffe927c11c7, documentedc3bdb1ccf39373cbb5a94a7a5964ab954f466e33; NOT included in C20. Preserve integrated News01/02 and untouched News03 branch.

Exact C20 candidate **ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726**, branch fix/football-result-queue-c20-20260926. Compare ahead10/behind0, ten changed files: five collector runtime files, three test files, one inert patch archive and one offline-only workflow. No frontend, News, API bootstrap, DB schema, service variables or root deployment recipe changes. All five runtime and three test archive files independently byte/SHA256 matched to locally reviewed source.

Pre-release backend source snapshot branch **rollback/pre-c20-results-20260926** points to9db4b7cd3b83aac57981cd2769fec089d7786b1f. This is NOT a database backup.

## Actual observed issue classes

Direct existing worker logs show source_identity_conflict with explicit proof: same owned native event split between canonical parent and season leaf, and native women's events duplicated under known domestic non-women's competition buckets. Examples: Colombia1000014161 parent274/leaf1000001696; SpainLigaF5882299/leaf938777; Italy5977767/leaf942146; Germany6040018/leaf10650. Other conflicts include reversed/unequal pairs, independent trees and changed kickoffs; they must remain blocked unless separately verified.

Fresh PRE-release deployed worker3b49e467-8ce2-4eb2-a10e-158fc59dc574 log at **2026-09-26T07:38:41.729555336Z**: current native day20260926,449seen,12deferred,30processed,2written,1source_identity_conflict. The12 are deferred source observations, NOT12proven missing completed public matches. Native UTC date is not Sydney local date. Earlier future-day27 observations had28deferred; that is an earlier snapshot, not a current invariant.

One bounded TinyFish public default-browser visit eff42344-42be-405e-b020-2f620b61c1e6 (13steps) found19displayedFTrows with nonempty scores and two matching detail headers, but no concrete empty-score row. Its claim of exhaustive469-match correctness and its assertion that the site does not convert local times are NOT accepted: no independent coverage comparison or controlled timezone test was done. User report remains open. Capture/screenshots/recording flags were false; no image was attached by the assistant. Later use was text-only search/fetch. API/HTML fetch attempts often returned no usable body; they are not raw score evidence. Direct container HTTP could not resolve DNS. No blocked production-audit workflow was retried or bypassed.

## Bounded runtime changes

1. Reserve at most2of the existing maximum8 priority slots for fresh new live/final source IDs ahead of the current sequential cursor, retaining known-result slots and regular coverage first. No additional board fetch or new scheduler. Reuse existing accepted ingestion, receipts/backoff, time budget and owner lease; failures never advance over unvisited coverage. This is not an absolute latency guarantee or full source coverage.
2. Allow only exact owned native oriented participant IDs + match ID to bridge an explicit ungrouped parent/leaf scope for a canonical target. Group metadata, copied provider IDs, wrong IDs, contradictory finals, manual restrictions and independent child trees still reject.
3. Resolve native women's duplicates in frozen known domestic non-women's buckets only with exact owned match/team IDs, same native leaf, checked incoming women's category, and matching explicit native/catalog/old-registry countries. Missing cached old-league gender is not guessed. A missing or contradictory country does not use canonical_country_matches(empty)'s permissive default. Original row IDs/fingerprints remain; accepted duplicate becomes an old-link alias, not deleted data.
4. Linkage revision5 makes existing deferred entries eligible for one normal revalidation pass. It does not blanket clear deferreds, visibility restrictions or scores.

## Actual tests and review findings

Final gate **36227263924**: both backend and retained-frontend terminalSUCCESS. Downloaded actual JUnit:
- **1200 selected combined backend tests,0failures/errors/skips**: originalC19 1160 plus40new cases.
- Baseline unchangedC19:5new selected cases fail by assertion,0errors, proving root/scheduler defects before fix.
- **329 full frontend tests,0failures/errors/skips**, same published frontend7183733; production-target build and30existing Node policy checks passed.
- Test image uses actual dependency-compatible Python packages; execution is network-disabled with ephemeral data and no production credentials. No stub dependencies or requirement changes.

Final backend artifact10901415327 ZIP SHA256 **568c0ecfa3517ccb209ac64d2971c4caed2ad8bf35b65132cecf285e389e0d28**. Final frontend artifact10900169610 ZIP SHA256 **563246d6a3ba7a8a01f10dcfe8a62573ac13f047d5043a1fae0c07ae68801e98**. ZIP integrity, actual JUnit and candidate marker read. Runtime/test source patch SHA256 **8705ed35ddaeccda9e1dcbe63c8a1f9e38f13f5f1221e055ab677346857c573e**. All eight source/test files match local reviewed bytes; retained bot/extract.py, deploy/news/preflight.py, app.py and collector/worker.py unchanged.

Earlier gate36226932874 passed its original35new-case selection, but further local captured-native replay found Italy/Germany unnecessarily blocked by absent cached old-league gender. During review an explicit different-country negative test failed because parsed event country is not yet populated at root planning. Corrected to mandatory native context plus verified catalog/registry country matching, added tests, then reran full final gate. Neither review failure was deployed. Final local40cases pass.

Offline replay of three UNCHANGED captured native scheduled matches5882299/5977767/6040018 from c17-exact-source-categories.zip/native-20260927.json now preserves their actual kickoff/status/score/participants and both DB rows, while linking synthetic duplicate legacy rows to their correct women competitions. This is captured-source replay, NOT fresh production recovery; only the local validation fetch envelope was renewed. Original runtime patch had three transport-only extra spaces at diff boundaries; canonical stored patch was normalized only after checking exactSHA44c2effbe4cf94ec39d606a7eed63f994a1897e6a94d7d14bc9bfc1c0dfc9551. Final committed source is normal code, not runtime patch execution.

## Release/rollback boundary

Only nonforce main fast-forward to exact tested candidateba0b70017fa2d96717ce4c4f8e40e2ac95ec3726; frontend remains unchanged. Let existing GitHub integration update API/results-worker; inspect actual matching terminal deployments and new logs. No Railway Agent, configuration change, new service, News start, DB reset/direct score edit/blanket promotion, force push or unrelated staged environment patch.

If regression: preserve DB and aliases, diagnose, then forward-revert only these five C20 collector files relative to9db4b7. Prior C19/C18/C17 guards and News code remain. Old source version already understands canonical alias pointers, so do not reverse DB links/delete records. Record actual production outcomes and remaining deferreds before claiming progress. No claim of all fixtures/results/details/assets/mobile QA complete. Keep issues6/8 open and persist final checkpoint.
