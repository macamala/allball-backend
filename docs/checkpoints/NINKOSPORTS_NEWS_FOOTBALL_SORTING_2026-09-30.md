# NinkoSports News — football sorting checkpoint, 2026-09-30

## User scope
Continue football News, populate existing league menus and put each story in its appropriate section. Work only on News. Do not touch Live Scores, the results worker, the shared API deployment, or unrelated features. Do not use Railway's AI agent. Use ordinary connector operations only when necessary. No Railway agent was used.

## Deployed and verified
- Backend repository: macamala/allball-backend
- News branch: ops/news-free-probe-20260926
- Final News commit: 90f3fc4c297dcf64f370ab7550377221f8f28518
- Exact tested/deployed backend tree: b7661ec4cfd938708b555681cd8ee57953f2d10d
- News deployment: ec69e28e-fd33-4440-80a2-f202ca5937e8 (SUCCESS)
- Frontend repository: macamala/allball-frontend
- Frontend branch: master
- Frontend commit: 8ee13e024b917184d479392ae88ee17d8f91069d
- Exact tested/deployed frontend tree: f0a4fad9997830121839f34252392afbe2f0a37b
- Frontend deployment: 6f3e88ee-6ed1-4f1d-8280-556003a09f98 (SUCCESS)
- Public directory verified in the browser: https://ninkosports.com/football/other-leagues
- Both local working trees clean and equal to remote deployed trees after fetch.

## Result
At the final public API check around 06:06 UTC:
- 124 visible football stories in the API's current window.
- 90 existing visible articles gained/corrected their section compared with the initial 121-story snapshot.
- 4 additional stories arrived through the existing ingestion pipeline during this work.
- 7 stories remain in general Football because the evidence does not identify a supported exact competition.
- The startup maintenance tagged 98 of 131 eligible rows across its wider seven-day window.
- The final image-health pass at 06:05:22 tagged exactly 2 new edge cases, and completed at 06:05:24 with no errors.
- Headlines, summaries, original publication dates and hero-image URLs of retained existing stories were unchanged by sorting.
- Cartoon product article 22239 was held by the existing non-article policy maintenance; its database row was retained.
- Two new cases were verified after final deployment: Raphinha's Barcelona recovery story 22294 => spain-la-liga; Manchester City / A-Leagues season-launch story 22291 => england-premier-league, not WSL.

Final visible counts:
| Menu | Stories |
|---|---:|
| UEFA Nations League | 27 |
| National Teams | 21 |
| Premier League | 16 |
| Serie A | 15 |
| International / governance | 7 |
| Women's Super League | 6 |
| La Liga | 4 |
| Youth Football | 4 |
| La Liga 2 | 2 |
| SuperLiga Srbije | 2 |
| UEFA Women's Champions League | 2 |
| UEFA Under-21 EURO | 2 |
| A-League Women | 2 |
| Ligue 2 | 1 |
| Prva liga Srbije | 1 |
| Brasileirão Série A | 1 |
| Belgian Cup | 1 |
| Scottish Premiership | 1 |
| FIFA Women's World Cup | 1 |
| Women's Football | 1 |
| General Football (no exact league) | 7 |

## Implementation
- bot/news_football_sections.py assigns editorial menu metadata only AFTER football/public/quality admission.
- Explicit headline/lead competition evidence wins. Qualified women's/youth competitions have their own sections.
- Club news uses a dated membership catalogue, with official source URLs and expiry. This association never inserts a league claim into article text or weakens the source-grounding validator.
- Headlines about an international match cannot be pulled into a club league by incidental club affiliations in the body.
- Former/rejected clubs, promotion ambitions, historical World Cup rosters/champions, and incidental body mentions do not determine a league.
- New production checks caught and fixed incidental women's competition mentions in a mixed Australian season-launch report, plus national-team background in a Barcelona recovery headline.
- bot/news_football_clubs.json records official 2026/27 membership evidence (Brazil expires December 2026; European entries June 2027). It is partial, conservative and must be refreshed for later seasons.
- bot/news_league_index.py revisits only recent already-public AI football rows, max 600 and seven days; no held-story resurrection or historical mass rewrite.
- public_index.persist_public_article assigns sections after admission gates.
- The existing regular ingestion repair pass now also invokes menu maintenance, in addition to startup/image health and zero-budget maintenance.
- bot/news_policy.py rejects cartoon products, while allowing genuine reporting about a cartoon.
- Backend and frontend football catalogues are byte-identical and now contain 86 menu entries, including WSL, NWSL, Belgian Cup, women's UEFA/FIFA competitions, U21 EURO, Youth Football, Women's Football and National Teams.
- No changes to the Live Scores UI or collector code.
- Resolver version intentionally remains 4.4.1 so the independently deployed shared API continues to serve these stored rows.

## Validation
- Broad backend regression run: 419 passed before the final additional edge-case tests.
- Subsequent focused runs covering the final rules and ingestion integration: 268 passed, 126 passed and 152 passed at their respective steps.
- Frontend LeaguePage tests: 4 passed; production Vite build passed.
- Git diff --check passed; GitHub tree hashes exactly matched tested local trees before each deployment.
- Public API checked exact league filters for women's/mens Champions League, Serie A, SuperLiga, Ligue 2, La Liga 2, National Teams and WSL; no cross-league rows in these results.
- Browser confirmed 86 directory entries and actual article cards under Women's Champions League, La Liga 2 and SuperLiga.
- Final public API assertions confirmed both new edge-case corrections, cartoon absence, and preservation of original visible story fields.

## Explicitly unchanged
Railway project 17f6ebff-0f6b-42dd-be86-35ca9ca40301:
- Shared API service c08822c6-e602-4f32-a2bc-87aedbbe9b05 remains on deployment a6018808-ec70-44a9-8ddc-5a65b30f9c57, commit ff091f98b6c879c85978d78df7bdcd0853b08dfb.
- Results worker 2c89eecf-b094-428a-8f7c-9642605a6baa remains on deployment 25287c7e-08a8-46f8-aa3b-0d85ba6eaf53, same commit.
- Only News service be857be7-a029-4663-81c7-bcde75efc482 received NEWS_DEPLOY_REV updates; the frontend deployed its News catalogue edit through its configured master branch.
- Routeway key and provider configuration were left intact. No credential is stored in this checkpoint.

## Limits and continuation
The 86 menus are navigation coverage, not a promise that each has current articles. Twenty menu sections currently contain stories; others require fresh verified source material. Do not invent stories or mislabel another league to fill an empty page. The existing ten-minute News ingestion continues under its actual request budget and quality/image/source/deduplication gates. Previous observation: some full Routeway writer requests time out; independent fallback/validation remain in place. No provider or budget settings were changed in this turn.

The general International key is an editorial broad bucket. The older shared API intentionally suppresses broad competition labels on article detail, while list filtering uses the stored key. Do not redeploy the shared API to change this without a separate authorized scope.

Older checkpoint: checkpoint/news-league-menus-20260930, docs/checkpoints/NINKOSPORTS_NEWS_LEAGUE_MENUS_2026-09-30.md.
