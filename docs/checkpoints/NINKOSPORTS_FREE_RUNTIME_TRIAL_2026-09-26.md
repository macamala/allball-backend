# Actual free-provider runtime trial — 26 September 2026

## Outcome

Actual bounded provider requests ran from the EXISTING Railway News service. This is no longer just key storage or a local network attempt. Five metadata paths replied HTTP200; Groq and Cloudflare additionally produced a synthetic English brief and six translations. **Neither initial generated sample is approved for publication. Zero new public articles. Regular News ingestion and website article translation remain unactivated.**

The source-binding/staging obstruction was resolved without deleting a service. Production API/results/frontend code was not changed in this turn. This record does not close all-sport freshness or the 500-original/3000-translation capacity target.

## Exact code and deployments

Base: main `e844681d794d8303623e48a2b079fdcd33dc545d`.
Branch: `ops/news-free-probe-20260926`.
Only two new executable files, no edits to existing runtime:

- `news_free_probe.py` at commit `ab94f348aa62cb0e3007b6cabe3e379cb1c11de9`.
- `news_free_generation_probe.py` added at commit `aa7aef864b88234990b12df24a96e7421e322f99`.

The scripts are bounded, existing-News-service-identity guarded, require NEWS_FREE_PROBE=1 and --once, do not import app/database/scheduler, and never publish. Secrets come from environment and are not written into source, reports or comments. Metadata is read from fixed intended-provider URLs; no credential is forwarded between providers. No redirects or automatic retries.

Existing service: hopeful-blessing / `be857be7-a029-4663-81c7-bcde75efc482`.
Production environment: `cb27d851-9198-47c8-a733-8356e8b6cf63`.

1. Actual deployment `0007865f-98f9-4b87-8093-fb8df9a32aa0`, source ab94f348, started 13:00:19 UTC; NEWS_FREE_PROBE_REPORT logged 13:00:27 UTC.
2. Actual deployment `abbc5c5c-97a2-495e-86b4-38e73e19c5da`, source aa7aef864, started 13:04:50 UTC; NEWS_FREE_GENERATION_REPORT logged 13:05:13 UTC.

Both deployments report SUCCESS, which only describes completed deployments/probes, NOT editorial acceptance or a running scheduled publisher.

## Actual provider evidence

| Provider | Exact observed outcome | Boundary |
| --- | --- | --- |
| Groq | GET models200. POST openai/gpt-oss-20b200, finish_reason stop, seven-language JSON. 218 input /714 completion /932 total tokens, 1.08s request. | Metadata does not establish account quotas. The generated sample failed manual factual/language review below. No 120B generation completed. |
| Cloudflare | Token verify200 active. Actual @cf/qwen/qwen3-30b-a3b-fp8 execution200, success and seven-language JSON, finish_reason stop. 134 input /2280 completion /2414 total tokens, 22.67s. | This additionally proves Workers AI execution access for this token/account. Sample is not approved below; not long-article throughput proof. |
| Xkiro | Authenticated /v1/usage200: limit_per_day500000, remaining500000, used_today0. | Actual account quota, not an advertised million. No generation request completed; no model access-tier list was read in this trial. |
| LLM7 | Authenticated models200,60 model records. Follow-up metadata shows turbo/pro tiers and nonzero price fields on the returned entries. | No explicit zero-cost generation route established for this key; no generation sent. Do NOT infer every call is paid OR that all listed models are free from this alone. |
| Api.Airforce | models200,623 records. Follow-up free-suffix filter returned gemma3-270m:free only, max_tokens4096; catalog also listed a price field. | None of the reviewed larger :free variants were available; no generation sent. Do not count 623 usable free writing models or treat the tiny model as accepted journalism capacity. |
| Z.ai | One explicitly free glm-4.7-flash request returned429. | No successful draft. Error body was not logged, so the precise quota/concurrency/capacity cause is NOT established. No retry or model rotation. |
| NaraRouter | Authenticated /v1/models returned403. | Access failed from Railway; exact entitlement/security cause unproven. No retry/bypass and no generation. The advertised7M/day cannot be counted as available capacity for this account yet. |

Calls did not enable paid fallbacks, web-search/image tools, top-ups or subscriptions. Groq/Cloudflare samples used the user-selected free-tier setup and were bounded to4096 output tokens each; provider billing dashboard totals were not independently retrieved. Normal Railway build/runtime and the Agent are separate platform consumption, not a claim of zero total platform cost.

## Manual quality review: do not auto-publish these outputs

The intentionally fictional source supplied ONLY a North Club2-1South Club practice-match final and1-0 halftime. It did not supply an early goal or an uninterrupted lead.

Groq's English introduced an early lead and holding it throughout the second half; those are not supported by the two snapshots. Its Serbian included the incorrect expression "rani predlog" and unnatural wording. Therefore the short fixture is rejected, despite valid JSON and HTTP200.

Cloudflare preserved the two numerical facts but translated the proper club names into generic North/South clubs, omitted the requested longer length and had awkward Serbian grammar. Not accepted as the final naming/language behavior. Its refusal to invent a long article from two facts is preferable to padding, but this does not satisfy the intended reader output contract.

A larger model/separate translation request with exact name preservation was prepared as an additional bounded command. Railway.update-service for that command returned an OpenAI safety-status block. It was NOT applied, retried, re-encoded, split, put in a workflow, or sent through another tool. Fresh service config confirms the previous `python news_free_generation_probe.py --once` remained. Thus no improved-prompt, Groq120B or Xkiro model/generation evidence exists from that proposed third trial.

The old News04 runtime block remains unrelated and unapplied. No blocked News04 code was copied into these scripts.

## Staging cleanup and preservation

Initial mixed patch `db7eb99e-400a-4e62-ba03-c10610fea2f4` contained old audit-scheduler-lease pending isDeleted:true, News source and mistaken placeholder variables. Snapshot is issue8 comment5846459310; current protected production state and pending intent were recorded before cleanup.

One necessary Agent call verified the exact allowlist, discarded the UNCOMMITTED mixed batch without applying any deletion, then staged ONLY correct News source/build/start. Direct status independently confirmed one News-only resource change, no unrelated deletion/variables, before native accept-deploy. Live audit-scheduler-lease was preserved. Its old pending deletion was parked in the saved snapshot, not executed or automatically restaged.

A second necessary Agent call updated only the fixed source commit for the second sample because the direct service tool cannot change repository pins. Direct native operations handled variables, status, logs and deployment. No more Agent calls were made. No new service, volume, subscription, diagnostic database, schema migration or production article/result write.

## Safe final state

After completed probes and the blocked third command, direct set-variables with skipDeploys=true explicitly set NEWS_FREE_PROBE=0, NEWS_WORKER_ENABLED=0, WORKER_DISABLED=1. This prevents accidental re-execution of the samples on a later deployment; it does not claim hot-reloading a running process. The completed program was one-shot and restart policy remainsNEVER.

Current committed News source is repo macamala/allball-backend, branch ops/news-free-probe-20260926, pinned aa7aef864b88234990b12df24a96e7421e322f99, root/, Dockerfile deploy/news/Dockerfile. Start command remains `python news_free_generation_probe.py --once` for the last completed trial, not the regular scheduler. Staged changes:null, pendingWork:[] at final direct read.

API deployment remains ccf0c8b2-c64e-4eb7-b576-988965ae502e; results-worker829672cf-c03e-4b49-b403-63e0efaa4f95; diagnostic services remain present. No frontend redeploy. Existing production rewrite_ai still points to OpenAI; connecting free providers to scheduled publication and persistent article translation is NOT done by these standalone probes. Do not turn on the existing writer assuming it uses the free keys.

Next work needs the normal authorized resolution of the blocked follow-up, a real free-provider production adapter with no paid fallback, factual/name-preserving output review, retained single-owner/durable accounting and source-to-public integration. New keys are not the first unresolved problem. Do not promise500originals/3000translations from these short samples or claim the website now has fresh generated content.
