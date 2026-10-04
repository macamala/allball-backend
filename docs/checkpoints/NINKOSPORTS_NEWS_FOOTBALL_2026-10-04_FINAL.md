# NinkoSports News football — verified release, 4 October 2026

This final record supersedes the pending deployment status and the initial failure hypothesis in NINKOSPORTS_NEWS_FOOTBALL_2026-10-04.md. It does NOT declare complete football coverage.

## Verified deployed release

Production News branch ops/news-free-probe-20260926 is pinned to 34885ab355b0dee6fae31d77278baf0c6af0a34b. Railway News deployment b7bf65ad-4986-4d25-9c71-a7142167c7bd is SUCCESS, and its real runtime log at 05:51:59 UTC confirms a 600-row football-prioritized editorial repair. All 2,198 retained and new News regression tests passed in Actions run 37180937246. No API, results-worker, frontend/mobile design, AI budget or translation configuration was changed. Only the News service commit reference was staged and committed; no Railway AI agent was used.

The deployed changes include source-only Portuguese count validation, early BET INFO betting-product filtering, two additional verified existing-pipeline source desks (Get Belgian and Dutch Football News and FK Spartak Subotica), same-article body/photo checks and publisher-logo rejection, explicit non-football admission guards, a 600-row football league-menu repair, and football-prioritized bounded editorial maintenance. Full implementation details and negative tests are retained in the accompanying checkpoint and source history.

## Actual publication / reader checks

Actions run 37180618045, attempt 2, job 111373706533, completed SUCCESS at 05:52 UTC. It repeated the original public checks without weakening them. Artifact 11294084275 preserves the public response and detail evidence.

At 05:52:08 UTC the public football endpoint returned 478 article cards. There were zero missing image_url fields; 94 cards still had no league field. These are current inventory counts, NOT newly published articles from this release. The previously observed surfing article 22926, futsal article 22979 and Battlefield product article 22523 were absent from football. The acceptance list also checked absence of 22444, but it was already absent at the first pre-maintenance snapshot; do not attribute its disappearance to this deployment without further evidence.

Six current article-detail requests succeeded with the correct ID, full content and image URL: 22971, 22968, 22967, 22977, 22966, 22959. This is an API/detail check, not a visual desktop/mobile browser acceptance test or a factual certification of every sentence.

Real first-release maintenance at 05:45:23 UTC recorded three league-menu assignments among 600 scanned football rows. Those are actual data changes, not claims that all empty leagues were filled.

## Correction to the initial failure diagnosis

The first public test ended at 05:46:04 UTC while article 22523 was still visible. A later read of the original c446bd6 deployment log proves it was held at 05:47:41 UTC with reason non_article_video_game_product. Therefore the first failed acceptance snapshot was taken before that maintenance pass had finished; the mixed-sport starvation explanation was a hypothesis, not the demonstrated cause of this particular late removal. The 34885ab follow-up selection priority is independently regression-tested prevention of a possible starvation case; do not claim that it was what removed 22523. The source guard from the first release performed that confirmed removal.

## Image verification and remaining work

A separate whole-feed byte/dimension probe, Actions 37180732721, examined the then-current 481 cards / 469 distinct image URLs: 478 article-photo checks passed and three were inconclusive. The count predates the final cleanup and must not be confused with the later 478-card inventory.

A bounded repeat in Actions 37180937246 still found ReadTimeout for IDs 22782 and 22739 and HTTP 429 for 22730, all on thumbs.smartframe.io. No unrelated photo was substituted and no access limit was bypassed. Zero empty image_url fields is not proof that all photographs load in every client.

Football completion remains OPEN. League/club freshness coverage is still uneven; 94 public cards lack a league field, though not every general football story necessarily belongs to a domestic league. Other explicitly documented scope questions (22513, 22505, 22967) still need exact-source review. New BeNe and Spartak desks retain original freshness limits and must not be described as new October 4 publications when their latest audited source entries were October 2 and September 27. No new article publication attributable to this release was verified in this acceptance window. See the accompanying checkpoint for the Napredak extraction gap and next source work.
