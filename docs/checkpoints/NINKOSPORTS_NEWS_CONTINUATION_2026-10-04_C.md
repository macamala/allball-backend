# NinkoSports News continuation C — 4 October 2026

## Exact tested state

Repository: macamala/allball-backend. Audit branch: audit/news-football-completion-20261004. Exact tested runtime commit: 8dcf6ace33b449aed09affccb8467d1b64330f27. This record is documentation added after that tested commit; it adds no runtime code.

Final GitHub Actions run 37186566654, job 111389622353, completed SUCCESS. Downloaded artifact 11296629796, news-continuation-final-tested-evidence, contains the actual test output: **2,328 passed, 5,431 warnings in 33.39 seconds**. Its tested-news-commit.txt matches the SHA above. The artifact also includes the complete tested source, runtime patch, scope comparison and a real Swedish index-selection result. Passing these tests is not certification that every existing article is factually correct or every league is complete.

## Implemented in this continuation — audit branch, NOT production

1. Football index selection excludes already-ingested URL identities BEFORE the eight-link hydration quota. HTML anchors, the scoped Chelsea component and news sitemaps use the same pre-quota exclusion. Confirmed stale source pages enter a thread-safe, source-specific, bounded 30-minute cache so a stale prefix does not permanently hide deeper articles. Future/unverified dates, access errors, missing bodies/images and successful articles awaiting a writer are not cached. The eight-link cap, transport bounds, robots rules, AI budgets and publication gates remain unchanged. Other sports retain their existing selection behavior. Source hold URLs with no ingested Article record are not claimed to be comprehensively addressed by this change.

2. Added official Motherwell FC and Kilmarnock FC desks to the EXISTING RSS/extraction pipeline. Motherwell loads multiple full stories on a single URL; prose, gender category and photograph are now taken only from the one infinite-item whose data-href matches the requested article's canonical identity and whose article ID is valid. A neighboring story, global social avatar, hidden schema or changed structure cannot supply substitute content. Kilmarnock uses its verified article__body and own social photograph. Both use the existing robots-aware, DNS/redirect/size-bounded transport; wrong or missing canonical identity fails closed, without falling back to generic HTTP. No blanket league, men's first-team or current-publication label is assigned from publisher identity.

3. Removed the exact FotbollDirekt Allsvenskan directory slugs alla-lag, spelschema and tabell from article discovery BEFORE they consume news slots. Longer actual reporting slugs about schedules or tables remain eligible. The final live source read returned eight candidate article links and zero directory links, under the original read cap. It did not publish these candidates or certify them as eligible original stories.

## Supporting evidence and qualifications

- Index regression run 37185898753 passed 2,293 tests. Artifact 11296853173; integrated index commit dcbe616e9fb07b4ed41ce620491d6c7f588b6cc8.
- Scottish source run 37186300341 passed 2,323 tests and real source checks. Artifact 11296958639; integrated source commit 8dbdd36b18440d3a76661224067c20ac4436e896.
- Earlier Scottish run 37186175672 passed runtime tests but its read-only probe failed because the probe omitted the required now argument to news_freshness_reason. The corrected run supplies an explicit UTC clock; no freshness rule or assertion was weakened.
- Motherwell's next-up-aberdeen-h-4 page yielded 363 words from the correct women's article, its own photo and original 2026-10-02 15:04:01 UTC date. The Jake Girdwood-Reich article yielded 1,660 words and its own photo, excluding neighboring stories, with original 2026-10-02 11:00:41 UTC date. Kilmarnock's Dave Richards report yielded 107 words, original 2026-10-01 16:28:04 UTC date and its own photo. All three bounded image-byte checks passed. All three dates correctly remained stale; none was republished as fresh October 4 news.
- The deeper-index demonstration explicitly simulated the first eight links as known. Deeper links were found on Swedish, MLS and Eredivisie indexes, but sampled deeper articles were stale. This proves the selection mechanism and preserved freshness checks, NOT newly available fresh articles for every empty league.
- Read-only inventory at approximately 07:24 UTC contained 474 public football cards, 59 without league fields and no empty image_url fields. General football reports do not necessarily belong to a domestic league; zero empty image fields does not prove all photos load or match their articles. These are a dated inventory snapshot, not articles created by this patch.
- Olympiacos was inspected but NOT added: its latest feed mixed women's water polo congratulations and academy/youth reports. FCM, Braga and TSC probes did not yield usable feed entries and were not claimed as verified working integrations.

## Production status and blocking condition

Actual Railway News configuration was re-read during this continuation: production remained on **00604b3721780179c0381ef2ca8dbe7332f363a0**, service hopeful-blessing (be857be7-a029-4663-81c7-bcde75efc482), project 17f6ebff-0f6b-42dd-be86-35ca9ca40301, environment cb27d851-9198-47c8-a733-8356e8b6cf63. Latest read identified deployment 8d664e32-ce06-436b-a9cc-84a6036118c9 as SUCCESS.

A prior interrupted turn had left patch 959d429f-603e-4027-b6ab-b895fbd2d014 staged for News commit **f46b9d98fb67a1ce69c30e9c8fddf8d90a735e09**. The reviewed patch touched only the News source configuration, with no variable or other-service changes. The exact f46 artifact in run 37184051750 recorded 2,275 passing tests.

One accept-deploy attempt in this continuation was blocked by OpenAI with: "This tool call was blocked by OpenAI because we couldn't determine the safety status of the request." No successful deployment followed. The block was not bypassed through another tool, GitHub workflow, API, production ref mutation or credential route. Subsequent work and CI writes remained on the audit branch only. The later configuration read still showed live00604 and stagedf46.

IMPORTANT: the existing staged f46 target does NOT contain the new 8dcf continuation. Do not describe it as deploying the latest audit changes. Do not claim this continuation is visible on the public site. A future continuation must resolve the blocked deployment through the permitted mechanism, re-read live and staged state, compare the latest tested commit, preserve concurrent work and verify actual publication after a successful allowed deployment.

No API/main, results-worker, frontend/mobile design, approved AI budget or translation configuration was changed. No Railway AI agent was used. Production's existing scheduler continued independently; its new articles must not be attributed to these un-deployed changes. Football coverage and original-source review remain open, not complete.
