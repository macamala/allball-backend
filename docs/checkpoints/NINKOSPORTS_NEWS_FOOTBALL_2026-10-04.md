# NinkoSports News football checkpoint — 4 October 2026

## Scope and production

News only. Do not merge this branch into main or deploy the API/results worker as a shortcut. No frontend/mobile changes. No paid model, spend-limit, translation or provider-key changes. No Railway AI agent used.

- Repository: macamala/allball-backend.
- News source branch: ops/news-free-probe-20260926.
- Recovery/evidence branch: audit/news-football-completion-20261004.
- Original production commit: b62ecd517f0e6b6373145c4a745aa7ff4a669748.
- First tested/deployed commit: c446bd6e1b55c50ffffbe94247cca1e9457f1931; Railway deployment 18eb4b22-d10e-47bd-b112-a61e9aa471d2 SUCCESS at 05:41:26 UTC.
- Follow-up tested commit: 34885ab355b0dee6fae31d77278baf0c6af0a34b; staged changes contained ONLY the News service commitSha; deployment b7bf65ad-4986-4d25-9c71-a7142167c7bd triggered at 05:50:38 UTC. Final status must be read, not inferred from this checkpoint.
- Railway project 17f6ebff-0f6b-42dd-be86-35ca9ca40301, production cb27d851-9198-47c8-a733-8356e8b6cf63, News service be857be7-a029-4663-81c7-bcde75efc482 (hopeful-blessing).
- Unchanged API deployment a6018808-ec70-44a9-8ddc-5a65b30f9c57 and results-worker deployment 25287c7e-08a8-46f8-aa3b-0d85ba6eaf53, both September 27 and online in the actual environment read.

## Implemented and tested

1. Exact source-only Portuguese thousand-person counts (21 mil torcedores -> 21,000; 14 mil -> 14,000). Reject decimals, scores, money, ranges and unobserved quantities. Independent semantic validation still mandatory. Only the exact pre-05:22 UTC Sion unsupported-number hold can retry; no global holds or publication guards were disabled.
2. BET INFO daily betting-product rejection before writer calls. Betting investigations and ordinary league sponsorship reporting remain eligible.
3. Additional verified desks use the existing RSS and same-article extraction pipeline: Get Belgian and Dutch Football News (visible entry-content), FK Spartak Subotica (visible post-content). A known BeNe publisher-square logo is rejected. No artificial source dates, default logos, full-RSS body fallback, league, gender or membership guesses.
4. Explicit surfing/triathlon headlines, reviewed Record sections and the distinct O Parrulo–Valdepenas futsal fixture cannot be forced into football. Battlefield product announcements are not treated as sports news. Existing incidents retain the original records and copy.
5. Football league-menu maintenance now covers up to 600 recent public football rows rather than only 300, without changing its hard cap, original dates, prose or admission gates.
6. Follow-up: editorial-repair selection prioritizes football when NEWS_FOOTBALL_ONLY=1. The SAME 600-row worker budget previously allowed newer other-sport rows to starve older wrong football cards. Generic mode keeps date order. Tested with 601 newer basketball articles plus one older wrong football article; no other-sport records are modified by the test repair.

## Evidence

- First gate: Actions 37180168092, 2,176 tests passed.
- Full gate: Actions 37180378928, 2,196 tests passed; artifact 11295096825 includes complete tested source and bot diff.
- Follow-up gate: Actions 37180937246, 2,198 tests passed; artifact 11294403256 contains exact tested SHA and photo recheck.
- Live maintenance at 05:45:23 UTC: football league menus tagged=3, scanned=600.
- Initial public acceptance Actions 37180618045 correctly FAILED rather than claiming completion: known surfing/futsal cards disappeared, but older Battlefield article 22523 remained outside the mixed-sport repair window. This failure motivated the selection follow-up, not weaker acceptance checks. Artifact 11294379696 preserves the actual 05:46 UTC public response.
- At 05:46 UTC that response had 479 cards, zero missing image_url fields, and 95 with no league field. Rolling 72-hour expiry means differences in total count are NOT automatically new publications or accidental deletions.
- Whole-feed photo audit Actions 37180732721: 481 cards, 469 distinct image URLs; 478 article-photo checks passed and 3 were inconclusive (request_failed). This checks image bytes/dimensions, not the factual relevance of every photograph.
- Three-photo recheck in Actions 37180937246: 22782 and 22739 ReadTimeout, 22730 HTTP 429, all thumbs.smartframe.io. Do not treat provider throttling/timeouts as proof of a missing photograph or bypass them by changing signatures/URLs.

## Still open — not full football completion

- Filling all leagues/clubs remains incomplete. Earlier actual worker audit found 96 of 862 catalogued clubs with seven-day coverage; a catalogued provider is not proof of fresh published coverage.
- New BeNe desk latest observed October 2, Spartak September 27: do not advertise these as new October 4 stories or loosen freshness to inflate counts.
- Existing public cards 22513 (Asier Aguirre, Porto Santo Iberian Open, 65 strokes) and 22505 (Portuguese Olympic research grants) still need exact-source scope review; neither is resolved by the four known-incident acceptance list.
- Some national/team stories and club cards remain without correct sections. Review actual public ID 22967 (Racing manager Jose Alberto) against its source: current national-teams menu appears questionable. Do not force a club league from an unverified roster.
- Three Smartframe photo requests remain inconclusive as above; retain bounded provider-respecting retries or recover another genuinely same-article photo, never an unrelated fallback.
- FK Napredak official feed has a fresh October 3 youth report (tri-pobede-danas-3), but generic extraction returns no body/photo. Evidence artifact 11294372932 shows elementor-widget-theme-post-content and exact featured-image widget. Needs URL-bound extraction and youth scope tests before adding; do not classify it as senior Superliga merely because it is a club feed.
- Public API intentionally omits source_url/source from its response. That is NOT evidence that database source provenance is missing. Source URL is stored on ingestion; no new public attribution design was added.
- Do not declare all news error-free, all clubs filled, all photos verified, or the follow-up deployment verified before reading final production acceptance.
