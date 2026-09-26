# NinkoSports News checkpoint #05 — 26 September 2026

## Safe stopping point

This checkpoint intentionally stops before any production activation or merge.

- Working branch: `news/free-router-20260926-05`
- Base production/main News checkpoint: `e844681d794d8303623e48a2b079fdcd33dc545d`
- Last implementation commit before this checkpoint: `3b5314dc03c1b580d30e4638d4687ee800fcfa03`
- Production News service was NOT switched to this branch.
- No News scheduler was activated.
- No new public article was written from this branch.
- Live Scores/API/results-worker/frontend production code was not changed by this News pass.
- Railway Agent was not used in this continuation.

## Free-provider findings retained

Existing isolated probe evidence remains on `ops/news-free-probe-20260926`.

- Groq generation worked but the tested sample introduced unsupported chronology and failed editorial review.
- Cloudflare Workers AI generation worked but the tested sample changed proper names and failed editorial review.
- xKiro authenticated usage returned an observed free allowance of 500,000 tokens/day for the connected account.
- The follow-up production-quality xKiro probe is implemented in `news_xkiro_quality_probe.py` using a fixed `:free` model ID, but it has NOT yet been executed on Railway.
- LLM7/Airforce/Z.ai/Nara remain non-production candidates until stronger zero-cost + quality evidence exists.

## Implemented on the candidate branch

### 1. Free-only AI router

Added `bot/free_ai_router.py`.

- Default candidate provider mode is xKiro free-only.
- Writer/validator model IDs must end in `:free`.
- No automatic paid alias fallback.
- No provider rotation into an unverified paid route.
- Every actual request still consumes the existing shared durable News request ledger.
- Existing OpenAI path remains only as an explicit `openai_legacy` mode gated by `NEWS_ALLOW_PAID_AI=1`.

### 2. Stronger factual safety

Updated `bot/rewrite_ai.py`, `bot/fetch_sources.py`, and `bot/news_policy.py`.

- Prompt explicitly requires exact proper-name preservation.
- xKiro candidate draft must pass a second free-model fact validator before DB write.
- Unsupported claims or changed names fail closed.
- Deterministic number gate remains.
- Deterministic proper-name preservation gate was added in addition to the model validator.
- Writer-visible-source bounds are respected so the deterministic gate does not require names the model never received.

### 3. Startup/deploy guards

Updated `news_runtime.py` and `deploy/news/preflight.py`.

- xKiro free-only is the candidate default.
- Missing xKiro key fails closed in free mode.
- Any configured xKiro writer/validator model not ending in `:free` is refused.
- Unknown provider mode fails closed.
- Legacy OpenAI cannot start unless explicit paid opt-in is present.
- `bot/free_ai_router.py` is required in the News artifact.

### 4. Offline tests added

Updated `tests/test_news_deploy_contract.py` and added `tests/test_news_free_ai.py`.

Coverage includes:

- free model suffix enforcement;
- missing-key fail closed;
- legacy paid OpenAI explicit opt-in;
- invalid/unsupported validator responses fail closed;
- changed proper names fail closed;
- deterministic proper-name preservation.

These tests have been committed but a full branch CI/test run has NOT yet been proven in this continuation.

### 5. New zero-AI NinkoSports data-news lane

Added `bot/data_news.py`.

Purpose: create original NinkoSports result briefs from the already-public canonical Live Scores API, rather than rewriting another publisher.

Current implementation:

- reads only finalized events from the NinkoSports public `/sports-data/recent` endpoint;
- never contacts upstream score providers directly;
- uses public rows after canonicalization/dedupe/provider-branding policy;
- produces deterministic competition/day result briefs;
- never invents scorers, incidents, quotes, injuries, tactics or statistics;
- no AI request is consumed;
- idempotent Article identity uses `ninkosports-results:<day>:<sport>:<competition>`;
- public source/provider branding is not exposed by the existing News serializers;
- writes trusted taxonomy resolution from the canonical event metadata.

IMPORTANT: this lane is implemented but NOT yet connected to `bot/scheduler.py`, NOT added to News startup configuration, and NOT tested against production DB. That is the next integration step, not a completed production feature.

## Important capacity finding

The current C22 request-ledger guard allows at most 200 AI requests/day.

With the proposed free writer + fact-validator two-call path, the theoretical upper bound is roughly 100 accepted new AI-written stories/day before retries/rejections. This is not enough by itself for broad all-sport freshness, so the deterministic Live Scores → Result Brief lane is strategically important because it adds broad fresh result coverage with zero AI calls.

## Current source coverage finding

The base feeds plus expanded verified RSS catalog cover many sports, but not all 41 sports equally and some endpoints are stale/undated or metadata-only. The intended architecture is therefore:

1. NinkoSports canonical Live Scores → deterministic result/ranking/result-event briefs at zero AI cost.
2. RSS/source extraction → original free-AI stories for transfers, interviews, injuries, previews and wider reporting.
3. Future translations use the same free-only/validated provider architecture but remain a separate phase.

## Do NOT do automatically on resume

- Do not merge this branch to main yet.
- Do not start the regular News scheduler yet.
- Do not enable historical repair.
- Do not switch on expanded feeds blindly.
- Do not publish an xKiro-generated real article until the synthetic quality probe passes.
- Do not spend Railway Agent calls unless direct Railway/GitHub actions genuinely cannot do the required operation.
- Do not disturb Live Scores production while News work continues in parallel.

## Resume tomorrow

Resume from this checkpoint and do, in order:

1. Run branch/offline tests and fix any failures.
2. Execute ONE bounded xKiro `:free` synthetic quality probe on the existing News service, with News worker disabled and zero DB publication.
3. Manually inspect factuality, exact proper names, Serbian Latin and other translations.
4. If it passes, wire `bot/data_news.py` into the guarded News cycle with explicit `NEWS_DATA_NEWS_ENABLED` gate and tests.
5. Add data-news artifact/preflight coverage.
6. Verify the deterministic result brief against real public NinkoSports events without publishing first; then run one bounded DB write only if the branch tests and taxonomy/public-index checks pass.
7. Continue broad free source coverage for sports that still lack good non-result reporting.
8. Only after those checks prepare a production activation/merge plan.
