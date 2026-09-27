# NinkoSports News checkpoint #06 — 27 September 2026

## Status

Candidate News work is preserved and tested. Production News remains unchanged and disabled.

- Working branch: `news/free-router-20260926-05`
- Base main: `e844681d794d8303623e48a2b079fdcd33dc545d`
- Green News CI code head: `c88357a0f181b0cbf146475d69bf08dff7153002`
- Green News CI run: `36288323810`
- News CI result: **69 passed in 1.12s**
- Existing football regression run on the same code head: `36288323813` — **SUCCESS**
- Temporary PR-only News workflow was removed after the green run at commit `3ad3df26d2f5bfb25ad34427918d9eb5db4c4b62`.
- Draft PR #9 remains open only as a review/CI surface. It is not merged.
- No Railway production deploy was performed.
- No News scheduler was activated.
- No public News article was created by this candidate.
- No historical News repair was enabled.
- Live Scores API/results-worker/frontend production were not changed by this News branch.

## Railway safe state

Existing News service `hopeful-blessing` remains on the prior isolated probe source:

- repo: `macamala/allball-backend`
- branch: `ops/news-free-probe-20260926`
- commit: `aa7aef864b88234990b12df24a96e7421e322f99`
- start: `python news_free_generation_probe.py --once`
- restart policy: `NEVER`
- News worker remains disabled.
- Candidate source staging was restored and the remaining no-op staged patch was explicitly discarded.
- No pending candidate deploy is intentionally left on Railway.

## Free-only AI route

`bot/free_ai_router.py` is the candidate News AI transport.

- Default candidate route is xKiro free-only.
- Writer and validator model IDs must end in `:free`.
- Default candidate model: `qwen/qwen3.5-397b-a17b:free`.
- No paid model alias fallback.
- No automatic provider rotation into an unverified paid route.
- Before a generation call the live public xKiro model catalog is checked.
- The model must exist, have `access_tier=free`, and expose zero input/output pricing.
- Missing/unavailable catalog metadata fails closed.
- Each actual model request still uses the durable shared News request ledger.
- OpenAI is retained only as explicit legacy code and requires both `NEWS_AI_PROVIDER_MODE=openai_legacy` and `NEWS_ALLOW_PAID_AI=1`.

Current xKiro documentation confirms that `GET /v1/models` is public and the live source of truth, with `access_tier` and pricing metadata. Actual account/model quality is still NOT production-proven by this checkpoint.

## Factual safety

The candidate now uses three layers before a source-based story can be written publicly:

1. Existing deterministic number/source-overlap/structure gates.
2. Exact multi-word proper-name preservation gate.
3. Separate free-model fact validator that fails closed on unsupported claims or changed names.

A real GitHub CI failure exposed two defects before deployment:

- double-escaped proper-name regex;
- field-hockey/water-polo/futsal headlines colliding with generic football phrases such as “World Cup” and “Champions League”.

Both were fixed. Explicit niche-sport title evidence now overrides only those generic football tournament signals. Existing football regression CI remained green.

## Zero-AI NinkoSports result-news lane

`bot/data_news.py` remains implemented but disabled by default.

- Requires explicit `NEWS_DATA_NEWS_ENABLED=1`.
- Reads only NinkoSports public canonical finalized results.
- Does not contact upstream score providers.
- Generates deterministic NinkoSports result briefs.
- Consumes zero AI requests.
- Uses stable result identity by day/sport/competition.
- Adds no unsupported scorers, incidents, quotes, injuries, tactics or statistics.
- Writes `ai_generated=False`.
- Trusted sport/competition resolution comes from the canonical NinkoSports result.
- It is NOT yet wired into the regular News scheduler and has NOT written to production DB.

## Expanded free News sources

Expanded feeds remain behind `NEWS_EXPANDED_FEEDS_ENABLED`.

New configured free source paths added in this pass:

- Australian Rules — AFL first-party RSS.
- Badminton — BBC Sport RSS candidate.
- Field Hockey — BBC Sport hockey RSS candidate.
- Table Tennis — BBC Sport RSS candidate.
- Water Polo — BBC Sport RSS candidate.
- EA Sports FC — Electronic Arts press-release RSS.

The BBC niche endpoints are intentionally not labelled production-proven merely because they are configured; runtime freshness/robots/extraction gates still decide admission.

## First-party official index adapter

`bot/news_official_indexes.py` was added for sports whose official sites expose fresh News pages/sitemaps rather than RSS.

Configured bounded candidates:

- Handball — IHF Media Centre.
- Futsal — UEFA current News sitemap, filtered to futsal URLs/titles.
- VALORANT — VALORANT Esports official News.
- League of Legends — LoL Esports official News.
- Call of Duty — Call of Duty League official News.
- Overwatch — official Overwatch News, competitive/esports markers only.
- Rocket League — official competitive News page.

Safety:

- behind expanded-source flag;
- same-host URLs only;
- robots-aware existing public News transport;
- bounded index bytes, candidate links and hydrated stories;
- explicit source publication timestamp required;
- stale or undated material fails closed;
- article body is hydrated once and reused;
- no third-party bypass when a first-party page is inaccessible.

Robots behavior has NOT been production-proven for every candidate. The runtime deliberately yields zero rows when permission/access cannot be established.

## Configured coverage map

The source configuration now has a discovery path for **40 concrete sport slugs** in the 41-row Sports Registry.

The remaining registry row is the generic `esports` parent/aggregate. Its concrete child sports have configured paths:

- EA Sports FC
- Counter-Strike
- League of Legends
- Dota 2
- VALORANT
- Call of Duty
- Overwatch
- Rocket League

Do not report this as 41 independently proven production sources. A configured path is not the same as a runtime-proven fresh source.

## Capacity

The current News request ledger allows at most 200 actual AI requests/day.

With writer + fact-validator, source-based AI stories normally consume two model calls before optional retries. Therefore AI rewriting alone cannot be the worldwide freshness layer.

The intended architecture remains:

1. canonical NinkoSports results -> zero-AI original result briefs;
2. free public/official News discovery -> free-model original reporting with factual validation;
3. translations later on a separately budgeted free-only path.

## Next gate

The next meaningful step that cannot be proven offline is ONE bounded deployment of the synthetic xKiro `:free` quality probe on the existing News service.

That probe must:

- keep News worker disabled;
- never access/write production DB;
- never publish an article;
- use exactly a `:free` model;
- preserve supplied names/numbers;
- return English + Serbian Latin + configured translation fixture;
- be manually reviewed for factuality/language quality;
- restore the safe one-shot state after completion.

Do not merge or activate the scheduler before that probe passes.
