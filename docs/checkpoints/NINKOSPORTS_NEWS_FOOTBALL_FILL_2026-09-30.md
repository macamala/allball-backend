# NinkoSports football News continuation — 2026-09-30

Scope: football NEWS only. User says do not change Live Scores, results collection, shared API deployment or other features; do not use Railway AI agent. No agent or sub-agent was used. Routeway key already stored on News; no keys in this record.

## Release

Production News branch: `ops/news-free-probe-20260926` in `macamala/allball-backend`.
Final code commit: `dd1144ec6042c4fee466472e4927d5948c2a6c56`; tested tree: `5c9b75d97d3d061eee678c24594590db00aecaf3`.
Local backend: `/workspace/scratch/de740b98f4bb/news-sort`; local HEAD `620c59fd524b7db40544aafb58fb68ec73db8285` has the same tree.
News deployment: `96fb0c26-754d-42a3-a299-83ca92841ec8`, SUCCESS. Exact News service `be857be7-a029-4663-81c7-bcde75efc482` in project `17f6ebff-0f6b-42dd-be86-35ca9ca40301`, environment `cb27d851-9198-47c8-a733-8356e8b6cf63`.

Shared API remains deployment `a6018808-ec70-44a9-8ddc-5a65b30f9c57`; results worker remains `25287c7e-08a8-46f8-aa3b-0d85ba6eaf53`, both commit `ff091f98b6c879c85978d78df7bdcd0853b08dfb`. Verified unchanged at 06:39 UTC. Frontend untouched this continuation; remains `8ee13e024b917184d479392ae88ee17d8f91069d` with 86 News menus.

## Changes

- Reader-visible league inventory controls News candidate scheduling. Keep explicit Zvezda priority; balance underfilled major leagues and reserve every fourth non-Zvezda slot for other leagues. Scheduling hints never authorize publication or factual competition claims.
- Already hydrated official article bodies now reach candidate classification instead of classifying only an often ambiguous headline.
- Five official discovery entries added: German and English Bundesliga, Bundesliga 2, MLS, Eredivisie. Bounded robots-aware existing transport, current publication timestamps, article photos and full prose still required. No league stamped purely from publisher identity.
- Scoped actual article body/photo extraction for Bundesliga, MLS, Eredivisie excludes sibling recommended articles. Missing scoped body fails closed.
- Added verified 2026/27 French and Dutch club membership for News menu routing. Primary evidence: https://ligue1.com/fr/articles/l1_article_5284- and https://eredivisie.nl/nieuws/ . Women/youth and explicit event routing stay separate.
- Serbian `4:1` in explicit match-result grammar supports exact English `4-1`; clocks/ratios/reversed scores do not. `Прве лиге Србије` supports Serbian First League, not Superliga.
- Expired only the exact Graficar URL's old numeric/competition holds before 06:28 UTC. Subsequent quality/semantic failures retain normal cooldowns.
- Audited existing card 22217 into Conference League. Exact official source introduction identifies Copenhagen and the Conference League; copied English lead omitted the competition. Exact-source mapping plus ID-and-headline-bounded legacy correction changes only menu metadata.
- Routeway explicitly requests `reasoning_effort: none` on its already verified zero-cost model. Independent validation, request accounting, model/cost checks unchanged. Provider still returned 502 in production; this is not a fix for upstream availability.
- Fantasy Manager products, live tour diaries, international-duty trackers, playoff analysis, power rankings and a confirmed retrospective Greek-player list no longer consume writer slots in new sources. Fragment exclusions are tested through discovery, not just config presence.
- German `Basketballer` headline overrides generic Bayern/Bundesliga evidence even on mixed feeds. Full extracted-source product checks happen before image/writer spending.

## Verification and incidents

Targeted offline tests: initial 315 passed; expanded parser/image suite 367 passed; final changed-scope suite 239 passed. Other focused passes 111 and 101. All deployed trees exactly matched tested local trees. No failing version was deployed.

Runtime before changes: 125 visible football cards, 20 populated specific menus, 7 general cards. 24-hour football inventory 77, but empty leagues had no scheduling debt. RSS 351+ candidates, eligibility 39 before source extension.
06:40 run: verified source discovery/hydration MLS 5, Eredivisie 2, German Bundesliga 5, English Bundesliga 4, Bundesliga 2 one rolling diary. Diary now excluded by final fragment fix; genuine Bundesliga 2 candidates were stale. Do not relabel stale dates to fill the menu.
Graficar retry reached writer but failed direct-quote then summary-only quality; keep held, do not force public.
Two interim new articles were subsequently held after source-type audit: 22296 playoff analysis rewritten as LAFC coach story, 22297 retrospective Greek-player rankings. Do not count these as successful coverage.
Final startup 06:47 tagged one card (22217), held 22296 and 22297. Browser verified 22217 visible at https://ninkosports.com/football/conference-league ; 86-entry directory also verified.

## Remaining boundaries

New source freshness is rolling 24h UTC; public browsing is 72h. Resolver version must remain 4.4.1 to match the unchanged shared API. Do not lower quality/image/semantic/dedup gates or manufacture stories to fill all menus.
News scheduler runs every 10 minutes; image-health maintenance at +5 minutes. Free upstream 429s/502s/timeouts and poor writer drafts remain real throughput limits. Never claim all 86 menus are populated.
FootMercato works intermittently but production robots/page requests returned 429. No bypass. EFL current article had no readable prose, so not added. Official Ligue1 current listings were client-rendered/empty to this parser, so not added. J.League transport/full prose was verified, but a current Levain Cup story risks a J1 mislabel; source not enabled this turn.
Scratch probes in `/workspace/scratch/de740b98f4bb/football-fill-probes`. Public before snapshot `football-fill-before.json`. No repository duplication in file storage.

## Latest production outcome

At 06:56:27 UTC deployment d3639802-1074-4e72-9d8c-1473c0983a9e completed its 06:50 scheduled cycle successfully: ai_articles=1, translated_rows=0, indexed=0, attempts=16/16, stop=None. Final eligibility was 61 football candidates (previously 39).
- Published 22298, “Germany Coach Jürgen Klopp Calls 44 Players for Upcoming Matches”, original English, independently validated, source timestamp 2026-09-29 10:51 UTC preserved. Public API correctly returns league football-national-teams, quality_ok=true, sport_match_ok=true and editorial photo; browser confirms it is listed under National Teams.
- Brown draft rejected unsupported_acronym:U17. USMNT draft rejected invented veteran characterization and changed Peru starter claim. Asencio candidate 22299 failed public weak_body admission. These are held, not successful publications.
- Routeway again returned timeout/502. Groq, Mistral and ZAI returned quota 429s. Cloudflare/Gemini/ZAI fallback produced the accepted article while a separate provider validated it. No quotas, budgets, or quality gates were relaxed.
- Final public API snapshot: 126 football cards, 21 populated specific league/competition menus plus 7 general football cards, all 126 with image URLs. Interim cards 22296 and 22297 absent. Full 86-menu coverage remains incomplete.
- Current counts: EPL16, SerieA15, LaLiga4, NationsLeague27, NationalTeams23, International7, Youth4, UEFAU212, Women1, WSL6, WomensChampions2, WomensWorldCup1, Conference1, Ligue2=1, LaLiga2=2, SerbiaPrva1, SerbiaSuperliga1, BrazilSerieA1, AustraliaALeagueWomen2, BelgiumCup1, ScottishPremiership1; general7.
- Bundesliga 2 current official discovery: 0 accepted fresh, 7 stale. Other current new sources found German Bundesliga4, English Bundesliga2, MLS4, Eredivisie1. New source availability does not guarantee an accepted original article in every category.
- Prior verified production status SUCCESS for News deployment d3639802-1074-4e72-9d8c-1473c0983a9e at code f810b50df9608b7db2f2fd880231f5f7a366c4bc. Working tree clean. Final snapshot football-fill-final.json; 22298 response football-fill-probes/22298.json.
- This checkpoint belongs only to checkpoint/news-football-fill-20260930, to avoid triggering another production deployment.

## Final narrow false-rejection fix and handoff

The completed cycle exposed a real false positive: official Bundesliga source explicitly says “U17s” for Brown's former Nuremberg team, while the draft used “U17”. Exact U10–U23 English plural spellings now normalize for acronym comparison; the age number and every unrelated acronym stay strict. No sport/league fact or validation outcome is inferred from this normalization. The exact Brown URL's unsupported_acronym:U17 hold before 06:53 UTC is allowed one normal retry; later factual failures retain cooldown. 100 focused regression tests passed, including different-age/acronym rejection and exact old-hold scope. Test tree matches GitHub tree exactly.

Final deployment 96fb0c26-754d-42a3-a299-83ca92841ec8 is SUCCESS at dd1144ec6042c4fee466472e4927d5948c2a6c56; scheduler started 07:01:55 UTC. This narrow final change awaits the next normal 07:10 cycle for Brown's retry; do not claim Brown is published yet. All prior source discovery/publication verification is from the completed 06:50 cycle. New article 22298 was opened in the public browser: full body displayed and editorial photo loaded at 1120×630. Verified URL: https://ninkosports.com/article/germany-coach-jrgen-klopp-calls-44-players-for-upcoming-matches .

Next continuation should inspect the normal cycle and exact empty-menu source gaps. There is no task authorisation to touch Live Scores or increase paid spending. Do not describe all 86 menus as filled: last snapshot has 21 populated league/competition menus and 7 general cards, 126 total football cards.
