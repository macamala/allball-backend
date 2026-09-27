# NinkoSports News checkpoint #09 — 27 September 2026

This checkpoint supersedes News checkpoints #05-#08 for recovery/resume.

## User direction / non-negotiable product rules

- NinkoSports News is **independent from Live Scores**.
- Do NOT create News from finished scores/results/match rows.
- Do NOT re-enable Result News/data-news.
- News must be real sports news discovered from feeds/official News pages, then written as an original NinkoSports story.
- NinkoSports copy must not imitate/rewrite a publisher article paragraph-by-paragraph.
- The factual source is evidence only; the final article must have its own NinkoSports structure, headline and voice.
- For football especially, use restrained poetry, passion, rhythm and love of the game without inventing crowd emotion, motives, tactics or events.
- Avoid corporate/AI sports prose and cliches.
- Keep fact gates strict: names, numbers, unsupported claims, direct quotes, taxonomy conflicts.
- Free-first only; no automatic paid AI fallback.
- Do NOT use Railway Agent unless there is genuinely no direct GitHub/Railway command that can complete a necessary task.
- Avoid wasting Railway runtime/agent credits; batch changes before deploys where practical.

## Exact durable backend state

Repository: `macamala/allball-backend`
Production News source branch: `ops/news-free-probe-20260926`

At checkpoint creation, code head and active Railway production deployment are identical:

- GitHub branch head: `822a11b28b4bb66c6b4b63b64681f23cd00e3e17`
- commit: **Retry cached News translations under extended-timeout v11**
- Railway deployment: `1dc66093-4933-4a6e-9c35-1659b93e9aa1`
- Railway status: **SUCCESS**
- Railway service: `hopeful-blessing`
- project: `17f6ebff-0f6b-42dd-be86-35ca9ca40301`
- production environment: `cb27d851-9198-47c8-a733-8356e8b6cf63`

Observed runtime:
- scheduler interval: **30 minutes**
- deploy startup cycle: **20 second delay** before the first News job
- cycle AI request cap observed in production: **4**
- English writer + fact validator normally consume 2 requests for an accepted source story
- remaining request is intentionally preserved for cached translations
- source cooldown is durable in existing Postgres, not process memory only

At the moment this checkpoint is written, deployment `822a11b...` is healthy and its delayed startup cycle has begun feed discovery. **Translation v11 has not yet been proven with `translated_rows=6` in this newest cycle. Resume by reading this deployment's logs, not by redeploying immediately.**

## Frontend state

Repository: `macamala/allball-frontend`
Production `master`: `66aa42c1eecd775072a39189b4285f47c341a878`
Railway frontend deployment: `6509d108-9ff7-499d-875a-d3d82d8b14bc` — **SUCCESS**

Article reader behavior:
- English does not call translation endpoint.
- Selecting sr/es/de/fr/it/pt calls the cached translation endpoint.
- Ready translation overlays article title/summary/body.
- Missing translation falls back to English without breaking the page.
- Full frontend suite previously passed 332/332 and production build passed.

## Result-News / Live Scores separation

The earlier Live Scores -> Result News experiment was explicitly rejected by the user.

Current state:
- `NEWS_DATA_NEWS_ENABLED=0` was set in production before this checkpoint.
- `bot/data_news.py` was deleted from the News branch.
- News scheduler contains no `data_job` and no `_run_data_lane`.
- News preflight no longer requires `bot/data_news.py`.
- News runtime no longer has a data-only lane.
- 127 legacy Live Scores-derived News articles were retired/hidden from public News during cleanup.
- Do NOT recreate this architecture.

## NinkoSports editorial voice now in production

`bot/rewrite_ai.py` contains:
- `NINKOSPORTS VOICE`
- special `FOOTBALL VOICE`
- basketball/combat/racing/racket/general sport voice guidance
- explicit ban on press-release/corporate filler
- explicit ban on stock AI sports cliches
- clear/factual headline requirement
- human column-style rhythm in the body
- restrained literary line for football player/club/match/transfer/career stories
- factual constraints remain strict

Writer:
- xKiro `:free` writer model
- writer temperature was raised above validator temperature to allow more human voice
- validator remains deterministic/strict
- every numeric token in English writer output must already exist in source facts
- proper names cannot be invented
- source headline near-copies are rejected by headline originality gate

Production editorial samples observed before this checkpoint:
- LeBron article was too corporate -> prompt was strengthened.
- motorsport article improved but still had AI cliches -> cliche filter added.
- later rugby/cricket/boxing/MMA/swimming/greyhound/EA FC articles demonstrated more natural, human prose and clean taxonomy when they passed all gates.
- body-preview logging was temporary and was later removed after editorial review.

## Free AI / safety architecture

`bot/free_ai_router.py`:
- xKiro free-only route
- model ID must end `:free`
- live model catalog must report free access tier
- explicit pay-as-you-go model route is refused
- free-token usage endpoint must confirm allowance
- no automatic paid fallback
- OpenAI path remains legacy/explicit only, not production default
- writer and validator share the durable per-cycle budget
- six-language translation JSON request uses a longer timeout than English writer/validator

Latest translation timeout behavior:
- prior translation attempts sometimes hit `ReadTimeout` at 95 seconds.
- current v11 code extends **only the six-language JSON translation call** to up to 180 seconds.
- English writer and fact validator keep the normal shorter timeout.
- v11 bumps provider version so recent failed translations can retry immediately.

## Durable AI source cooldown

`bot/news_source_holds.py` is in the production artifact.

Behavior:
- rejected source URL is stored as a SHA-256 fingerprint in existing Postgres
- cooldown survives Railway redeploys/restarts
- typical reject cooldown: 6 hours
- no new Railway service or volume
- old Curry/Brunson/Packers examples were later skipped from durable cooldown without spending new AI requests
- source hold stores expiry/reason only, not source article text

This is critical for free-budget efficiency. Do not regress to in-memory-only reject cooldown.

## Scheduler / deployment-lock fix

Railway blue/green deploys can briefly run old and new containers together.

Fixed behavior:
- no immediate startup `job()`
- new container schedules first News cycle ~20 seconds after startup
- existing 30-minute recurring interval remains
- Postgres advisory owner lock still prevents duplicate writers
- this eliminated the need for manual redeploys just to catch an initial cycle after a Railway swap

## Source coverage / source cleanup

Broad source families include BBC, ESPN, football league RSS, international mixed feeds, official sport feeds, official first-party News pages and selected official competition partner sources.

Important production changes:
- BBC Scottish Premiership canonical feed URL fixed.
- EA press RSS that returned 403 was removed; official EA SPORTS FC News index is active.
- TalkBasket robots-blocked feed was disabled.
- FIVB RSS returning 202 was removed.
- official **Volleyball World News** index was added and returned 200 for current News pages/articles.
- Rocket League own host remains robots-blocked and is NOT bypassed.
- filtered BLAST.tv Rocket League/RLCS partner fallback works and returns 200.
- official IHF, UEFA futsal, VALORANT Esports, LoL Esports, Call of Duty, Overwatch candidate indexes remain bounded and robots-aware.
- RSS full-content fallback is used when linked pages are JS/202/0-word but the feed contains enough factual source text.

The old FIVB/EA press/TalkBasket dead routes should not be reintroduced.

## News priority / fairness

Queue is fair across sport buckets and uses freshness + editorial-value scoring.

Higher priority includes:
- championships/finals/titles/trophies
- wins/upsets/knockouts
- transfers/signings/departures
- injuries/withdrawals/suspensions
- contracts/appointments
- qualification/returns/comebacks
- manager/coach/captain/debut/selection/squad/call-up context

Lower priority includes:
- tickets
- schedules/calendars
- event/fan guides
- how-to-watch content
- podcasts/audio/quizzes
- patch notes
- pack probabilities/offers
- generic rankings/power-rank/admin/policy content

This scoring only decides what spends scarce free AI requests first; it does not relax factual admission.

## Taxonomy state

A multilingual alias layer is active for real production titles, including football/basketball/boxing/handball/rugby-league/futsal/water-polo/field-hockey/AFL/netball/lacrosse/table-tennis/badminton/darts/racing/athletics/swimming/winter sports/MMA/ice hockey/volleyball/esports children.

Current branch aliases include, among others:
- Portuguese football: Racing Power, Ana Nogueira, Gil Vicente, Lucão/Lucao, Buatu, Elimbi
- Balkan handball: rukometašice, Trifej Makedonije, Ohrid
- boxing: Radivoje Kalajdžić/Kalajdzic and the identified London headline
- Rugby League: Wigan Warriors, Wakefield Trinity, Super League Grand Final
- EIHL ice hockey: Cardiff Devils, Sheffield Steelers, Nottingham Panthers
- multilingual Czech/Serbian/Portuguese/Dutch football and hockey cues from earlier production samples

Known intentional gap:
- Muay Thai article remains unclassified rather than being falsely stamped as boxing/MMA because the registry currently has no dedicated Muay Thai sport.

Recent observed taxonomy improvement:
- production unknown-sport snapshots were reduced drastically from the earlier 16-item batch.
- a later diagnostic snapshot contained 5 items:
  1. Ana Nogueira / Racing Power -> football alias is now present
  2. Lucão/Buatu/Elimbi / Gil Vicente -> football aliases are now present
  3. Radivoje Kalajdžić London story -> boxing alias is now present
  4. Rukometašice / Trifej Makedonije -> handball aliases are now present
  5. Muay Thai -> intentionally unresolved
- because current production code head contains those aliases, next production discovery should be checked before adding any new taxonomy aliases.

The bounded `unknown_sport_samples` diagnostic is currently present in `bot/fetch_sources.py` on production v11. After confirming only intentional/unresolved items remain, remove this temporary diagnostic log.

## Translation architecture

Current provider marker: **`xkiro-free-v11`**

One translation request targets:
- sr
- es
- de
- fr
- it
- pt

Rules:
- Serbian Latin only
- preserve NinkoSports literary voice
- preserve locked names / official labels
- preserve numeric values
- locale punctuation differences are canonicalized
- locked numeric values must remain numerals
- no extra numerals
- multiple safe JSON response shapes are canonicalized before semantic validation
- failed provider version gets a cooldown; bumping provider version permits immediate retry after a parser/prompt/timeout fix

Previous translation issues resolved in sequence:
- locale score/thousands punctuation
- diacritic normalization for names
- proper names such as competition/stadium labels
- nested/flat/wrapped JSON shapes
- missing locked numeral `13`
- extra numeral `1`
- 95s translation timeout

Current unresolved verification:
- v11 now uses extended translation-only timeout.
- **Need to confirm production `translated_rows=6` on deployment `1dc66093...` or later.**
- do not bump to v12 unless v11 gives a concrete new failure reason.

## Public News / frontend

Backend translation endpoint already exists in backend main:
`GET /articles/{slug}/translation/{language}`

Frontend master `66aa42...` consumes it.

An earlier `esports` parent aggregation fix exists in News branch work, but before changing backend main verify current main/public_read state to avoid colliding with concurrent Live Scores/backend work.

Do not change backend main just for News if another chat is actively deploying Live Scores; keep News worker work isolated unless a public API merge is actually needed.

## Production behavior already proven

- News worker builds/runs in Railway without Railway Agent.
- Scheduler starts and performs broad RSS/official-index discovery.
- xKiro free model catalog/usage checks return 200.
- source writer and fact validator return 200.
- unsupported drafts are rejected.
- deterministic gates can reject before the second validator request, saving free budget.
- accepted articles are stored with correct sports in many categories.
- recent taxonomy-held articles can be repaired without re-running AI.
- durable rejected-source cooldown survives redeploys.
- queue preserves a translation request instead of starting another impossible writer pair near cycle end.
- startup delay prevents blue/green owner-lock loss.
- source cleanup removed repeated dead-feed errors.
- article translation reader is live on frontend production.

## Railway Agent policy

User explicitly said not to use Railway Agent unless truly necessary.

So:
- prefer GitHub direct tool calls
- prefer Railway direct variable/service/deploy/log commands
- direct redeploy is allowed when needed
- do not call Railway Agent merely to change source/variables/start commands if direct tools can do it

## Resume from here

Do not repeat earlier research.

1. Read logs for current deployment `1dc66093-4933-4a6e-9c35-1659b93e9aa1`.
2. Confirm v11 startup cycle completes.
3. Check for `translated_rows=6`.
4. If v11 fails, use only the concrete logged failure reason; do not redesign translations blindly.
5. Check the new `unknown_sport_samples` snapshot.
6. If only Muay Thai remains, remove temporary unknown-sport diagnostic logging and leave Muay Thai intentionally unresolved.
7. If another safe known sport remains, batch-fix aliases, not one-at-a-time deploys.
8. Continue improving source freshness/priority and article quality only from production evidence.
9. Keep News completely independent from Live Scores.
10. Keep NinkoSports article voice original, passionate and literary but factual.
11. Never re-enable Live Scores-derived Result News.
12. Do not use Railway Agent unless direct tools genuinely cannot complete a required operation.
