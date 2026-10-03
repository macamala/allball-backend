# NinkoSports Football News — throughput checkpoint, 3 October 2026

## Current recovery version

**Deployed and tested; football News coverage remains incomplete.** This supersedes the News source version in `NINKOSPORTS_NEWS_FOOTBALL_2026-10-03_FINAL.md`. Prior frontend data-alias and source-coverage evidence remains applicable; it is not presented as newly retested in full here.

- Production News branch: `macamala/allball-backend`, `ops/news-free-probe-20260926`.
- Clean source commit: **6e975006a52aff1f45db2a047a233faed28de907**.
- Clean release branch: `audit/news-throughput-release-20261003`.
- Preceding tested patch: `998c290289ba5ef22afbd7c424a1e2145edba747`; both commits descend from previous production `8a541d8f7f32d7241a5ecff4a862af86e1b05ea0`.
- Railway News service: `be857be7-a029-4663-81c7-bcde75efc482` (hopeful-blessing).
- Actual new deployment: **8d3f2f68-6ab9-43d7-bb26-c2ae43150c00**, **SUCCESS**. Created 2026-10-03T02:34:00.465Z, settled 02:34:26.842Z.
- Railway deployment metadata independently reports commitHash **6e975006a52aff1f45db2a047a233faed28de907** and the intended News branch.
- Project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`.

One source-pin deployment was requested and committed; operation `patch:46d8504c-5198-4448-b449-c793c958985c`. No second explicit redeploy was triggered. Only `source.commitSha` changed. Existing variables, keys, writer budgets, model allowances, translations setting, RESULTS guards, region, replicas, Dockerfile and start command were left unchanged.

**Shared API deployment remains a6018808-ec70-44a9-8ddc-5a65b30f9c57; results-worker remains 25287c7e-08a8-46f8-aa3b-0d85ba6eaf53, both from 27 September.** No sporting records, collector code, shared backend main, or frontend files were changed in this session. Frontend recovery version remains `5e2d799c38d22ac709644dcbc7646bfc40f3559b` from the previous checkpoint.

## Fixed in the existing News system

1. **Article parsing interrupted by empty HTML class attributes.** The production parser raised `AttributeError: NoneType has no attribute split` for markup such as `<p class>`. Normalizing attributes fixes the main text extractor and scoped body extractor; the regional metadata parser also handles an empty class safely. Exact body-class requirements, chrome exclusion and paywall holds remain in place. This is not permission to extract unrelated recommendations or inaccessible copy.
2. **False confederation acronym rejection.** Football source text containing the exact bounded token Concacaf/Conmebol now supports the same uppercase acronym. Arbitrary acronyms, substring lookalikes, new confederations, numbers, quotes and unsupported assertions remain rejected. The Greek source was read directly: 140 visible words, including the exact mixed-case Concacaf token. No AI-generated draft was accepted merely because this spelling check passed.
3. **Opinion products wasting original-news attempts.** Explicit `Opinion:` prefixes and `: Opinion` / separator suffixes are held as analysis before writing. Ordinary reporting mentioning a doctor's second opinion or another person's opinion is unaffected.
4. **Full RSS bodies being treated as article leads in the editorial queue.** Queue menu hints now use the first complete source paragraph, with a bounded complete-sentence fallback. The complete source body is retained unchanged. A historical league mention in the tail or an unsupported classifier hint cannot by itself create missing-league priority. This does not change article dates, rewrite facts or force publication.
5. **Common word Start mistaken for a Norwegian club.** Real-source replay exposed this after the lead correction: headlines about an excellent/tough start were still assigned to Norway through a current club catalogue alias. The News-only menu classifier now requires an explicit club form or possessive sporting role for that ambiguous alias. It does not modify shared team identities or invent a replacement league.

Important replay result: the Blackburn/Doncaster examples no longer receive Norway or Germany's second-tier menu. Their current output is **unknown menu**, not a claimed verified Championship/League One assignment. Remaining membership/category evidence must be addressed separately.

## Regression and real-source gates

- Final identity/source gate: **37090073252**, SUCCESS.
- **1,469 News tests passed, zero failures or errors**, on **Python 3.12**, matching the production minor version. Previous complete suite had 1,403 cases: this work adds 66 regression cases.
- All earlier source/originality/fact/independent-validator/public-admission tests remained enabled. Existing editorial length thresholds and provider budgets were not changed.
- Earlier throughput gate **37089866527** passed 1,457 tests and direct Greek/The72 source reads. It found the Start collision during real-source review, which was then fixed and retested before deployment.
- Reproductions on unmodified source failed as expected: 18 parser/acronym cases and 10 queue/opinion cases. The final source contains their fixes; the before failures are retained as evidence, not hidden.
- Final full-feed replay at **02:32:32.578299Z** confirms the labelled Watford opinion is held, and the two start-related headlines are not assigned to Norway/Germany. No AI calls or production content writes were used for these source probes.

Evidence artifacts:
- Run 37089340493, artifact 11261956076: initial 86-menu/source/parser diagnosis.
- Run 37089866527, artifact 11262121729: tested throughput patch, before/after XML, actual source replay.
- Run 37090073252, artifact **11261533372**: final 1,469-test XML, exact source hashes, final replay and tested commit.

Selected tested SHA256 hashes:
- `bot/extract.py`: 5b56845d4abbab2df0bd717db4897cf5ceec67c0430bfc6de2fe622a1b6c9690
- `bot/news_fact_guard.py`: e1af72439747da568813b6a3e81f3a1e1db705263a28d55c6e1f4b48ed7146f0
- `bot/news_football_sections.py`: 42b3ec072a026f2570f0457e7c63fbb11262bfd75fd26d150cb2cd9d410f2632

## Actual public publication coverage

Public read/browser workflow **37090333914**, SUCCESS; artifact **11261788151** (`news-throughput-public-20261003`). Coverage snapshot **2026-10-03T02:35:43.065787Z**:

| Measurement | Observed |
|---|---:|
| News menus checked | 86 |
| Menus with at least one published article | **31** |
| Menus with an article from the past 24 hours | **25** |
| Empty News menus | **55** |
| API errors | 0 |
| Returned article sport/league field mismatches | 0 |
| Missing image URLs in the inspected article sample | 0 |

The read sampled up to three articles per menu. Field consistency is not proof of every article's semantic accuracy, and an image URL is not by itself proof that every photo loads. This is NOT full football News completion.

The increase from the prior checkpoint's 30 populated menus is independently verified in **Austria Second League**: public article **22723**, `fc-hertha-wels-engages-legal-and-tax-advisors-following-management-changes`. It was published by the previous normal worker cycle before the new throughput deployment; do not attribute it to the new fixes.

Actual browser checks at **1440, 390 and 320 pixels** loaded that article's complete **62-word brief** and its same-article **1280x720 photograph**, with matching title and Austria Second League association. No mocked responses, script errors, horizontal overflow or sporting-data write requests were used. Mobile screenshot was visually inspected. This proves full rendering of the served brief, not a long-form editorial feature. The initial reader test incorrectly imposed an unrelated 100-word UI threshold; it was corrected to check the entire served payload. No production editorial acceptance threshold was lowered.

Observed editorial limitation: the served brief's paragraphs lack terminal periods. Investigate sanitization versus rendering before proposing a bounded News-only correction; do not describe all editorial polish as complete.

## Runtime and next work

New deployment startup at **02:34:25.529737Z** confirms the existing 10-minute News scheduler, first next cycle **02:40 UTC**, and staggered image-health checks beginning 02:35. A full new-publication cycle of this final deployment has **not yet been observed at the time of this checkpoint**. The prior worker demonstrably completed normal cycles and published articles, including Austria Second League, women's football and U21 reporting.

Remaining work is not a second News architecture:

- Resolve the 55 empty menus using actual source-to-publication evidence. Continue major football/Serbia priorities; do not fill a menu with unrelated or fabricated copy.
- The72/current-club queue association still lacks verified current membership/category evidence for some English lower-league clubs. A source's historical league is not a replacement. Exact article category metadata may be useful after it is independently inspected.
- Confirm production throughput and false-rejection changes over the next normal cycles. Do not increase budgets or manually trigger extra paid writer jobs to make the graph look better.
- Review exact held-source/cached rejection behaviour before claiming that previously rejected articles have been reprocessed. This release does not indiscriminately clear holds or override validator decisions.
- Preserve prior findings on duplicate-story review, source freshness and missing football identity assets. Those were not closed by this release.

Use the clean deployed branch/commit above for code recovery. The audit branch contains one-off workflows and must not be merged wholesale into production. Recheck current branch heads and Railway state before any later deployment so newer work is preserved.
