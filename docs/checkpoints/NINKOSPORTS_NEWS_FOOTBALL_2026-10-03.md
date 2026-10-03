# NinkoSports Football News — 3 October 2026

## Recovery anchor

Status recorded after deployment verification at approximately 01:54 UTC. This is a **partial News release checkpoint, not a claim of 100% football News coverage**. The next verification is the already-running final public coverage workflow; update this record with its actual result, not an assumed increase.

Strict scope: football NEWS. Reuse existing public sports records only through read-only adapters. Do not modify/deploy shared backend main, Live Scores collectors, sporting records, or the results worker. Do not increase budgets or turn translations back on. Preserve current keys and all RESULTS false guards on the News worker.

## Actual production releases

- Dedicated News: macamala/allball-backend `ops/news-free-probe-20260926` at **8a541d8f7f32d7241a5ecff4a862af86e1b05ea0**. Railway source pin verified equal. Service `be857be7-a029-4663-81c7-bcde75efc482`; active deployment **e4077f41-ec6c-4ac1-a36e-cff6247a760d**, SUCCESS, created 2026-10-03T01:49:48.559Z.
- Frontend: macamala/allball-frontend `master` at **5e2d799c38d22ac709644dcbc7646bfc40f3559b**. Railway deployment **262dc78d-16d4-4821-8215-639ee20a8735**, SUCCESS, created 2026-10-03T01:37:28.479Z.
- Shared API unchanged: service `c08822c6-e602-4f32-a2bc-87aedbbe9b05`, deployment **a6018808-ec70-44a9-8ddc-5a65b30f9c57**, 27 September.
- Results worker unchanged: service `2c89eecf-b094-428a-8f7c-9642605a6baa`, deployment **25287c7e-08a8-46f8-aa3b-0d85ba6eaf53**, 27 September.
- Last direct environment inspection: no staged changes or pending work. Unrelated old crashed audit service was not changed.

News Railway project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`. Frontend project `d2187a78-90d0-437a-871b-10e16ba8d07c`, environment `52ceaa71-df43-4275-9ebe-6c19d4437461`, service `df4b231a-fcbc-4d89-bef8-d9028d03b473`.

News retains `deploy/news/Dockerfile`, `python deploy/news/preflight.py --run`, us-west2, one replica. Runtime scheduler log: every 10 minutes, first cycle after final deployment 02:00 UTC, image-health first 01:55 UTC. No extra production publication jobs or additional paid AI requests were triggered by the audit workflows.

## What was shipped

1. Multilingual women/youth subject recognition and separation of current regional national-team events from incidental World Cup references. The observed Frankfurt Frauen men's-menu error was repaired by the existing worker; title, copy and dates were retained.
2. Nine additional RSS desks in the EXISTING News intake: Football Espana, Get German Football News, FotbollDirekt, SuomiFutis, Liga2 ProSport, Blick Football, STV Sport, Gong and Equalizer Soccer. Dedicated football feeds are distinguished from mixed sports feeds. No blanket league/country stamping. Exact article paths and scoped visible body containers; old/paid/inaccessible stories remain held. Reviewed hero fallback is limited to that article's OG/Twitter photograph, not neighbouring cards.
3. Budget-neutral football queue fairness: an underfilled competition with an actual waiting source gets an opportunity before repeated repair attempts on another story. Existing AI limits, paid allowances, fact checking, originality checks and independent validation remain unchanged. Football prompt clarifies BODY length, excluding headline and summary, and prohibits padding.
4. Four reviewed HTML indexes: Greek Superleague and Superleague 2 via Gazzetta; Austrian Bundesliga and second tier via LAOLA1. Gazzetta prose requires BOTH `content` and `is-relative` on the same div, never generic page content. LAOLA1 uses its `editor-text` div. Exact publisher article categories can provide a News-menu fallback after explicit primary subject classification; they never create sporting facts or league membership.
5. Same-article women's-category preservation: Sportschau NewsArticle metadata must have the exact canonical mainEntityOfPage, football AND Frauen keywords. Audio objects, unrelated articles, navigation, lookalike hosts and malformed metadata cannot establish the category. The writer's title or summary must preserve it; a dropped qualifier is rejected. No hidden JSON-LD body is used to bypass unavailable visible copy.
6. Audited menu-only correction for source story `https://www.sportschau.de/regional/wdr/wdr-leverkusen-feiert-comeback-sieg-gegen-bremen-100.html`, source date 2026-10-02, public article 22719. The source's explicit Frauen category was lost in the generated lead. Correct destination is `football-women`; no new score, participant, date or admission state is invented. **Post-deployment automatic execution still needs the pending coverage observation; passing the repair regression is not runtime proof.**
7. News-only data aliases for Women's Champions League and Mexico Expansion. Canonical data wins when populated. The retained Mexico phase is visibly labelled Apertura and never mixed with Clausura. Explicit non-women events cannot enter the Women's Champions League menu.

## Tests and evidence

Backend final release gate **37087422475** SUCCESS: **1,403 News tests passed**, syntax checked. Clean release branch `audit/news-football-context-release-20261003`. Prior gates: 37085348312 (1,352 News tests), 37085201166 (1,343 tests plus regional source admission probes).

Frontend alias gate **37086580946** SUCCESS: **341 non-App regression tests**, production build and actual public News adapter reads. Clean branch `audit/news-football-alias-release-20261003`. Do not describe this as a rerun of every App route test: those were run separately in the earlier release.

Public browser gate **37087500971** SUCCESS: 18 new alias tab checks across 1440/390/320 pixels plus the same fully loaded real article on all three viewports. Checks waited for actual copy and decoded hero photo, not a loading skeleton. Article 22717 displayed 160 body words and its actual 1920x1080 image. No mocked/intercepted API responses, page script errors, page overflow, or sports-data write requests. Screenshots visually inspected on mobile. Earlier public gate 37085765034 passed another 24 tab checks for EPL, La Liga, Brazil B and Serbia Superliga; its early article screenshot was a skeleton and is NOT article acceptance evidence.

Verified alias data at 01:34 UTC:

| News menu | Table rows | Available matches | Upcoming | Results | Missing team logos |
|---|---:|---:|---:|---:|---:|
| Mexico Expansion — Apertura | 16 | 117 | 40 | 77 | 0 |
| Women's Champions League | 18 | 54 | 36 | 18 | 0 |

Counts are observed available records, not a claim of complete season coverage.

Source proof at 01:48 UTC: fresh, fully scoped, photo-verified candidates for Greek top tier (2), Greek second tier (1), Austrian second tier (1). Austrian top-tier index was quiet within the source freshness window. These are **pre-writer candidates, not four published articles**. Earlier 9-desk probe produced 15 eligible candidates across 8 desks; Equalizer had no eligible fresh public candidate. No AI calls in source probes.

Production build hashes matched the tested source:
- `bot/extract.py`: f038949003b68c147d49ccca4479dd90a5705a35b42444100f1966ae0275fea9
- `bot/news_fact_guard.py`: 62797067c2923f378f2a9fff8e6ab2ce03cddc1966dd1c78983b79fc82d2ec2a
- `bot/fetch_sources.py`: c2ceac7d49caf45740c7fe7e93471e45c25cb4f3b659194142b08cac5351c4df

## Last completed full 86-menu measurement (before final aliases/context release)

Snapshot 2026-10-03T01:23:52.238Z, production workflow 37085765034:
- 86 menus inspected; 30 had published News; 23 had a story within 24 hours.
- 50 menus returned table rows; 70 returned match records; 44 had upcoming fixtures and 68 had results.
- Zero API errors and zero mismatched returned league/sport fields. Field consistency does NOT prove every story's semantic correctness.
- Frankfurt Frauen known mislabel absent. The later Leverkusen error was separately discovered and is addressed by the final release.
- Complete football News: **NO**.

Empty News menus in that snapshot:

england-championship; italy-serie-b; germany-2-bundesliga; france-ligue-2; serbia-prva-liga; netherlands-eerste-divisie; belgium-challenger-pro-league; turkey-super-lig; turkey-first-league; greece-super-league; greece-super-league-2; scotland-premiership; scotland-championship; switzerland-super-league; switzerland-challenge-league; croatia-hnl; croatia-prva-nl; poland-first-league; czech-first-league; czech-second-league; austria-bundesliga; austria-second-league; denmark-superliga; denmark-first-division; norway-first-division; sweden-allsvenskan; sweden-superettan; finland-veikkausliiga; finland-ykkosliiga; romania-liga-1; romania-liga-2; bulgaria-first-league; bulgaria-second-league; hungary-nb-2; usa-mls; usa-usl-championship; brazil-serie-b; argentina-primera-nacional; mexico-liga-mx; mexico-liga-expansion; japan-j1-league; japan-j2-league; south-korea-k-league-2; saudi-first-division; australia-a-league-women; uefa-europa-league; uefa-conference-league; uefa-euro; fifa-club-world-cup; conmebol-libertadores; conmebol-sudamericana; afc-champions-league-elite; caf-champions-league; usa-nwsl; belgium-cup; uefa-womens-nations-league.

Do not report all data as current/full merely because a menu returned a row. Stale flags, exact season, missing logos and cup/phase applicability still matter. Off-season or knockout competitions may legitimately have no current league table.

## Recovery procedure and remaining work

Use the deployed clean News branch above, NOT the audit branch as a production base. Frontend master is separately deployed. Preserve all newer commits before a fast-forward. The audit branch contains workflows and staging files that must not enter production en masse.

1. Read the result for audit commit **acc84719ac0c7f78e38db36ed90a13f94cc888ed**, workflow `news-football-final-coverage-20261003.yml`, artifact `football-news-final-coverage-20261003`. It records every menu, tables/matches/logo gaps, exact dates, and bounded automatic Leverkusen repair observations. Update this checkpoint from the measured results.
2. Check final News deployment e4077f41 logs after its normal 02:00 cycle. Source admission and passing tests do not prove publication. Record actual new article IDs and rejection reasons; never fabricate a full status.
3. Continue the empty-menu list by missing stage: fresh accessible source, article extraction, original writing, factual validation, menu association, photo availability or provider capacity. Do not remove validators or change source dates to inflate counts. Some free writers were returning quota errors; paid fallback allowance remains capped.
4. Validate publisher independence and additional local desks for still-empty leagues, then prove end-to-end publication in the corresponding menu. Existing 48-feed probe includes stale/blocked/HTML-not-RSS candidates; do NOT blindly enable them.
5. Inspect two related Negreira reports (22717/22718) for substantive overlap. They contain distinct developments but can be repetitive. Do not delete either blindly or label all deduplication complete.
6. Missing sports-data tables beyond the exact available aliases require investigation within the user-approved read-only scope. Do not modify shared result storage or workers to make News completeness numbers look better.

This record intentionally separates deployed code, proven production behaviour, available source candidates and remaining gaps.
