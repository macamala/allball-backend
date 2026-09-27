# NinkoSports News05 — unified self-healing News system — 27 September 2026

## Status

**IMPLEMENTED AND FOCUSED-GATE GREEN ON ISOLATED NEWS BRANCH. NOT MERGED TO MAIN. NOT DEPLOYED OR ACTIVATED IN PRODUCTION.**

Branch: `news/source-coverage-20260927-05`
Production base/ancestor: `e844681d794d8303623e48a2b079fdcd33dc545d`
Exact runtime/test commit accepted by the final focused gate: **`146a6c7c51f42ce670f7983683d3074c9a681c41`**
The only later pre-checkpoint change was restoring `.github/workflows/news05-self-healing.yml` to manual-only; runtime code did not change.

Final focused GitHub Actions run: **36304710425**
Job: `news-self-healing`
Result: **SUCCESS — 221 passed, 0 failed, 0 errors, 12 deprecation warnings, 2.53s.**

This checkpoint is documentation-only and does not authorize a production deploy.

## What “one News system” now means

RSS and first-party official HTML are discovery adapters only. After discovery every story enters the same pipeline:

`source discovery -> canonical URL/dedupe -> freshness -> source article facts -> independent sport/competition classification -> writer router -> confirmed correction memory -> deterministic fact-lock -> corrective retry -> quality/originality gate -> taxonomy -> public index`

There is no separate “esports HTML publisher” and no separate RSS publisher.

### Source coverage

- Canonical News sports: **41**.
- Existing prepared RSS/Atom discovery: **35/41** scopes.
- Six former RSS gaps now use bounded first-party HTML discovery:
  - EA Sports FC / FC Pro
  - League of Legends
  - VALORANT
  - Call of Duty
  - Overwatch
  - Rocket League
- The source catalog is unified in `bot/news_sources.py`.
- Official HTML discovery is bounded, same-host, robots-aware, freshness-gated and metadata-only before the shared article extraction path.
- Locale-neutral LoL/VALORANT `/news/...` links are accepted because official sites may redirect them to a locale path; unrelated hosts remain rejected.
- Discovery source hints do not stamp the final sport. Article evidence must independently classify.

Public accessibility is not treated as a licence to copy publisher prose/images. New publication still requires original NinkoSports copy from sufficient source facts; HTML discovery deliberately supplies no publisher image candidate.

## Error prevention and self-correction

### 1. Deterministic fact-lock outside the writer

`bot/news_fact_guard.py` runs outside all writer models. It blocks, among other things:

- unsupported numeric values;
- copied source prose / excessive phrase overlap;
- automated direct quotations;
- unsupported known teams/people;
- newly introduced multi-word proper names;
- unsupported acronyms;
- unsupported month/day references;
- newly introduced high-risk claim families such as transfer, injury, discipline, result, retirement, death and appointment;
- generated copy whose independently recognized sport disagrees with the source article;
- clear competition mismatch.

Passing this gate is an additional safety barrier, not a claim that software can prove every sentence true.

### 2. Corrective retry

A draft that fails fact-lock is never committed. The failure reason is reduced to a stable non-secret reason code and sent to one bounded corrective rewrite. The router deprioritizes the first writer so another configured writer is preferred for correction. If the corrected draft still fails, the story is held/quarantined and is not published.

### 3. Incident memory

New table `news_incidents` records blocking observations with source URL/host, sport, phase, stable reason, writer provider/model and bounded draft excerpt. Source prose is not copied into the incident record.

Open blocking incidents prevent an article from becoming public through `public_index.py`.

### 4. Confirmed correction memory

New table `news_correction_rules` stores only staff-confirmed rules:
- exact phrase replacement;
- block phrase.

Rules may be scoped to one source host, one sport, or global scope. Arbitrary regex/executable rules are intentionally unsupported.

Automated observations do **not** become permanent truth by themselves. This prevents the system from “learning” its own hallucination.

### 5. Staff correction API

`news_feedback_api.py` adds moderator/admin-only endpoints:
- list incidents;
- list active learned rules;
- dismiss a false alarm;
- correct article title/summary/body/sport/competition;
- resolve/confirm an incident;
- optionally create a confirmed correction rule;
- re-evaluate public eligibility and bump the public cache.

Mutations require existing auth + CSRF and a moderator/admin role.

### 6. Writer trust and circuit breakers

Persistent trust:
- a writer provider/model is excluded after repeated **confirmed** incidents inside the configured time window.

Short-lived automatic trust:
- deterministic fact/quality rejects are counted within the current worker cycle;
- after three rejects that provider is held for the rest of that cycle;
- this short-lived penalty resets next cycle and is not persistent “learning”.

This gives fast protection without letting an automated heuristic permanently blacklist a model.

## Multi-writer router

New `bot/news_writer_router.py` puts all writers behind one interface and one durable request budget.

Production-capable adapters implemented only for providers with prior actual generation evidence:
- **Groq** — default model `openai/gpt-oss-20b`;
- **Cloudflare Workers AI** — default model `@cf/qwen/qwen3-30b-a3b-fp8`;
- **OpenAI** — retained as a supported fallback when explicitly/configurably available.

The router:
- is free-first by default among configured credentials;
- can be explicitly ordered with `NEWS_WRITER_ORDER`;
- rejects unknown/duplicate routing names;
- skips missing credentials;
- honors the persistent writer-trust policy;
- fails over on HTTP/unusable completion;
- holds an unusable provider for the rest of the current cycle;
- records the actual provider/model that produced the draft;
- prefers a different writer for fact-correction retry;
- uses the same shared durable `NEWS_AI_LEDGER_PATH` reservation for every real Groq/Cloudflare request;
- reuses the existing OpenAI adapter, whose bounded HTTP attempts are already individually reserved.

No provider is allowed to bypass fact-lock, correction memory, originality, classification or public-index gates.

Xkiro is NOT a production writer adapter yet because its account quota was verified but an acceptable generation path/model was not previously proven. LLM7/Airforce/Z.ai/Nara are also not promoted into the production router merely because credentials/catalogs exist.

## Startup / deployment safeguards

`news_runtime.py` no longer requires OpenAI specifically. Guarded startup accepts any valid configured writer credentials from the supported router and rejects invalid explicit writer orders.

`deploy/news/preflight.py` now includes the unified writer/source/fact/learning modules in the inspected backend artifact.

The existing requirements remain:
- explicit worker enablement;
- exact News Railway service identity;
- Results writer/scheduler flags explicitly off;
- PostgreSQL configuration;
- bounded fetch/article settings;
- legacy repair acknowledgement;
- explicit per-run and per-day request limits;
- historical/expanded-feed booleans;
- durable ledger under a verified persistent volume;
- single cooperating News owner lock.

No request is authorized merely because a provider key exists.

## Exact focused validation

Run **36304710425** covered:
- `tests/test_news05_self_healing.py`
- `tests/test_news05_unified_sources.py`
- `tests/test_news05_writer_router.py`
- `tests/test_c22_news_runtime.py`
- `tests/test_c22_news_scheduler.py`
- `tests/test_news_deploy_contract.py`
- retained News03 policy / HTTP / integration tests
- retained classifier tests

Result: **221 passed, zero failures/errors.**

An earlier intermediate run failed and was not relabelled successful. Its failures exposed Mock-DB compatibility and fixture-order issues; those causes were fixed before the final run.

## Isolation from Live Scores

Current branch compare against main is ahead-only and touches no `collector/` result/fixture/score implementation file. Changes are limited to News/article infrastructure, additive News tables/API, public article eligibility, documentation and News tests.

This does not replace a combined full regression gate if the branch is later merged into production main, because shared `models.py`, `app.py` and `public_index.py` are touched.

## Production status / next release boundary

No Railway Agent, Railway config mutation, production DB write, AI generation, public article publication, main update, frontend update, Live Scores change or production deployment occurred in this News05 implementation pass.

The existing production News service remains disabled/probe-bound from the prior free-provider trial. A real release must deliberately:
1. reconcile current main at release time;
2. run the combined regression gate because shared backend files changed;
3. deploy the API/schema-compatible code before activating the News worker;
4. restore the News service from the one-shot probe source/start to the guarded scheduler;
5. verify persistent ledger volume and explicit request caps;
6. explicitly select/approve the writer order;
7. enable expanded sources if the 35-scope RSS expansion is intended;
8. perform bounded real source -> writer -> fact-lock -> DB -> public acceptance.

Do not claim “zero errors guaranteed”. The implemented policy is instead: **uncertain or unsupported copy does not publish; detected mistakes can be corrected, confirmed corrections become reusable rules, and repeatedly unreliable writers are isolated.**
