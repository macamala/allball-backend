# NinkoSports News05 — source coverage checkpoint — 27 September 2026

## Purpose

Continue News source discovery without touching Live Scores, production Railway services, scheduler, database, AI budget/ledger, or frontend.

This is **source discovery coverage**, not a republication licence and not a claim that production ingestion is already 41/41. Publisher prose/images must not be copied into NinkoSports. Use source pages as factual evidence, retain source URL/publisher/time, write original NinkoSports copy, and hold/skip when evidence is insufficient or conflicting.

## Coverage state

- Canonical News sports: **41**.
- News03 + News04 prepared RSS/Atom metadata coverage: **35/41 sport scopes**, 45 prepared endpoints.
- The six RSS gaps were: `ea-sports-fc`, `league-of-legends`, `valorant`, `call-of-duty`, `overwatch`, `rocket-league`.
- Current 27 Sep research confirms a fresh public official first-party news path for all six. Therefore discovery now has a **41/41 source path**. These six need an HTML/JSON-LD/embedded-data discovery adapter rather than fake RSS URLs.

## Six remaining scopes — official primary + official backup

| Sport | Primary | Official backup | Observation |
|---|---|---|---|
| EA Sports FC | https://www.ea.com/games/ea-sports-fc/fc-pro/news | https://www.ea.com/news filtered to FC/FC Pro | Dated 2026 FC Pro stories and readable article pages. |
| League of Legends | https://lolesports.com/en-US/lolesports/news | LoL Esports home/schedule NEWS modules; leagueoflegends.com news only as secondary game-context evidence | Dated Sep 2026 esports stories and readable full articles. |
| VALORANT | https://valorantesports.com/en-US/news | https://playvalorant.com/en-us/news/ filtered to Esports | Both official Riot surfaces expose explicit timestamps/categories and current Sep 2026 VCT stories. |
| Call of Duty | https://callofdutyleague.com/en-us/news | Official COD/Activision news only when clearly CDL/esports related | CDL index exposes Announcement/News/Recap/Match VOD categories. |
| Overwatch | https://esports.overwatch.com/en-us/ NEWS module and /news articles | https://overwatch.blizzard.com/en-us/news/ for OWCS/competitive stories | Current OWWC/OWCS material and readable Blizzard competitive articles. |
| Rocket League | https://www.rocketleague.com/news/tag/competitive | https://www.rocketleague.com/news plus https://www.rocketleague.com/competitive | Competitive tag exposes dated RLCS stories through Sep 2026 and readable full articles. |

## 41-sport primary discovery coverage

The existing `bot/news_source_catalog.py` already has a primary discovery URL for every canonical News sport. Keep it as the authoritative sport-to-source catalog and extend ingestion by representation instead of inventing feeds.

1. football — FIFA / BBC Sport RSS discovery
2. basketball — FIBA / broad basketball RSS discovery
3. tennis — ATP Tour / BBC Sport RSS
4. motorsport — FIA / BBC Formula 1 RSS
5. american-football — NFL / broad American-football RSS
6. ice-hockey — IIHF / broad ice-hockey RSS
7. baseball — MLB / broad baseball RSS
8. rugby — World Rugby / BBC Rugby Union RSS
9. rugby-league — International Rugby League / BBC Rugby League RSS
10. cricket — ICC / BBC Cricket RSS
11. volleyball — FIVB
12. handball — IHF + Handball Planet prepared discovery
13. futsal — FIFA + Futsal Focus / U.S. Futsal prepared discovery
14. water-polo — World Aquatics + USA Water Polo / SwimSwam
15. field-hockey — FIH + The Hockey Paper
16. australian-rules — AFL + Zero Hanger
17. netball — World Netball
18. lacrosse — World Lacrosse + USA Lacrosse/Inside Lacrosse
19. table-tennis — ITTF + Table Tennis England
20. badminton — BWF + Badzine/myKhel
21. snooker — World Snooker Tour + BBC/WPBSA/WSF
22. darts — PDC + BBC/Dartsnews
23. boxing — World Boxing + BBC Boxing RSS
24. mma — UFC + broad MMA RSS discovery
25. horse-racing — BHA + BBC/Racing NSW
26. greyhound-racing — GBGB
27. harness-racing — Harness Racing Australia + USTA
28. golf — PGA Tour + BBC Golf RSS
29. cycling — UCI + BBC Cycling RSS
30. athletics — World Athletics + BBC Athletics RSS
31. swimming — World Aquatics + BBC Swimming RSS
32. winter-sports — FIS + BBC/FasterSkier/Etusuora
33. esports — ESL + general esports discovery
34. ea-sports-fc — EA FC Pro HTML + EA News backup
35. counter-strike — Valve Steam News RSS plus official tournament evidence
36. league-of-legends — LoL Esports HTML + LoL official backup
37. dota-2 — Valve/Dota official news + Steam News metadata
38. valorant — VALORANT Esports HTML + PlayVALORANT Esports
39. call-of-duty — Call of Duty League HTML + official COD/Activision backup
40. overwatch — Overwatch Esports HTML + Blizzard competitive news
41. rocket-league — Rocket League Competitive HTML + News/Competitive backup

## Runtime design to turn source coverage into production coverage

Add one generic `official_html` representation beside existing RSS:

1. Public HTTPS only, existing bounded robots-aware transport.
2. Extract same-origin story links from anchors plus JSON-LD / embedded app state.
3. Parse explicit title + publication time; unknown/future/stale dates fail closed under existing freshness policy.
4. Canonicalize tracking URLs and dedupe before any AI call.
5. Fetch article page and require sufficient source evidence; landing metadata alone is never article body.
6. Independently classify from title + source body; configured sport is a discovery hint only.
7. Require source classification and generated-draft classification agreement or hold.
8. Store source URL/publisher/time and publish only original NinkoSports prose; never publisher prose fallback.
9. Do not ingest source images unless separately permitted/licensed.
10. Isolate failures per source so one changed website cannot stop other sports.

Recommended per-source config: approved origin, landing path, allowed article path prefixes, optional category requirement, parser strategy (`jsonld`, `embedded_json`, `anchors`), publisher, sport hint, secondary official lane.

## Rights/source guard

Public accessibility is not a commercial reuse licence. NinkoSports should use discovery + factual verification + attribution + independently written copy. Do not republish/lightly rewrite publisher prose, strip required attribution, proxy publisher images, or assume RSS means commercial derivative-use permission.

Current research found restrictive terms for several tempting aggregation/feed shortcuts, including Guardian RSS, WTA RSS, Yahoo RSS and Google News/service feeds. ESPN RSS also has display/attribution restrictions. Do not count these as unrestricted free commercial content licences.

## Status

- **SOURCE DISCOVERY: 41/41 sports have a concrete path.**
- **RSS/Atom prepared adapter coverage: 35/41.**
- **HTML-first official adapter required: 6/41.**
- **Production source → original article publication is NOT claimed here.**
- No Railway Agent, deploy, production DB write, AI request, main reset, Live Scores change, scheduler change, frontend change or paid source was used.

Next implementation unit: one bounded generic official-HTML discovery adapter for the six scopes above, then reuse it for other official landing pages already in the 41-sport catalog.