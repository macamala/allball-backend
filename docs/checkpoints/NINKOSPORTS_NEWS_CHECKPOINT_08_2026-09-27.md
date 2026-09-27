# NinkoSports News checkpoint #08 — 27 September 2026

This checkpoint supersedes News checkpoints #05-#07 for production News recovery.

## User intent — hard requirements

NinkoSports News is fully independent from Live Scores.

News means real sports journalism discovered from public/official news sources. It must NOT create articles from finished scores, fixtures, standings or other Live Scores data.

Articles are not copied rewrites. Source material supplies verified facts only. NinkoSports writes a new article with its own structure and voice.

Editorial voice:
- human, elegant, memorable;
- restrained sports poetry, passion and warmth;
- especially football: love of the game, weight of the shirt, joy/regret, romance of football;
- metaphors may decorate verified facts but must never invent match events, crowd/weather, tactics, motive, pressure or historical importance;
- factual headline, literary body;
- no source/provider branding in public copy.

## Production News service

Railway:
- project: zesty-stillness / 17f6ebff-0f6b-42dd-be86-35ca9ca40301
- production environment: cb27d851-9198-47c8-a733-8356e8b6cf63
- service: hopeful-blessing / be857be7-a029-4663-81c7-bcde75efc482
- source branch: ops/news-free-probe-20260926
- start command: python deploy/news/preflight.py --run
- restart policy: ON_FAILURE
- Railway Agent was NOT used for this production work.

Current intended production head after this checkpoint work:
- 822889219a642a792f3d1032a306cd61ee1255e4
- message: Log accepted NinkoSports News articles for production review
- deployment at checkpoint creation: building; verify SUCCESS before treating it as final deployed head.

Previous proven production head:
- a06570a2249f977c2509320893417fe3f3745bea
- deployment cd671363-3922-4ef3-a977-ea34c85266af — SUCCESS
- live cycle on that head: eligible=75, ai_articles=1, attempts=3.

Scheduler:
- independent News scheduler only
- NEWS_FETCH_INTERVAL_MINUTES=30
- no Result News/data job
- Postgres request accounting/ownership
- no Railway volume needed.

## Live Scores-derived News removed

The mistaken Result News lane was fully retired.

Production cleanup proof:
- log: [data_news] retired legacy result-news articles=127
- 127 legacy Live Scores-derived articles were hidden from public News.

Then code was removed:
- bot/data_news.py deleted
- data job removed from bot/scheduler.py
- News preflight no longer requires data_news.py
- News runtime no longer has a data-only lane
- new production image source manifest no longer contains bot/data_news.py
- Railway legacy NEWS_DATA_NEWS_ENABLED variable may remain set to 0, but current code does not read it.

Do not reintroduce News generated from scores/results.

## Free AI architecture

Provider candidate in production:
- xKiro free-only
- qwen/qwen3.5-397b-a17b:free
- live /v1/models must confirm access_tier=free
- pay_as_you_go=true refused
- authenticated /v1/usage must confirm free-token allowance
- no paid fallback
- 429/timeouts fail closed.

Accounting:
- NEWS_ACCOUNTING_BACKEND=postgres
- atomic news_ai_requests daily ledger
- Postgres advisory lock for one News writer
- request reservation occurs before outbound AI HTTP.

Observed xKiro production proof:
- /v1/models 200
- /v1/usage 200
- /v1/chat/completions 200
- successful AI-written public articles have been stored.

Budget/rhythm:
- small bounded request budget per cycle
- source lane preserves the final available request for cached translation
- current cycles have shown attempts=3 or 4 rather than unbounded rewriting.

## NinkoSports writer voice

bot/rewrite_ai.py production branch now instructs the model:
- never imitate, translate or structurally rewrite publisher copy;
- rebuild story from verified facts in a new order;
- human, elegant, memorable NinkoSports prose;
- restrained poetry/passional sports language;
- sport-specific voice.

Football voice explicitly encourages:
- love of football;
- weight of a shirt;
- thin line between joy and regret;
- old romance of the game;
- one memorable lyrical line;
while explicitly banning invented crowd noise, weather, tension, rivalry, pressure, tactics or historical importance.

Fact rules:
- every numeric token must already occur in source facts;
- no inferred/calculated year, age, score, rank or date;
- no invented facts, quotes, links, source footers;
- exact facts remain authoritative.

## Fact validation

Layer 1 deterministic:
- links/footer rejection
- direct quote rejection
- unsupported number rejection
- copied-source / excessive overlap rejection
- minimum article/paragraph structure.

Brittle deterministic proper-name regex rejection was removed from publication admission because it produced false holds on literary/title-case phrases.

Layer 2 free-model semantic validator:
- sees source facts and draft;
- approves faithful paraphrase/restructuring;
- understands that clearly non-factual sports metaphors are style, not event evidence;
- rejects changed/invented proper names;
- rejects invented event-specific cause, motive, importance, chronology, atmosphere, crowd reaction, tactics, injuries, statistics, locations, standings, predictions or consequences.

## Translation lane

Frontend translation reader is already deployed.

Backend endpoint exists on main:
GET /articles/{slug}/translation/{language}

Languages:
- sr
- es
- de
- fr
- it
- pt

One free AI request can produce six cached translations.

Translation voice:
- preserves NinkoSports rhythm, warmth and restrained poetry;
- Serbian must be natural Serbian Latin;
- Serbian should sound like a passionate Balkan sports columnist rather than literal machine translation;
- no added facts, links or quotes;
- numeric tokens preserved.

Failure handling:
- failed article translations receive a 6-hour cooldown;
- same bad article no longer consumes every future translation slot;
- translated proper-name validation blocks invented name tokens while avoiding exact full-phrase false positives.

Production proof before latest style work:
- one translation request successfully stored translated_rows=6.

## Source coverage

41 active News registry rows.
40 concrete sports have dedicated/configured source discovery.
The 41st is generic esports parent; children are the actual source-bearing categories:
- EA Sports FC
- Counter-Strike
- League of Legends
- Dota 2
- VALORANT
- Call of Duty
- Overwatch
- Rocket League.

Public-read aggregation for sport=esports is patched on the News branch to include child esports. Backend main still needs this specific safe read-path merge when it will not conflict with concurrent Live Scores work.

Current source improvements:
- BBC Scottish Premiership canonical RSS -> 200 in production
- EA SPORTS FC official index at ea.com -> 200; individual EA FC articles hydrate 200
- Rocket League official site remains robots-blocked and is not bypassed
- filtered BLAST.tv /rl/news partner fallback works; RLCS individual articles return 200
- VALORANT official News works
- LoL Esports official News works
- IHF/UEFA/Overwatch/Call of Duty index paths remain fail-closed according to runtime access
- substantial RSS fallback allows real feed content when linked article page is JS-only/202/zero prose
- fallback minimum is 25 source words and still passes all writer/fact gates.

Live discovery has reached ~74-75 eligible fresh candidates in a cycle.

## Editorial priority

Latest production branch logic prioritizes real sports stories before low-value administrative content.

Higher signal includes:
- finals/titles/champions
- wins/defeats
- transfers/signings/departures
- injuries/suspensions
- records/contracts/managers/coaches.

Lower signal includes:
- calendars/schedules
- ticket/event guides
- how-to-watch/fan guides
- pack probabilities
- patch notes/soundtracks/offers
- policy/admin updates.

Sport diversity remains via rotating tie-breaks.

## Frontend

Frontend master contains the translation reader commit:
66aa42c1eecd775072a39189b4285f47c341a878

Behavior:
- English does not call translation endpoint
- selected language loads cached translation
- translated title/summary/body replace English when ready
- missing translation falls back to English.

Frontend production deployment for that commit previously succeeded.

## Production facts observed today

- 127 legacy score-derived articles retired from public News.
- xKiro free entitlement works live.
- early source cycles produced at least 3 original AI articles before Result News removal.
- final News-only literary pipeline on a06570a produced ai_articles=1 in a live cycle.
- discovery has produced ~75 eligible fresh source candidates.
- successful translation batch has written 6 language rows.
- News worker is independent from Live Scores.

## Resume instructions

1. Verify deployment for 822889219a642a792f3d1032a306cd61ee1255e4 reached SUCCESS.
2. Inspect its first production cycle:
   - eligible count
   - deterministic rejects
   - semantic validator rejects
   - published log entries
   - translated rows
   - News cycle final counters.
3. For the first published entry, review the public article itself for NinkoSports voice.
4. Do not re-add Result News or Live Scores-derived articles.
5. Do not use Railway Agent.
6. Keep improving real-source coverage/quality in broad passes, not one provider at a time.
7. Merge only the safe esports parent read aggregation into backend main when it will not collide with concurrent Live Scores work.
