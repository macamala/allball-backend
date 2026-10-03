# NinkoSports Football News — rosters and native sources, 3 October 2026

**Status: deployed, tested, partially populated. NOT 100% Football News completion.**

This supersedes the deployed News source version in `NINKOSPORTS_NEWS_THROUGHPUT_2026-10-03.md`. Preserve its earlier protections and the prior frontend recovery checkpoint. Do not merge this audit branch wholesale.

## Actual production recovery anchor

- Repo: `macamala/allball-backend`.
- News production branch: `ops/news-free-probe-20260926`.
- **Deployed source: 8f474371ac8001ecfeb0438f5020f79312f19339**.
- Clean release branch: `audit/news-completion-release-20261003`.
- Actual Railway News deployment: **412990de-5f65-40b7-96b4-cfd12c48042d — SUCCESS**, created 2026-10-03T03:48:26.576Z, settled 03:48:47.466Z. Direct deployment metadata independently confirms the source commit and branch.
- News service `be857be7-a029-4663-81c7-bcde75efc482`, project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`.
- Final source-pin operation: `patch:60ecb604-24b8-4bd2-8a8e-c8f203dbaa63`. Only `source.commitSha` was changed and committed once; no duplicate explicit redeploy.
- Earlier release in this session: **10757cc555feba62f04cdf5dd252c857287a948c**, actual deployment `4b0cc4ce-7722-4114-86bf-8bdf902e9cf2`, SUCCESS. It fixed punctuation and added initial read-only roster fallback. Final release includes it.
- Intermediate **46ec6e800f5ca1ee7be7f25ad5d167a0da3660a0** (clean `audit/news-native-release-20261003`) was tested and incorporated into the final child; it was NOT separately deployed.

Shared API deployment **a6018808-ec70-44a9-8ddc-5a65b30f9c57** and results-worker deployment **25287c7e-08a8-46f8-aa3b-0d85ba6eaf53** remain unchanged from 27 September. No shared sporting records, results collectors, backend main or frontend code was changed in this session. Frontend master remains the prior recovery version **5e2d799c38d22ac709644dcbc7646bfc40f3559b**; this session did not redeploy it.

News retains `deploy/news/Dockerfile`, `python deploy/news/preflight.py --run`, us-west2, one replica. Existing AI provider settings, keys, paid request/spending caps, translations setting and RESULTS false guards were preserved. Last direct project status had no pending or staged changes.

## Shipped fixes — existing News pipeline only

### Current club-to-league association from existing public records

Standings remain the first choice. When an applicable table is missing, News may read the existing competition hub and, if necessary, a separate date-bounded stored-event response. These supply **club identity for a News menu**, not scores, calculated standings, invented season labels or prose sporting claims.

Strict checks retain exact football competition scope, independently updated recent records, supported statuses, bounded kickoff dates, participant identity and men/women/youth separation. A partial roster remains `complete_roster=False`, even when all 24 Championship clubs happen to be observed. An unknown season remains unknown. Explicit club-type forms such as FC may produce bounded equivalent names; generic words do not become guessed club aliases.

The Championship hub's `coverage.stale` comes from its external native-schedule supplement. The hub itself was correctly rejected; this flag was NOT removed or ignored. The final fallback independently reads `/sports-data/events` with exact competition and a UTC date range, requires a complete public stored snapshot whose count and bounds match the response, then checks each record's own freshness. In the accepted probe the separate snapshot had 199 records; 24 clubs passed the current-roster rules. Fresh HTTP retrieval cannot freshen an old sporting record.

The initial 49-versus-50 production discrepancy was therefore **not demonstrated to be a network outage**. It was traced to the hub's aggregate stale flag. The new stored-record fallback addresses that actual cause. Separate bounded retries address genuine transport errors only: ten-, twenty- and forty-minute delays on existing cycles, at most three extra attempts, failed leagues only. Wrong-scope, old, forbidden and malformed responses do not gain retries or admission.

**Actual production log, 03:51:44.905689344Z:** 50 supported domestic league rosters, 864 clubs, all fresh, two fixture-derived rosters (Championship and Argentina Primera Nacional), no read failures or pending retries. This is NOT 50 populated News menus.

### Native Japanese reporting instead of relying only on delayed English pages

The existing official-index intake now reads the native J1 and J2 news pages through `bot/news_jleague_native.py`. A story must have the exact same-article canonical identity, its own visible title/date/category module, its own visible prose and matching article photograph. Japanese local publication time is converted to UTC, without resetting it. Navigation parameters cannot supply a league; hidden content, broadcasts, previews, promotions and unrelated cards are excluded.

Three source inputs were proven usable before the writer: J1 article 35031 (Noguchi professional contract), J1 article 35032 (Kashiwa promotions), and J2 article 35030 (Suzuki injury). All retained source dates, exact J1/J2 categories and reachable own photographs. Existing originality, numeric, factual, independent-validator and image gates are still required before publication.

**Actual production source logs, 03:50:42–03:50:47:** native J1 discovered eight and hydrated two; native J2 discovered eight and hydrated one. Nonmatching and stale candidates were rejected. This proves the sources are wired into the worker, NOT that three English articles were published.

### Correct primary transfer subjects and protected empty-menu opportunities

A secondary phrase such as `from a Serie A side` no longer takes the News menu away from the actual subject club. The live replay of the Burnley headline now associates it with Championship when the verified roster is available; without evidence it remains unknown rather than being forced into Italy. Historical `Former Premier League` references cannot return through the queue's broad classifier fallback.

Zvezda priority remains first. The normal three-major/one-other cadence is retained by default. In one of three ten-minute slots, a real queued empty nonmajor league can take an earlier opportunity only when no queued major league is below its existing floor. Unknown topics cannot invent a priority debt. This reorders an existing allowance; it does not add AI requests or increase paid caps.

### Punctuation preservation

The text normalizer now preserves ordinary sentence-ending periods, abbreviations and decimals while retaining actual ellipsis/truncation handling. It does not invent new prose or rewrite old archived articles. A new production article was verified with both complete paragraphs and their terminal punctuation intact.

## Tests and source evidence

Final release gate **37094279386 — SUCCESS**, artifact **11263033192** (`news-completion-final-20261003`):

- **1,655 tests passed: 1,651 News tests plus four text-utility tests.** Zero failures, errors or skips. Python 3.12, matching production minor version.
- Isolated SQLite regression database; no production credentials or writer API calls in the tests/source probes.
- Actual read-only source replay: 50 rosters/864 clubs, Championship 24 clubs, exact transfer association, and the three native Japanese input articles with photos.
- Exact allowlisted file changes and patch SHA256 were checked before application. No audit workflows entered the production source.

Earlier gates: **37092297505** (1,531 News/text checks and initial roster proof), **37093635016** (1,603 checks plus native-source/retry proof). The initial native gate's failed live association correctly exposed missing Championship evidence; it was not hidden by assigning the wrong league.

Selected hashes in final artifacts:
- `bot/news_football_memberships.py`: 38728309596dc0c6152b3294fdb8482986b54c0206a2693521f2e63e16d46422
- `bot/news_football_priority.py`: c92b214137040653404a9e79d407deabe72b8d65a1fa97595591dc49222b4fae
- `bot/news_jleague_native.py`: b217b688aba822c2869b64fb5eac7786e059bc8fe77f3fd885516a326da9c8a1

## Actual public coverage and reader checks

Public browser/read workflow **37094462044 — SUCCESS**, artifact **11263414767** (`news-completion-public-20261003`). At 03:50:15UTC all 86 menus were read. Actual article **22740** (Raphinha monthly award) loaded its complete 77-word brief and original 740x416 hero at 1440, 390 and 320 pixels. Both served paragraphs retained terminal punctuation. No intercepted/mocked API data, page script errors, page-width overflow or sports-data write requests were used. Mobile screenshot visually inspected. This is a rendering check for that actual brief, not a claim that every article or all related-card photos were verified.

Bounded normal-cycle observation **37094631899 — SUCCESS**, artifact **11264330182** (`news-completion-publication-observation-20261003`) repeated public GETs without triggering any writer and re-read all menus. Final snapshot **2026-10-03T03:56:45.051371Z**:

| Measurement | Observed |
|---|---:|
| Football News menus inspected | 86 |
| Menus with published articles | 31 |
| Menus with a story within the past 24 hours | 25 |
| Empty menus | 55 |
| Public read errors | 0 |
| Returned sport/league field mismatches | 0 |
| Missing image URLs in the inspected sample | 0 |

The aggregate count did not increase, but a real classification repair was observed. **Championship is no longer empty.** Its returned sample includes articles 22748, 22684 and 22739. Article **22684** was observed before in `norway-eliteserien` and after in `england-championship`, retaining the same ID, headline and dates. The previously populated Norwegian menu became empty after that incorrect English association was removed. Do not count a wrong-category article as successful league coverage.

Japanese J1 and J2 were still empty at this measured snapshot. At **03:57:06UTC**, the worker attempted native source 35031, but the draft added unsupported `2026/27`; the numeric gate rejected it and the existing paid retry allowance was exhausted. **Do not claim a successful native English publication or weaken that gate.** Native source acquisition is fixed; writer acceptance remains an observed bottleneck.

The worker also logged publication 22750 at 03:54:27UTC. Its original candidate was a `Ticket news` Chelsea Legends item; review its promotional versus editorial status before treating it as a clean quality success. No deletion/forced hold was made without inspecting its source. The public Superliga sample also contains youth-looking 2018-team article 22475; inspect its exact original category before claiming all men's/youth associations are complete.

## Runtime and remaining gaps

Final deployment's startup confirms the existing ten-minute scheduler, first cycle 03:50UTC, staggered image health 03:55. That normal cycle fetched native sources, refreshed the 50 club rosters, attempted writing, and produced at least one logged publication. The cycle-end summary was not yet included in the captured evidence. The audit itself made zero AI requests and did not trigger publication jobs.

Railway labels stderr lines as severity=error even when their message begins INFO; this alone is not a crash. Distinguish actual exceptions, rejected drafts and normal INFO messages.

Empty menus at the final measured snapshot:

italy-serie-b; germany-2-bundesliga; france-ligue-2; serbia-prva-liga; netherlands-eerste-divisie; belgium-challenger-pro-league; turkey-super-lig; turkey-first-league; greece-super-league; greece-super-league-2; scotland-premiership; scotland-championship; switzerland-super-league; switzerland-challenge-league; croatia-hnl; croatia-prva-nl; poland-first-league; czech-first-league; czech-second-league; austria-bundesliga; denmark-superliga; denmark-first-division; norway-eliteserien; norway-first-division; sweden-allsvenskan; sweden-superettan; finland-veikkausliiga; finland-ykkosliiga; romania-liga-1; romania-liga-2; bulgaria-first-league; bulgaria-second-league; hungary-nb-2; usa-mls; usa-usl-championship; brazil-serie-b; argentina-primera-nacional; mexico-liga-mx; mexico-liga-expansion; japan-j1-league; japan-j2-league; south-korea-k-league-2; saudi-first-division; australia-a-league-women; uefa-europa-league; uefa-conference-league; uefa-euro; fifa-club-world-cup; conmebol-libertadores; conmebol-sudamericana; afc-champions-league-elite; caf-champions-league; usa-nwsl; belgium-cup; uefa-womens-nations-league.

Next work must diagnose these by missing stage (current accessible reporting, body/date/image, correct menu identity, draft, independent factual acceptance, or budget capacity). Quiet/inactive competition periods do not justify fabricated fresh stories. Do not lower numeric/originality/gender/image gates, reset source dates, indiscriminately clear holds or raise spending limits. Review the exact unsupported-season Japanese draft and its provider, and monitor actual publication through normal cycles.

Earlier unresolved duplicate-story and missing-identity-asset findings remain open. The prior News data-tab coverage was not fully re-audited here, so retain its timestamps rather than presenting old counts as current completeness. Keep Live Scores and its production services unchanged.

For recovery, start from the clean deployed commit above, compare current heads to preserve newer work, and use the saved artifacts and this record. The staging/audit branch is not a production base.
