# NinkoSports News checkpoint #07 — 27 September 2026

This checkpoint supersedes News checkpoints #05 and #06 for resume purposes.

## Durable repo state

Backend:
- repo: `macamala/allball-backend`
- branch: `news/free-router-20260926-05`
- final clean head: `3f3eca3549be3b2b51db0d2e65a903ebb0c57583`
- base main: `e844681d794d8303623e48a2b079fdcd33dc545d`
- 0 commits behind main
- draft PR #9 remains open; DO NOT MERGE/DEPLOY automatically.

Frontend:
- repo: `macamala/allball-frontend`
- branch: `news/article-translations-20260927-01`
- final clean head: `66aa42c1eecd775072a39189b4285f47c341a878`
- base master: `7183733e5eed7dae566aeaf1632fc757c547cc4c`
- 0 commits behind master
- final diff is only src/api.js, src/pages/ArticlePage.jsx and its News test.
- draft PR #5 remains open; DO NOT MERGE/DEPLOY automatically.

Temporary CI workflows were removed from both branches after proof.

## Final regression proof

Backend final logic head before CI-harness removal:
- `8a75e6747a44ca685525582e1582370d327f20b0`
- complete News regression run `36290025373`: **300 passed, 2 warnings, SUCCESS**
- same-head football source/lifecycle run `36290025385`: **SUCCESS**

The warnings were existing datetime.utcnow deprecation warnings, not test failures.

Frontend proof:
- candidate CI run `36289161815`: **SUCCESS**
- full retained suite: **37 files / 332 tests passed**
- focused translated ArticlePage tests passed
- production Vite build passed
- temporary workflow removed at `66aa42c1eecd775072a39189b4285f47c341a878`.

## Railway production remains untouched

Project: zesty-stillness
Environment: production
News service: hopeful-blessing / `be857be7-a029-4663-81c7-bcde75efc482`

Current source remains:
- repo macamala/allball-backend
- branch `ops/news-free-probe-20260926`
- commit `aa7aef864b88234990b12df24a96e7421e322f99`
- start `python news_free_generation_probe.py --once`
- restart NEVER
- staged changes: none

No candidate worker/scheduler deploy has happened. No public article has been written by candidate code. Live Scores production was not modified.

## Final candidate architecture

### A. Zero-AI NinkoSports Result News

`bot/data_news.py`:
- reads only canonical public NinkoSports finalized results
- zero AI requests
- original NinkoSports result roundups
- no provider branding
- no invented scorers/incidents/quotes/injuries/tactics/stats
- one stable article per Sydney-local day/sport/competition
- updates as confirmed finals arrive
- `ai_generated=False`
- per-group savepoint isolation prevents one bad group rolling back the rest
- Sydney editorial calendar is converted to exact UTC date_from/date_to bounds
- invalid timezone falls back to Australia/Sydney
- explicit `NEWS_DATA_NEWS_ENABLED=1`

Scheduler runs this lane before AI checks. It continues even if free AI allowance is exhausted or unavailable, as long as the worker/accounting ownership can run.

### B. No Railway volume required

Production candidate accounting was redesigned to use the existing Postgres database.

Explicit activation mode:
- `NEWS_ACCOUNTING_BACKEND=postgres`

AI request budget:
- atomic daily rows in tiny `news_ai_requests` table
- cycle cap remains process-local and explicit
- daily cap is atomic across processes
- reservation happens before outbound AI HTTP and is never refunded
- existing SQLite/file backend remains only for offline/legacy regression fixtures

Single News owner:
- Postgres advisory lock per News cycle
- every scheduler tick independently reacquires ownership
- if a process/connection dies, the next cycle must acquire again
- duplicate writers cannot execute the same cycle concurrently
- no persistent Railway volume, no extra Railway storage resource

Data-only mode can run without an AI key or AI request limits when:
- NEWS_MAX_AI_ARTICLES=0
- NEWS_DATA_NEWS_ENABLED=1
- translations/history are off
- accounting backend is Postgres.

### C. xKiro free-only AI

`bot/free_ai_router.py`:
- model IDs must end in `:free`
- default writer/validator: `qwen/qwen3.5-397b-a17b:free`
- live public /v1/models entry must say `access_tier=free`
- any explicit `pay_as_you_go=true` is refused
- authenticated /v1/usage must show remaining free tokens >0 or an uncapped/null value
- missing catalog/usage verification fails closed
- 429 pauses the AI lane for that run
- no automatic paid fallback
- OpenAI remains available only as explicit legacy code requiring NEWS_ALLOW_PAID_AI=1.

### D. Original source-story factual gates

Source-based stories require:
1. source extraction/freshness/quality
2. deterministic numbers and source-overlap checks
3. exact protected proper-name preservation
4. no direct quotes in automated output
5. full paragraph/length quality
6. separate free-model fact validator
7. taxonomy conflict hold before DB write

Dedicated sport feeds may supply trusted sport context only when:
- feed is statically curated as dedicated
- article text has no conflicting sport evidence
- feed sport matches classifier result

Cross-product feeds such as EA general press releases remain mixed and cannot silently stamp EA Sports FC.

### E. Source coverage

Configured discovery exists for 40 concrete sport slugs; the 41st registry row is the generic esports parent.

Concrete esports children have paths:
- EA Sports FC
- Counter-Strike
- League of Legends
- Dota 2
- VALORANT
- Call of Duty
- Overwatch
- Rocket League

Expanded free RSS includes existing BBC/official/Valve/USTA/FIVB/etc plus:
- AFL official RSS
- BBC badminton
- BBC field hockey
- BBC table tennis
- BBC water polo
- EA press-release discovery, mixed classification

First-party official index adapter covers candidates:
- IHF handball via active Media Centre landing
- UEFA futsal current News sitemap
- VALORANT Esports
- LoL Esports
- Call of Duty League
- Overwatch competitive/esports items
- Rocket League competitive News

Runtime remains robots-aware, same-host, bounded, timestamp-required and fail-closed. Configured does not mean every source is runtime-proven yet.

### F. Cached translations

`bot/news_translations.py`:
- English is always primary
- one free AI request translates one already-public article into sr/es/de/fr/it/pt
- translations run only after English source-ingestion work
- explicit `NEWS_TRANSLATIONS_ENABLED`
- explicit `NEWS_TRANSLATIONS_PER_CYCLE` in range 0..3
- uses existing ArticleTranslation table
- exact numeric token preservation
- exact protected proper-name preservation
- Serbian Latin-only, Cyrillic rejected
- links/incomplete JSON rejected
- long body >12000 chars is held instead of partially translated
- failures never hide English article
- provider/model remain internal

Frontend branch now actually reads existing:
`GET /articles/{slug}/translation/{language}`

Reader behavior:
- English language does not call translation endpoint
- language switch does not refetch English article
- ready translation overlays title/summary/body
- missing translation falls back to English
- view counting and related stories are retained.

### G. One-shot xKiro synthetic probe

`news_xkiro_quality_probe.py` is ready but NOT deployed.

Before generation it now verifies:
- live model catalog contains the exact model as free
- pay-as-you-go is not enabled for it
- authenticated free-token remaining is positive/uncapped

Fixture gate:
- all locked proper names exact in all languages
- every source numeric token must remain
- no unsupported numeric token
- English expected length
- Serbian Cyrillic rejected
- still requires manual factual/language review
- database is never accessed
- no article publication

## Activation variables still missing from Railway service

Current safe service intentionally does not yet have the new candidate variables. Before real worker activation, candidate needs explicit values such as:

- NEWS_ACCOUNTING_BACKEND=postgres
- NEWS_AI_PROVIDER_MODE=xkiro_free
- NEWS_XKIRO_WRITER_MODEL=qwen/qwen3.5-397b-a17b:free
- NEWS_XKIRO_VALIDATOR_MODEL=qwen/qwen3.5-397b-a17b:free
- NEWS_DATA_NEWS_ENABLED=1
- NEWS_TRANSLATIONS_ENABLED=0 or 1 only after runtime probe decision
- NEWS_TRANSLATIONS_PER_CYCLE=0 initially, then a small value such as 1
- NEWS_HISTORICAL_REPAIR_ENABLED=0
- NEWS_EXPANDED_FEEDS_ENABLED initially conservative until source runtime probe
- existing explicit AI request caps retained
- no NEWS_AI_LEDGER_PATH/RAILWAY_VOLUME_MOUNT_PATH required in Postgres mode

## Next real external gate

The remaining blocker is no longer code/CI/storage design.

Next step requiring an actual deployment:
1. deploy exactly one bounded xKiro synthetic quality probe to existing hopeful-blessing
2. keep NEWS_WORKER_ENABLED=0 and no DB publication
3. inspect generated English + Serbian Latin + other language output
4. restore safe one-shot service state
5. if quality passes, merge/activate backend in controlled stages:
   - data-only Result News first
   - source-based free AI second
   - expanded sources
   - cached translations last
6. merge/deploy frontend translation reader only when backend translation cache lane is ready.

Do not skip the synthetic provider-quality gate merely because all code tests are green.
