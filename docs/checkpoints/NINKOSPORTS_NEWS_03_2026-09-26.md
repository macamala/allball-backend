# NinkoSports News03 — 26 September 2026

## Status and safe handoff

**Bounded backend candidate tested and saved. NOT deployed. NOT all-sport production freshness acceptance.** The primary Live Scores chat remains the only integration/release owner; backend issue8 tracks News, issue6 tracks primary release coordination.

User explicitly said the other chat is deploying News01/02 and Live Scores, and authorized further News development for a later release: fresh coverage of all existing sports and full original NinkoSports articles rather than external-link cards or publisher copies. Work therefore moved to a NEW branch, leaving the old handoff frozen.

- New branch: `news/coverage-originality-20260926-03`.
- Frozen parent: News02 record `99cc5f0a1d0951e286c58bd1176d729141a28f02`.
- Exact tested News03 runtime/test candidate: **`f08633d0221fbf9d9850f291dbab4ffe927c11c7`**.
- Earlier metadata commits on this new branch: `734b810fe978fcaa59b7a59ea3b4c69ff42aa04c`, then `bff0c2e41c4e94c17c9f7ec813f53b655fd204ad`.
- This later checkpoint commit changes documentation only.

Final read of old `news/isolated-20260926-01` still returned99cc5f0. Main advanced independently from cf192f22da637b9b54495cd5fc2ba238abbfbee3 to **9db4b7cd3b83aac57981cd2769fec089d7786b1f** during this work. Comparing News02 record to that main showed merge-base24714028a8e3a1e3b6ac679bd6db703beeddffea and seven primary-side files (C18 collector changes/tests plus combined-offline-gate); no overlapping News03 runtime file in that snapshot. This is not a guarantee about a later head. Never reset main to this branch's old base or claim these tests include later C18 integration.

No main/master update, merge, PR, deploy, Railway operation or Agent, production DB mutation, production ingestion, real AI request, new subscription, source-policy bypass, or frontend change occurred in this workstream. Source metadata GETs and ordinary CI dependency downloads did occur. A prior safety-blocked C18 workflow was not modified, retried or bypassed.

## Exact implementation

Existing News runtime files changed:

- `bot/fetch_sources.py`: original-only admission; source freshness before extraction and publication; newest eligible feed entries selected before per-feed limit; independently classified, round-robin sport queue; explicit actual-request budget context.
- `bot/rewrite_ai.py`: every attempted request requires an atomic budget reservation; rejected/timeout/429 and length retries still consume reservations. Truncated/refused responses cannot become publishable copy. Prompt requests independent prose, no invented reporting or direct quotations, and necessary in-sentence attribution instead of pretending another outlet's exclusive is ours.
- `bot/feeds.py`: original FEEDS entries and values retained, expanded discovery opt-in, exact URL dedupe. FEEDS representation was compacted; do not confuse formatting changes with removed feeds.
- `bot/pipeline.py`: legacy entrypoint delegates to the same guarded original-only pipeline instead of maintaining a separate RSS-summary publishing path.
- `repair_content.py`: no re-extracted publisher prose pasted as fallback; historical scans are explicit opt-in. Summary repair requires an active request-budget context even when explicitly invoked. Existing clean/salvage logic is retained, not a retroactive originality audit.

New modules: `bot/news_policy.py`, `bot/news_budget.py`, `bot/news_feed_http.py`, `bot/news_verified_feeds.py`, `bot/news_source_catalog.py`.
New tests: `tests/test_news03_policy.py`, `tests/test_news03_budget.py`, `tests/test_news03_http.py`, `tests/test_news03_integration.py`.
New audit files: `audit/news03_source_probe.py`, `audit/news03_extra_probe.py` and three `.github/workflows/news03-*.yml` files.

No collector/score worker, shared app bootstrap, models, database module, public-read/homepage composition, News02 deploy/preflight/extract-date code, scheduler implementation, requirements, navigation, styles or frontend runtime changed. CI asserts those protected paths are byte-unchanged from the frozen News02 parent. CRLF-to-LF normalization enlarges fetch_sources/rewrite_ai textual diffs: review intent and reconcile rather than pasting a whole old file over newer main.

### What original-only means here

A successful original draft is required before a NEW article is stored. AI failure, no budget, no usable source body, malformed or empty output cannot fall back to copied publisher prose. Conservative draft checks hold direct source copies, excessive shared eight-word sequences, unsupported numeric values, automated direct quotations, redirect/read-more copy, source-banner footers and summary-sized output for substantial material. Short evidence supports a short brief, not invented filler.

Original source_url and publication time remain stored. The prompt no longer instructs the model to erase necessary attribution. Material needing unsupported mandatory credits must be held/reviewed, not stripped. Existing article links stay internal; this backend pass does not redesign article UI or remove existing legitimate image credits.

**These checks are heuristics, NOT factuality, language, plagiarism or legal certification.** Numeric-set matching does not verify who scored, names, dates in words or causal claims. The inherited English check is largely a Latin-character heuristic. Publisher terms, image rights, required credits, factual verification and output quality still require review. No historical article was rewritten, removed or certified original in production. Cross-publisher semantic story dedupe and persistent canonical tracking-URL identity remain further work; new queue dedupe is within a batch plus the retained database duplicate checks.

### Freshness and sport fairness

Known-timezone, nonfuture publication dates at most72hours old enter the new queue. Missing/naive/future/older dates are held with explicit reasons, never replaced by ingestion time. News02 publication-before-modification parsing stays intact. Each sport's newest items come first, then sports take turns; start position rotates over10-minute time slots. Tests cover all41 canonical News sports with123 synthetic candidates.

This prevents a fixed football-first queue, but is not a guarantee that every sport receives an article each day: scarce source material, classification, rejected drafts, cycle timing and the daily request cap can still constrain output. Stale homepage selections and historical rows remain separate shared-code work, not fixed by filtering new admissions.

RSS transport is bounded to HTTPS/public resolved addresses, a2MB body and a20-second read deadline with8-second socket timeouts. Robots disallow/unverified states, unsafe redirects and non200 responses stop the read. HTML landing pages cannot masquerade as RSS. DNS behavior depends on the platform resolver; this is not a network sandbox guarantee. Article-page extraction remains the existing separately reviewable extractor, not proven by RSS metadata.

## Actual all-sport source research

Two independent, bounded source metadata audits examined **68 candidate URLs across all41 active supports_news sports**. No AI or database work was used. Successful metadata is NOT permission to republish text/images, a working article extractor, or production coverage.

Observations:2026-09-26T06:37:05.991572+00:00 and2026-09-26T06:43:20.010289+00:00.

Combined states:22fresh RSS endpoints (21sports),8RSS stale/undated results,24HTML landing pages needing adapters,9HTTP errors,4unverified robots results,1access-blocked source. Of the8stale/undated results, IHF's parsed feed had0eligible HTTPS article rows and was NOT added. Thus the opt-in expansion contains **29usable RSS metadata endpoints for27sport scopes**, including7valid but stale feeds. Those stale feeds must produce a new eligible entry before admission. Freshness numbers are point-in-time observations, not a claim they stay fresh.

| Sport | Audited URLs | Prepared RSS | Fresh RSS at observation |
| --- | ---: | ---: | ---: |
| football |2|1|1|
| basketball |3|1|1|
| tennis |2|1|1|
| motorsport |2|1|1|
| american-football |3|1|1|
| ice-hockey |3|1|1|
| baseball |3|1|1|
| rugby |2|1|1|
| rugby-league |2|1|1|
| cricket |2|1|1|
| volleyball |1|1|1|
| handball |2|0|0|
| futsal |1|0|0|
| water-polo |1|0|0|
| field-hockey |1|0|0|
| australian-rules |1|0|0|
| netball |1|1|1|
| lacrosse |1|1|0|
| table-tennis |1|0|0|
| badminton |1|0|0|
| snooker |2|1|0|
| darts |2|1|0|
| boxing |2|2|2|
| mma |2|1|1|
| horse-racing |2|2|0|
| greyhound-racing |1|1|1|
| harness-racing |2|1|1|
| golf |2|1|1|
| cycling |2|1|1|
| athletics |2|1|1|
| swimming |2|1|1|
| winter-sports |2|1|0|
| esports |1|0|0|
| ea-sports-fc |1|0|0|
| counter-strike |1|1|1|
| league-of-legends |1|0|0|
| dota-2 |2|1|0|
| valorant |1|0|0|
| call-of-duty |1|0|0|
| overwatch |1|0|0|
| rocket-league |1|0|0|

There are14sport scopes without a prepared usable RSS adapter in this expansion. Existing mixed feeds are not counted as verified sport coverage. Valve game-news metadata is not automatically evidence of competitive match coverage; classification still applies. Some working RSS feeds expose no current items and cannot be labelled fresh just because the endpoint responds.

## Actual completed tests and evidence

**Run36225363508 / quality job108358227197 completed SUCCESS** at exact candidatef08633d0221fbf9d9850f291dbab4ffe927c11c7.

- **1,235 selected backend tests passed,0failures,0errors,0skips.** Includes the retained1,119-case News02 selection,22additional existing News cases, and **94new News03 cases**.
-71pure new policy/budget/HTTP cases also passed locally before the full environment run; they are a subset, not another71unique tests to add to1,235.
- Existing nested News Docker recipe built and its inspection preflight passed with Python3.12.14. No recipe or Railway configuration was changed.
- Combined tests ran with container `--network none` and ephemeral SQLite data. Mocked source text/AI responses prove deterministic paths, NOT remote AI editorial quality. A valid original fixture persisted its own body/source identity; failed/copied/unsupported drafts did not commit raw source text.
- Every runtime/test file transferred to GitHub matched the local prepared bytes in the downloaded tested-source archive. ZIP checksum/integrity, candidate marker, actual JUnit counts, preflight JSON and all source-SHA256 entries were independently verified.
- No frontend build/browser or actual-production acceptance was run in this backend-only pass; News01 remains its separate previous reader evidence. Later main/C18 integration must be retested by the primary chat.

| Evidence | Run / artifact | ZIP SHA256 |
| --- | --- | --- |
| Initial59source metadata |36224287029 /10900246067|1afd3c2388f5cbf147c7a6de08f3285959c7f7118efca16e83d240700d4dc537|
| Additional9source metadata |36224595913 /10900621257|c253981fabbacce5697b74396b707c67a20c91b6b3e34a78ced72f365515f435|
| Exact runtime/tests/image |36225363508 /10901105275|c1c5716f1d7276f9ee69dd39e5dffa5d3f1f0d1cee61b32f9308090dfa1917e0|

CI artifacts have30-day retention, not permanent backup. Code, tests, probes and this summary are committed durable records. No failed News03 quality run was relabelled successful; this tested candidate's quality run passed on its first execution. Metadata job success only means the audit completed, not that every source succeeded.

## Required later-release configuration and caveats

**Do not merge this into a running News worker without coordinating the new request ledger.** Missing key/valid ledger configuration or exhausted allowance prevents new ingestion; it does not delete existing articles. Reservations fail closed if storage cannot be written.

- `NEWS_AI_LEDGER_PATH`: absolute file path in an existing approved directory on genuinely persistent storage. This code does not create an unapproved directory or provision a Railway volume. Verify persistence across a restart; do not silently use ephemeral container storage. Multiple workers with separate local volumes do NOT share a global cap.
- `NEWS_AI_MAX_REQUESTS_PER_RUN`: actual reservations,0..20; defaults to the passed accepted-article allowance, not an extra free retry allowance.
- `NEWS_AI_MAX_REQUESTS_PER_DAY`: actual reservations per UTC day in the same ledger,0..200; default40. This is NOT a dollar cap, token-accounting dashboard, model-price guarantee or account-wide provider billing cap. Existing output max_tokens1800 remains. Choose actual release values with the user’s cost constraints; do not raise them automatically.
- `NEWS_EXPANDED_FEEDS_ENABLED=1`: reviewed opt-in to add the29metadata endpoints alongside the retained16enabled feeds, deduplicating exact URLs. Source/body/image rights and actual extraction still need acceptance.
- `NEWS_HISTORICAL_REPAIR_ENABLED`: absent/anything other than1 disables the legacy historical scans. Even explicit summary repair must run inside a reviewed active budget context. Do not blindly enable the old scan just to clear a flag.
- Existing News02 service identity/preflight requirements still apply. This pass did not change or bypass `NEWS_LEGACY_REPAIR_ACK`, bind a repository, or start the scheduler.

The primary chat must fresh-read issues6/8 and current heads, review only the News03 delta from99cc5f0, preserve its latest C18/other changes, configure the ledger safely and rerun combined tests/build before its later controlled release. Do not fast-forward production to this old-based branch or use a reset. It must then prove real source->extraction->original draft->database->public article flow, freshness, suitable images/categories and unchanged Live Scores on desktop/mobile.

**Remaining:**14missing usable source adapters; freshness alternatives for currently stale feeds; article-page extraction and rights verification; actual AI factual/editorial output; semantic duplicate handling; original-copy audit of existing stored articles; shared-homepage stale-selection behavior; live News health/cost evidence after a separate authorized release. Keep News issue8 open. Whole News and all-sport production freshness remain OPEN.
