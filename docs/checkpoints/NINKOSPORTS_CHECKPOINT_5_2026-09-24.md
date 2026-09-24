# NinkoSports checkpoint #5 — 2026-09-24 22:42 AEST

This checkpoint is the recovery point after repeated chat connection interruptions.

## LOCKED / DO NOT REGRESS

### Football fixture stability
Production verification for Sydney-local 2026-09-25 is still exactly:
- public visible: 56
- all raw rows: 60
- hidden duplicate/contaminated rows: 4
- no ORPHAN_DUPLICATE_GUARD restore regression observed after repeated deploys/restarts

Do not reintroduce broad visibility repair logic. Treat 56/60/4 as the current stability invariant until upstream data legitimately changes.

### Frozen registry
- frozen matrix count: 180
- checksum observed in production: e16236bb4666665a6f49856fa6505e9c2defd7ec84b6fb7142fc872c79477440

## FRONTEND / PC + MOBILE

Current frontend recovery head:
- 92a9c9dbfe168cffe246a85b403b0f0fdf74473b — Keep home Live Scores visible across browser timezones
- 9ab3b1ab81210ada502a20cbb3f26cf4f948a40e — Test rolling home score fallback window
- 23f623d7dbbb25941ce18fdd0114c1a8739bb6db — Add rolling score window fallback
- 7c8af9a5d30ce22d30bb427501cf113b06e31ac1 — Close mobile drawer after route navigation
- earlier responsive fix 8d837673 — mobile competition-header 4-column grid + Match Centre active-tab correction
- Dota grouping commits 04fa37203c097c7f87c8cff1225e78b025b3621c + 07d9745ad1cbda2e1538499a37015100c5fa4714

Production frontend deploy was SUCCESS after the home fallback work.

Home page Live Scores hardening:
- first request remains browser-local day window
- if that returns empty or errors, fallback uses rolling UTC window of 12h back / 36h forward
- prevents one PC/browser timezone/date difference from hiding the home Live Scores rail
- no service worker/PWA cache exists
- CORS already allows ninkosports.com, www.ninkosports.com and Railway frontend domain

Mobile:
- drawer now closes on pathname/search route changes
- competition header grid no longer wraps the 4th action/count item incorrectly
- Match Centre inactive/active tab styling no longer leaves Overview visually active

## ASSET / MULTISPORT STATUS — PRODUCTION

### Solved
- GBGB Meetings competition logo: 97/97 current-day events now have competition logo
- HRNSW Meetings: current event has competition logo
- Formula 1 competition logo solved
- Formula 2 competition logo solved
- European Challenge Tour competition logo solved
- WTA participant countries: current-day tennis now 34/34 events have both participant-side country identity
- WTA dynamic competition artwork now fills current/future Singapore, Ankara 125, Tolentino 125 and Seoul rows
- tomorrow 2026-09-25 multisport public window: asset_gaps = {}
- 2026-09-26 WTA Seoul logo gap also disappeared after verified artwork propagation

WTA verified artwork commits:
- a9755c5a32d03f61a49894d0af730eacce57b244
- 8c1efc77d641e825548aecb9231510511cdbb1bd

WTA country repair:
- PRELOCK_WTA_COUNTRY_ASSETS runs successfully
- calendar_rows=25, active tournaments=7, HTTP errors=0, country keys=924
- current run updated 0 because the earlier propagation/breadth repair had already filled the visible gaps
- no remaining current-day WTA country gap in audit

### Dota — improved but not finished
Production current-day Dota audit after Liquipedia pass:
- events: 4
- side slots: 8
- side logos present: 7
- events with both side logos: 3
- remaining team-logo slots: 1
- remaining competition-logo gaps: 4

Liquipedia asset-only pass is PROVEN working in Railway:
PRELOCK_LIQUIPEDIA_DOTA_ASSETS:
- requests=2
- http_errors=0
- pages_ok=2
- catalog=17 team identities
- candidate_rows=11
- rows_updated=8
- participant_logos_filled=15

Pages:
- BetBoom Streamers Battle 15
- PGL Wallachia 9

Relevant commits:
- a4a261c50147f4e2a973bb660e0e42d665423e42 — Liquipedia Dota team artwork backfill
- 2390cff9bb9445b13b2e0513bb9ccc7e7d285bd8 — run pre-lock
- c3f77d620f29e2bdfeef6c7a9cffcb5272c30618 — tests

SofaScore Dota asset fallback:
- production fetch fails 4/4, not usable from Railway
- do not count it as solved

CyberScore Dota fallback:
- code/tests added, but production fetch failed 2/2
- do not count it as solved
- commits: 51bf9264524e3aab945a78ac51fd90ea903a8686, 87c5fe7a23b60a601f1432ceef27122400b6e6c5, 017a5b110d0f85b71db34d6e04155f8a6ec8e853

Current visible Dota gaps after Liquipedia:
1. Team avice vs Team GPK — team logos solved, competition logo still missing
2. Rostik Team vs TEAM YBN — YBN is the one remaining team-logo gap, competition logo missing
3. Team Nemesis vs Xtreme Gaming — team logos solved, competition logo missing
4. LGD Gaming vs Natus Vincere — team logos solved, competition logo missing; display competition is PGL Wallachia 2026 Season 9

Canonical competition key remains "professional", but frontend public grouping separates Dota groups by real tournament display identity where available.

## NEXT STEPS FOR NEW CHAT

Start from this exact order:
1. DO NOT touch football visibility/integrity code unless the 56/60/4 invariant genuinely changes.
2. Finish Dota:
   - extract/verify tournament artwork for BetBoom Streamers Battle 15 and PGL Wallachia 9 from a source Railway can actually access
   - fill only missing competition_logo
   - resolve remaining TEAM YBN logo if Liquipedia page can expose it through another exact-name/roster path
   - never use name-only fuzzy matching and never alter result/status/start_time
3. Re-run MULTISPORT_PUBLIC_WINDOWS and require current day to be asset-gap-free where identity is applicable.
4. After Dota, handle next future gap already visible in day+2 audit:
   - CFL BC Lions vs Saskatchewan Roughriders has 2 missing team-logo slots on 2026-09-26
5. Continue PC/mobile QA:
   - home Live Scores across desktop browsers
   - Live Scores responsive rows/competition headers
   - Match Centre tabs/overflow/lineups/statistics
   - compare desktop and mobile without changing stable data collection
6. Continue remaining multisport detail/coverage gaps after asset identity is clean.

## SAFETY / ARCHITECTURE RULES
- Asset-only fallbacks must never become score/result/fixture authority.
- No generic fake crest/logo should be used to mark a gap complete.
- Real competition logo/participant identity is mandatory where applicable.
- Do not mark a sport/competition complete merely because the fallback glyph renders.
- Source research can be broad, but production writes must be conservative/exact.
- Keep PC and mobile fixes global/systemic, not one-event CSS patches.

## Production deployment state at checkpoint
Backend project:
- API latest observed deployment: SUCCESS
- results-worker latest observed deployment: SUCCESS
- frozen matrix count 180

Frontend:
- ninkosports latest observed deployment: SUCCESS

