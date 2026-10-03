# NinkoSports Football News — verified release, 3 October 2026

**Status: DEPLOYED, TESTED, PARTIAL COVERAGE. Football News is NOT 100% complete.**

This is the latest recovery record for this work session. It supersedes pending-verification wording in `NINKOSPORTS_NEWS_FOOTBALL_2026-10-03.md`; that companion record retains detailed implementation history and the exact 56-menu gap list.

## Production versions and safety boundary

News backend branch `ops/news-free-probe-20260926`: **8a541d8f7f32d7241a5ecff4a862af86e1b05ea0**. Railway source pin matches. Actual successful deployment **e4077f41-ec6c-4ac1-a36e-cff6247a760d**, created 2026-10-03T01:49:48.559Z. Service `be857be7-a029-4663-81c7-bcde75efc482`, project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`.

Frontend master: **5e2d799c38d22ac709644dcbc7646bfc40f3559b**. Actual successful deployment **262dc78d-16d4-4821-8215-639ee20a8735**, created 01:37:28Z. Frontend project `d2187a78-90d0-437a-871b-10e16ba8d07c`, environment `52ceaa71-df43-4275-9ebe-6c19d4437461`, service `df4b231a-fcbc-4d89-bef8-d9028d03b473`.

Shared API deployment **a6018808-ec70-44a9-8ddc-5a65b30f9c57** and results-worker deployment **25287c7e-08a8-46f8-aa3b-0d85ba6eaf53** remain unchanged from 27 September. No shared sporting-data writes or result-worker changes were made. Existing News budgets, keys, translations setting, region, replica count, Dockerfile and start command were preserved.

## Measured public coverage

Actual post-deployment snapshot: **2026-10-03T01:56:27.768Z**, GitHub workflow **37087798967**, artifact **11261317616** (`football-news-final-coverage-20261003`).

| Measurement | Observed |
|---|---:|
| Football News menus inspected | 86 |
| Menus with at least one published article | 30 |
| Menus with an article from the past 24 hours | 24 |
| Menus still empty | 56 |
| Menus returning table rows | 52 |
| Menus returning match records | 72 |
| Menus with upcoming fixtures | 46 |
| Menus with results | 70 |
| Public API errors | 0 |
| Returned article sport/league field mismatches | 0 |
| Match rows missing at least one team logo | 1,384 |

Match counts include the available stored record windows and may include historical data; they do not prove a complete current season. The logo-gap sum is across inspected menu responses, not a deduplicated club count. Most missing-logo rows came from retained Championship data (844), with further gaps in other competitions. Do not call the News data experience fully complete or hide these gaps as success. Some cups and inactive competitions have no applicable current table.

The audited Leverkusen women article **22719** was observed via its public API at **01:53:31.492Z**, HTTP 200, in **football-women**. Its title and source date (`2026-10-02T19:15:07`) were retained. This is actual runtime evidence of automatic menu repair, not just a passing unit test.

## Shipped improvements

- Nine additional reviewed RSS desks in the existing intake: Football Espana, Get German Football News, FotbollDirekt, SuomiFutis, Liga2 ProSport, Blick Football, STV Sport, Gong and Equalizer Soccer. Dedicated football and mixed-sport feeds remain distinct. Missing, paid, stale or unverified copy is not promoted.
- Four additional publisher indexes: Greek Superleague and Superleague 2 through Gazzetta; Austrian Bundesliga and second tier through LAOLA1. Exact visible body containers and article-associated photos are required. Publisher league categories are a last-resort editorial menu association, not invented match facts.
- Source-bound women's category preservation: only exact-identity Sportschau NewsArticle metadata with football and Frauen keywords can annotate the source. Related articles, navigation and audio metadata cannot do so. Drafts dropping that explicit qualifier from both title and summary are rejected. The known existing Leverkusen misclassification was repaired without inventing or rewriting a result.
- Multilingual women's/youth and regional national-team news classification fixes. Existing fact locks, originality checks and independent validation are retained.
- Budget-neutral queue fairness for already-waiting, underfilled football competitions. Repeated repair attempts no longer always consume the opportunity available to another empty league. Existing spending limits were not raised.
- News-only data aliases for Women's Champions League and Mexico Expansion. Apertura is visibly identified; Clausura is never silently merged into its table. Canonical populated data wins, exact season is retained, explicit men's records cannot enter the women's menu.

At the verified alias API check: Women's Champions League returned 18 table rows and 54 matches (36 fixtures, 18 results); Mexico Expansion returned 16 rows and 117 matches (40 fixtures, 77 results). Neither response had missing team logos. These are observed available records, not full-season guarantees.

## Test and browser evidence

**1,403 News regression tests passed** in final backend gate **37087422475**, plus syntax checks and live public source admission checks. Clean release branch: `audit/news-football-context-release-20261003`. Production build hashes for extraction and fact checking matched the tested hashes in its artifact.

Frontend alias gate **37086580946** passed **341 non-App tests**, production build and actual adapter reads. This is not described as a fresh run of every App route test; those were tested separately in the earlier release.

Actual production browser gate **37087500971** passed all 18 alias tab checks and three fully loaded article-reader checks at 1440, 390 and 320 pixels. The same real article's 160-word body and 1920x1080 hero photograph loaded on all three viewports. No mocked API data, browser script errors, page overflow, or sports-data write requests. Mobile screenshots were visually inspected. Earlier gate 37085765034 adds 24 verified main-league tab checks; its initial article skeleton was not counted as reader acceptance.

## Automation and remaining work

The existing dedicated News worker remains enabled. Final deployment startup log records a normal 10-minute News cycle and staggered image-health checks. The first scheduled News cycle after this final deployment is 02:00 UTC. Its end-to-end new Greek/Austrian publication outcome was **not yet observed at this checkpoint**. Earlier active release completed normal cycles with published articles, and the final version's automatic Leverkusen menu correction was separately observed.

Fresh source admission is not publication. In the final source probe, Greek top tier supplied two eligible source articles, Greek second tier one, and Austrian second tier one; Austrian top-tier index was quiet within the freshness window. All four candidate texts/photos were verified before writing. Do not report these as four published stories until IDs and exact public menus are observed.

**Next work is the remaining 56 empty menus and factual/asset gaps, not recreating the News architecture.** Follow the companion record's complete gap list and source-probe evidence. Diagnose each empty menu's missing stage: accessible current reporting, correct extraction, original draft, factual acceptance, image, menu association or writer capacity. Do not manufacture articles, reset old dates, weaken validators, or populate unknown scores with zero. Review repeated Negreira coverage (22717/22718) before claiming full story-level deduplication.

Use the clean deployed branches above as recovery bases. Never merge the audit branch wholesale: it contains staging modules and one-off validation workflows. Before another deployment, compare current heads and preserve newer work from other sessions. The exact actual deployment IDs from direct Railway status take precedence over an agent's cached or prematurely reported IDs.
