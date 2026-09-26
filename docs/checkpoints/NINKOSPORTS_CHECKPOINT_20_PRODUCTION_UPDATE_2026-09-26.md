# Checkpoint 20 — latest production verification update

**This update supersedes the earlier C20 record's provisional one-link / unverified-future status.** Read together with `NINKOSPORTS_CHECKPOINT_20_2026-09-26.md` at4ed1b72065b5cc39810b3969d31eeb460e89fbe0 and its preflight. No new runtime change or deployment was made for this update.

## Current source, tested and deployed

Backend main **ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726**; frontend master **7183733e5eed7dae566aeaf1632fc757c547cc4c**, unchanged. Both heads were read back after deployment.

API **b9d2539c-b8cc-49b9-bd31-68e39bb50039** SUCCESS07:42:08.185Z; results-worker **98ceeeb2-9762-4686-81da-fc9e0c44521a** SUCCESS07:41:51.154Z on26September2026. Exact matching backend SHA. Pre-release backend9db4b7cd3b83aac57981cd2769fec089d7786b1f remains on rollback/pre-c20-results-20260926. Preflight4b78fc0dc658d539a00b9f5976978ddef8f9daf1 was committed before main advanced, nonforce.

Final gate36227263924: **1200 selected combined backend tests /329 full frontend tests**, zero failures/errors/skips, production-target frontend build and30 Node policy/ownership checks passed. Five new test cases fail by assertion on unchanged C19 before the fix. Actual downloaded JUnit and artifact integrity were inspected, not inferred from job labels. Backend ZIP10901415327 SHA256568c0ecfa3517ccb209ac64d2971c4caed2ad8bf35b65132cecf285e389e0d28; frontend10900169610 SHA256563246d6a3ba7a8a01f10dcfe8a62573ac13f047d5043a1fae0c07ae68801e98.

## Verified runtime progress — seventeen links, NOT seventeen new final scores

Direct NEW worker logs report one Colombia root link at07:41:57.097510635Z and sixteen women's legacy root links between07:50:32.679314928Z and07:50:38.978698119Z. These occur through normal accepted source ingestion; original row IDs remain as aliases. No rows were manually deleted or scores entered to obtain the counts.

| Native source ID | Canonical keeper | Retained legacy alias |
| --- | --- | --- |
|1000014161|ninko-evt-a65e5b0f697618a40473|ninko-evt-48ee659f22a82cb68ef9|
|5882299|ninko-evt-7384f2659befe0040598|ninko-evt-952a006e61a930a10398|
|5882301|ninko-evt-88d4ffcec3f2caaa2e6f|ninko-evt-46bf888bbeef5b060d2e|
|5882305|ninko-evt-22f6c8323ee6e2e462d5|ninko-evt-8d461c2143efb7124f0e|
|5882306|ninko-evt-e67e5537597a139d3113|ninko-evt-dcd5827d393505ded42e|
|5977767|ninko-evt-05bdc2c8e466fba80bbf|ninko-evt-8deb08fe96b7b3b0332f|
|5977770|ninko-evt-8bc30853290b57772178|ninko-evt-867e2594052569b55c7d|
|5977771|ninko-evt-d1395447af1753c19c9c|ninko-evt-2154d359c3f50be698f2|
|6040018|ninko-evt-d5d173a9cd79df7e2226|ninko-evt-ddf73a273a8741b94041|
|6040019|ninko-evt-49bcfc3a10be611a9420|ninko-evt-489c0d0d051de8ee71a6|
|6040020|ninko-evt-f261da5d21909a361e70|ninko-evt-62eba74f5880e800f9f7|
|6040021|ninko-evt-bf2d2430875556697285|ninko-evt-1403f8fff15b8fbefd0c|
|6040025|ninko-evt-63d94aeb9261c0015dc0|ninko-evt-61cdab911e62b89c8dfa|
|6040026|ninko-evt-948233247b59110fa0ad|ninko-evt-3c0a61d85d3bd5c197a4|
|6040028|ninko-evt-27a7af5883ff3ff47c6b|ninko-evt-8bfb11c561e760773806|
|6040030|ninko-evt-69a64f63894af226524b|ninko-evt-6bb63bdbf70f4eae73e9|
|6040032|ninko-evt-f8a79d468a985f042904|ninko-evt-9e7105b51c6bb0682744|

The sixteen future links comprise4SpanishLigaF,3ItalianSerieAFemminile and9GermanDFBPokalFrauen events previously split between native women's and known non-women's domestic buckets. This is now actual production linking evidence, no longer only the earlier offline replay proof. It still does not verify all future fixtures, complete lineups or rendered assets.

## Comparable before/after counters

These are **native UTC source-day deferred observations**, not Sydney-local board totals, not all missing finals and not a count of newly added matches.

- **25Sept:3 ->2 deferred /102source events.** Before oldworker07:40:57.390365487Z; after newworker07:43:30.772343671Z. Exact Colombia link listed above.
- **27Sept:20 ->4 deferred /283source events.** Before oldworker07:40:57.390365487Z; after newworker07:50:40.020282334Z. This post-release page processed27, rejected4source_identity_conflict and logged16accepted root links. Its0`written` new-observation count does not negate alias linking; do not describe these as16new inserted matches.
- **26Sept:12 ->12 deferred /449source events**, still unresolved. Newworker07:51:47.052444534Z completed that cursor sweep with `complete=true`, `data_complete=false`,43processed,4written,2rejected,2priority slots. Never equate completed traversal with full data completion or hide the unresolved12.

The runtime also continues normal score persistence and C18 detail/table warming. A60-second watchdog stack occurred07:42:50 while inSQLAlchemy; persistence continued and later cycles ran. There is no measured global freshness/latency guarantee; DB/cycle performance remains a follow-up item.

## What this release fixed, and boundaries

C20 gives fresh newly observed live/final IDs ahead of the saved cursor a bounded priority share without increasing source requests or replacing the validator. It also resolves only exact owned native parent/leaf collisions and proven women's domestic misclassification duplicates. Groups, copied IDs, reversed/unequal team pairs, conflicting final scores, manual-hidden/retired restrictions and independent trees retain their protections. Five collector runtime files changed; News/runtime frontend/shared schema remain untouched.

The two repaired Colombia score URLs returnedHTTP200 in new API logs07:48:34, but public extraction produced no usable response body. Therefore no numeric final score or exact body equality is claimed. The synthetic3-0 regression fixture is NOT the real match result. The one earlier normal-browser survey of19visibleFTrows is not exhaustive fixture/source coverage proof. No new public912-ID sweep, full-final comparison or actual1440/390/320 production check was completed. No local screenshot is presented as production; no screenshots/images attached to the user.

## Next priorities

Continue the12current-day and4future-day unresolved observations with exact provider identity/time/orientation proof, then verify public board, old/new match links and full details. Existing known unproven classes include NWSL5161651,USL5109962,Mexico5898735 and Chile6162931/6162932, with copied IDs, unequal pairs or changed kickoffs. Do not force score updates or broadly weaken identity guards merely to lower a counter. Keep full source-only MatchCentres, group tables, old Myanmar/Sligo links, possible Waterford duplicates, transfers/scorers/brackets/assets and full coverage OPEN.

News01/02 remain integrated. News03 candidatef08633d0221fbf9d9850f291dbab4ffe927c11c7 is untouched on its isolated branch and is not part of this release. News worker activation and old-homepage-news selection remain blocked/open as in C19. This chat remains sole integration/deploy owner; update both issues6and8 with this exact current source.

No Railway Agent, replacement service, subscription, credential disclosure, database reset, manual result override, force push or unrelated staged Railway patch. Resume from current C20 SHA plus this verification update, not by replaying C18/C19/C20 patches. Rollback, only if needed after diagnosis, is a reviewed forward revert of C20 code with DB rows/aliases and prior guards preserved.
