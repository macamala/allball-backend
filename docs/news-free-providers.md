# News free providers

Only the Railway News service `hopeful-blessing` uses these settings.
Keep API and results-worker settings unchanged.

The pool supports Groq, Cloudflare Workers AI, and optional Mistral Free.
xKiro remains the free fallback/corrective route. Every HTTP generation attempt
uses the existing News request ledger. A writer cannot approve its own draft:
semantic validation must come from another provider. Deterministic fact,
taxonomy, originality, image, freshness and dedupe gates remain mandatory.

## Optional Mistral Free

1. Use a Mistral account in **Free** mode, without enabling pay-as-you-go.
   API keys do not reveal billing mode; confirm it in the provider console.
2. Add `MISTRAL_API_KEY` directly to the **hopeful-blessing** service variables.
   Do not paste credentials into issues, source code or chat.
3. Set `NEWS_MISTRAL_FREE_ENABLED=1` on that same service only after confirming
   Free mode. `NEWS_EXTERNAL_FREE_WRITERS_ENABLED=1` is also required.
4. The default model is `mistral-small-latest`; `NEWS_MISTRAL_MODEL` can override
   it only with a model available on the confirmed Free account.

The route is disabled by default, even if a key exists. No Mistral requests
have been production-verified without a configured Free-account key. Rate
limits remain provider-controlled: another route adds capacity but does not
guarantee 500 articles per day. A quota or auth rejection cools down that
provider across writing, validation and translation, without logging secrets.

## Optional Groq writer pool

`NEWS_GROQ_WRITER_FALLBACK_MODELS=openai/gpt-oss-20b` adds the documented
Groq Free Plan production model to the writer lane on the existing account.
It does not call the paid OpenAI API or change the account's billing plan.
No other fallback IDs are accepted. The fallback cannot serve as a validator
or translator; another provider must validate every completed draft.

Groq quota holds are model-specific only when the actual 429 response explicitly
names the requested model and a recognized token/request limit. Each route
obeys its Retry-After. Unknown/account-wide limits, billing errors and 401/403
hold all models. Cloudflare daily free allocation remains account-wide. Every
attempt, including a rejected primary request, still consumes the common ledger.
Two Groq models never count as two independent providers.

Groq references, checked 2026-09-29:
- https://console.groq.com/docs/models
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/model/openai/gpt-oss-20b

Official references, checked 2026-09-29:
- https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key
- https://docs.mistral.ai/admin/billing-usage/usage-limits
- https://docs.mistral.ai/api/endpoint/chat
