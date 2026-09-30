# NinkoSports News football menus — 2026-09-30

User scope: improve the existing football News menus and use the supplied Routeway key. The user clarified that the existing system is already built: arrange menus and routing, do not rebuild sources. No Railway AI agent, no Live Scores changes.

## Published changes

- Frontend master: 352e0b96c312fb3d560d43ac38f80c01fb8038e0. Tested tree 429f8debb76723f3621dcd9a57ed77bb8afc8007.
- Frontend production service df4b231a-fcbc-4d89-bef8-d9028d03b473, project d2187a78-90d0-437a-871b-10e16ba8d07c, deployment 8aba1cc2-9d91-46f9-9d49-b92f831a3886 SUCCESS.
- News backend branch ops/news-free-probe-20260926: a7f3334485f6a45300dc32a97c00c1296a470ee4. Tested tree feb880aac1cab15d2724e92590723b81cbe4b0d9.
- News deployment 5d4499ce-9585-4e06-97c4-708b1fd5dc5e SUCCESS; service be857be7-a029-4663-81c7-bcde75efc482, project 17f6ebff-0f6b-42dd-be86-35ca9ca40301.
- /football/other-leagues now shows a searchable country-grouped catalog of 76 competitions: 64 domestic leagues across 32 countries and 12 international entries. Most countries have first and second tiers; Australia has separate men/women top leagues.
- Each entry has a canonical route, readable label, its own exact News league filter, and a switcher on league pages. Existing main league URLs are preserved. SuperLiga Srbije and Nations League are pinned in football navigation.
- Existing pagination limit of 80 now has Show more for football, maintaining the exact competition filter and removing overlapping IDs. League navigation remounts scoped state to prevent stale cross-league cards.
- New strings translated into all seven existing interface languages. Styles are scoped to News league components.
- Backend competition catalog matches the frontend manifest byte-for-byte. Adds missing Nations League and extended football competitions; specific CAF/AFC competitions receive the same continental recognition as UEFA, avoiding generic Champions League collisions.
- Bounded maintenance assigns tags to existing public AI football reports only with explicit headline evidence and high resolver confidence. It preserves article text, timestamps, images and public/held flags. Production at 05:06:33 UTC: tagged=8, scanned=124.
- No feeds/source configuration was rebuilt or changed.

## Routeway

Key stored only in ROUTEWAY_API_KEY on the existing News service; never in git or this checkpoint. NEWS_ROUTEWAY_FREE_ENABLED=1. Fixed approved route muse-glimmer-30b:free at official api.routeway.ai, no configurable paid alias or fallback. Before use, require current available=true and numeric zero input/output pricing in the live catalog (cached for five minutes). Shared News actual-request budget, independent-provider validation, existing quality/factual/image/dedupe gates. One concurrent call; 13-second spacing; daily/minute 429 holds shared across all purposes. No key/model rotation to bypass limits. HTTP redirects disabled.

Official docs read September 30: https://docs.routeway.ai/getting-started/models.md and https://docs.routeway.ai/getting-started/rate-limits.md. Docs disagree 20 vs 5 RPM; conservative 5 RPM used, 200 RPD stated in both. Public catalog confirmed zero-cost route. Authenticated free smoke test returned HTTP 200 and valid JSON for muse-glimmer-30b:free. DeepSeek free probe returned repetitive invalid JSON and was not enabled. Runtime writer usage of Routeway had not yet appeared in the new deployment logs at checkpoint; next scheduled cycle chooses among available providers normally.

## Validation and limits

382 targeted backend tests passed; 12 frontend tests passed; production frontend build passed. Tested price/availability checks, incomplete/changed-model rejection, quota and credential-safe logging, independent validation, competition IDs and collision resolution, existing tag repair without republishing, menu search, exact API filters, cross-route stale-state clearing and pagination.

Cloud browser confirmed the production directory, 76 visible links, search for Serbia and England, both league tiers, and a Premier League page with the correct selected menu and 11 Premier League stories. Local preview browser was blocked for localhost; production verification succeeded. Live API/worker deploy IDs remain a6018808-ec70-44a9-8ddc-5a65b30f9c57 and 25287c7e-08a8-46f8-aa3b-0d85ba6eaf53.

Catalog presence does not assert two independently verified publishers per competition or a current article in every league. Source coverage remains as previously configured. The existing public API recent list remains 72 hours; the existing archive search link remains available. This change does not claim a complete all-time browse API, all languages caught up, or 500 stories/day. Retain earlier checkpoint for remaining quality/source/translation work.
