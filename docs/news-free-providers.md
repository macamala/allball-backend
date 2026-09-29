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

Official references, checked 2026-09-29:
- https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key
- https://docs.mistral.ai/admin/billing-usage/usage-limits
- https://docs.mistral.ai/api/endpoint/chat
