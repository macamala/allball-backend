# C17 release preflight — 26 September 2026

User continuation: repair mixed men's/women's football and continue unfinished football detail, table, links, transfers, scorers and bracket work. This bounded release covers category identity/filtering, women marker detail/season linkage and verified season scorer API/UI. It does NOT complete the remaining global backlog.

## Exact bases and tested candidates
Backend main freshly read at52272139d4ecaffbe84cc4709e25c0b0ed3abb56. Candidate255f798cdbd8f33139d160aed60c37ef831ce4cf on fix/football-categories-scorers-c17-20260926, normal ahead4/behind0. Frontend master freshly read at0b26a18f5a1d0a5b8ccc8adc57b8c9d5d17d2f13; tested candidate878bcc5dd06baee5cc9a1a2e0f18767ec186686c on the same-named frontend branch. Both are isolated source candidates, not deployed as of this record.

Reviewed backend diff16files including workflow, two tests and replay; runtime changes limited to identity/category, scorer endpoint, three women-aware season pair comparisons, existing collector repair and public/cache projections. Frontend9srcfiles plus candidate workflow. Existing results and event IDs are not replaced; manual/retired/source/group protections retained.

## Actual gates and review
Initial exact restored draft run36213957560:961backend tests and294frontend tests/build pass. Review then reproduced a genuine missing women season canonical link: female witness tolerated (W), but three later hub pair comparisons omitted female context. New regression failed before the correction and passes after, with oriented native IDs still required. Second new regression proves slim/detail/live-delta category parity without mutating stored legacy rows.
Final backend run36214410022 allstepsSUCCESS:963tests,0failures/errors/skips plus retainedC16native replay and C17native replay294categories/2detailIDs/6scorer samples. Downloaded artifact10896857586 ZIP SHA2567a6bb682e294f80f523a6cf9cc4825a68e818c831a3b8f15064a12d4972c4cc7. Full source.patch55567bytes SHA256f9701f4c709afc357ee3c626aeb3c33adb0d91c93759fce52e60291e272df3fb. CandidateSHA and every fileSHA independently checked against extracted archive. Earlier run36214205631 stopped at diff-check because the three new lines inherited CRLF; normalized only those lines and reran fullgate. No failed test was relabeled passed.
Final frontend run36214237061SUCCESS:294tests,0failures/errors plus productionbuild. Artifact10896603169 ZIP SHA256d39a4745550bb34ee6b393d8760d5206723edef91053bba09a9074a900ebe943, exact prior draftsource.patch SHA256b7f01962d89daefcf4f5657ffc277a94cfd6d8f07f576f5a9f8916dc9d39a67a. ActualJUnit/candidate read and ZIP integrity verified.
Native scorer replay is parser proof, NOT production availability of all6leagues. Composite group scopes intentionally remain unavailable unless verified. Do not claim fullglobal top scorers or transfers.

## Fresh public pre-release baseline
Run36214428569SUCCESS; artifact10896807899 ZIP SHA2560338801d71c50401e8e2f0338639bce3bad51c10fd9019afe1276b58953c4a7c. At2026-09-26T03:19:07.753293+00:00:912canonical football IDs in SydneySept25–28cohort. Mexico hub35records, Toppserien132, bothHTTP200. The draft audit mistakenly called /sports-data/events/{id} for detail and received404; correct public detail route is /sports-data/matches/{id}. That404is an audit-route error, NOT evidence of a broken match. Correct route will be used in acceptance.
Railway actual pre-release API533968e7-64dc-489a-80f9-7b7836069fdb and worker d5707add-c5b2-45ad-b95a-112620add780 bothSUCCESSmatching52272139. No Railway mutations performed.

## Release and rollback boundary
Use only nonforce fast-forward of main/master to these exact reviewed candidate commits through existing integrations. Do not accept unrelated staged Railway patch; do not use Agent, addservices, runschedulers, changevariables, manually edit scores, resetDB or forcepush. Preserve worker-only RAILWAY_DEPLOYMENT_DRAINING_SECONDS=15 and existing owner-safe shutdown. Verify actual terminal deployments with matching hashes, then real API/browser1440/390/320 category/scorer/table/link flows and prior live/rich/home/player checks. A successful deploy is not acceptance.
Rollback if necessary is a reviewed new forward revert of only this release's runtime changes relative to the exactC16base, not a force-reset or database reversal; retain all records and historical protections. Persist actual observed acceptance failures and final outcomes.

Stillopen until separately proven: fullMatchCentre for source-only season records, remaining tables/oldMyanmar and Sligo aliases, complete transfers/fees/value history/squads, global scorers, brackets/shotmap/assets, other sports, news freshness/desktopnav. No global completion or publiclaunch claim.
