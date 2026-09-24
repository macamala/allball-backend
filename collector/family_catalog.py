"""Family-level adapter keys, source types, and default endpoints.

One adapter per upstream family. Competition-specific IDs/URLs live on
source mappings, not as 184 separate scrapers.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from collector.verified_coverage import OPENFOOTBALL_FILES, OPENLIGADB_LEAGUES, THESPORTSDB_LEAGUES

JSON_ADAPTERS = {
    "openfootball": "openfootball-json",
    "openligadb": "openligadb",
    "thesportsdb": "thesportsdb",
    "opendota": "opendota",
    "squiggle": "squiggle-afl",
    "cricsheet": "cricsheet-json",
    "fifa-digital": "fifa-json",
    "nhl-web": "nhl-web",
    "mlb-statsapi": "mlb-statsapi",
    "khl-mobile": "khl-mobile",
    "pulselive": "pulselive-family",
    "jolpica-ergast": "jolpica-f1",
    "euroleague-live": "euroleague-live",
    "openf1": "generic-http",
    "liquipedia": "liquipedia",
    "sackmann-tennis": "sackmann-csv",
    "omega-timing": "omega-timing",
    "sportscore": "sportscore",
    "fotmob": "fotmob",
    "sofascore-web": "sofascore-web",
    "pga-graphql": "pga-graphql",
    "click-tt": "click-tt-remix",
    "click-tt-remix": "click-tt-remix",
    "altiusrt-html": "altiusrt-html",
    "championdata-netball": "championdata-netball",
    "gbgb-meeting-json": "gbgb-meeting-json",
    "cfl-scoreboard-json": "cfl-scoreboard-json",
    "lolesports-json": "lolesports-json",
    "f1-livetiming-index": "f1-livetiming-index",
    "world-aquatics-api": "world-aquatics-api",
    "wta-json": "wta-json",
    "sporting-events": "sporting-events",
    "worldcup26-api": "worldcup26-api",
    "sportsrc": "sportsrc",
    "soccerway": "soccerway-html",
    "aiff-web": "aiff-web",
    "rte-rugby": "rte-rugby",
    "super-rugby-html": "super-rugby-html",
    "eliteprospects": "eliteprospects",
    "volleyballworld": "volleyballworld",
    "cev-competition-area": "cev-competition-area",
    "dataproject-web": "dataproject-web",
    "dataproject-wcm": "dataproject-web",
    "prod2-web": "prod2-web",
    "acb-web": "acb-html",
    "formula-e-web": "formula-e-web",
    "netballpass": "netballpass",
    "world-netball-web": "world-netball-web",
    "futsalplanet": "futsalplanet",
    "gbgb-web": "gbgb-web",
    "fis-web": "fis-web",
    "eurohockey-web": "eurohockey-web",
    "ettu-web": "ettu-web",
    "nll-web": "nll-web",
    "eurosport-volleyball": "eurosport-volleyball",
    "pcs-web": "pcs-web",
    "fcpro-web": "fcpro-web",
    "gri-web": "gri-web",
    "total-waterpolo": "total-waterpolo",
    "sporting-life": "sporting-life",
    "hbl-web": "hbl-web",
    "ibu-web": "ibu-web",
    "rte-cycling": "rte-cycling",
    "world-athletics-web": "world-athletics-web",
    "nrl-draw-web": "nrl-draw-web",
    "standardbred-canada-web": "standardbred-canada-web",
    "hrnsw-web": "hrnsw-web",
    "letrot-web": "letrot-web",
    "equidia-web": "equidia-web",
    "england-hockey-web": "england-hockey-web",
    "lacrosse-canada-web": "lacrosse-canada-web",
    "fiaf2-web": "fiaf2-web",
    "fiaf3-web": "fiaf3-web",
    "fia-web": "fia-web",
    "aso-letour": "aso-letour",
    "scottish-hockey-web": "scottish-hockey-web",
    "gpcqm-web": "gpcqm-web",
    "woodbine-mohawk-web": "woodbine-mohawk-web",
    "uefa-futsal-web": "uefa-futsal-web",
    "lnf-web": "lnf-web",
    "wikipedia-lnbp-web": "wikipedia-lnbp-web",
    "diamond-league-pdf": "diamond-league-pdf",
    "tischtennislive": "tischtennislive",
    "ttbl-web": "ttbl-web",
    "wikipedia-all-england-web": "wikipedia-all-england-web",
    "wikipedia-uefa-futsal-web": "wikipedia-uefa-futsal-web",
    "wikipedia-lol-worlds-web": "wikipedia-lol-worlds-web",
    "wikipedia-fifa-futsal-web": "wikipedia-fifa-futsal-web",
    "meadowlands-web": "meadowlands-web",
    "cetus-web": "cetus-web",
    "club-menangle-web": "club-menangle-web",
    "harrington-web": "harrington-web",
    "wikipedia-indonesia-open-web": "wikipedia-indonesia-open-web",
    "kompas-web": "kompas-web",
    "cbf-fifa-futsal-web": "cbf-fifa-futsal-web",
    "afa-fifa-futsal-web": "afa-fifa-futsal-web",
    "nordic-waterpolo-native": "nordic-waterpolo-native",
    "ettu-news-results": "ettu-news-results",
    "fftt-web": "fftt-web",
    "kpga-web": "kpga-web",
    "rocketleague-recaps": "rocketleague-recaps",
    "blizzard-owcs-recaps": "blizzard-owcs-recaps",
    "world-aquatics-web": "world-aquatics-web",
    "wikipedia-wa-wp-web": "wikipedia-wa-wp-web",
    "pgl-web": "pgl-web",
    "wikipedia-rlcs-web": "wikipedia-rlcs-web",
    "wikipedia-vct-web": "wikipedia-vct-web",
    "ewc-owcs-web": "ewc-owcs-web",
    "dttb-web": "dttb-web",
    "skidskytte-web": "skidskytte-web",
    "wikipedia-korean-tour-web": "wikipedia-korean-tour-web",
    "wikipedia-irish-greyhound-derby-web": "wikipedia-irish-greyhound-derby-web",
    "wikipedia-owcs-world-finals-web": "wikipedia-owcs-world-finals-web",
}

CREDENTIAL_ENV = {
    "startgg": "NINKO_SOURCE_STARTGG_CREDENTIALS",
    "altiusrt": "NINKO_SOURCE_ALTIUSRT_CREDENTIALS",
    "snooker-org": "NINKO_SOURCE_SNOOKER_ORG_CREDENTIALS",
}

FAMILY_URLS = {
    "openfootball": "https://raw.githubusercontent.com/openfootball/football.json/master/",
    "openligadb": "https://api.openligadb.de/getmatchdata/bl1",
    "thesportsdb": "https://www.thesportsdb.com/api/v1/json/123/all_leagues.php",
    "opendota": "https://api.opendota.com/api/proMatches",
    "squiggle": "https://api.squiggle.com.au/?q=games",
    "cricsheet": "https://cricsheet.org/downloads/recently_added_7_json.zip",
    "fifa-digital": "https://api.fifa.com/api/v3/calendar/matches?count=20&language=en",
    "nhl-web": "https://api-web.nhle.com/v1/schedule/now",
    "mlb-statsapi": "https://statsapi.mlb.com/api/v1/schedule?sportId=1",
    "khl-mobile": "https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json",
    "pulselive": "https://api.wr-rims-prod.pulselive.com/rugby/v3/match?pageSize=20&sport=mru",
    "jolpica-ergast": "https://api.jolpi.ca/ergast/f1/current.json",
    "euroleague-live": "https://live.euroleague.net/api/Header?gamecode=1&seasoncode=E2025",
    "openf1": "https://api.openf1.org/v1/meetings?year=2026",
    "bbc-sport": "https://www.bbc.com/sport",
    "premier-league-official": "https://www.premierleague.com/tables",
    "nba-web": "https://www.nba.com/games",
    "wnba-web": "https://www.wnba.com/schedule",
    "formula1-web": "https://www.formula1.com/en/results.html",
    "espn-html": "https://www.espn.com",
    "nrl-web": "https://www.nrl.com/draw",
    "super-league-web": "https://www.superleague.co.uk",
    "afltables": "https://afltables.com/afl/afl_index.html",
    "footywire": "https://www.footywire.com",
    "omega-timing": "https://www.omegatiming.com",
    "sportscore": "https://sportscore.com/api/widget/matches/?sport=football&limit=20&src=ninkosports",
    "fotmob": "https://www.fotmob.com/api/data/matches?date=20260920",
    "sofascore-web": "https://www.sofascore.com/api/v1/sport/football/events/live",
    "pga-graphql": "https://orchestrator.pgatour.com/graphql",
    "click-tt-remix": "https://www.mytischtennis.de",
    "altiusrt-html": "https://fih.altiusrt.com",
    "championdata-netball": "https://mc.championdata.com/data/competitions.json",
    "gbgb-meeting-json": "https://api.gbgb.org.uk/api/results",
    "cfl-scoreboard-json": "https://www.cfl.ca",
    "lolesports-json": "https://esports-api.lolesports.com",
    "f1-livetiming-index": "https://livetiming.formula1.com/static/Index.json",
    "world-aquatics-api": "https://api.worldaquatics.com",
    "wta-json": "https://api.wtatennis.com/tennis/tournaments/901/2026/matches",
    "sporting-events": "https://sporting-events.org/data/",
    "worldcup26-api": "https://worldcup26.ir/get/soccer/leagues",
    "sportsrc": "https://api.sportsrc.org/?data=results&category=leagues",
    "soccerway": "https://www.soccerway.com",
    "aiff-web": "https://www.the-aiff.com/competitions/isl",
    "rte-rugby": "https://www.rte.ie/sport/results/rugby/",
    "super-rugby-html": "https://super.rugby/superrugby/match-centre/",
    "eliteprospects": "https://www.eliteprospects.com",
    "cev-competition-area": "https://www-old.cev.eu/Competition-Area/",
    "prod2-web": "https://prod2.lnr.fr/calendrier-et-resultats",
    "netballpass": "https://www.netballpass.com/results/2026/suncorp-super-netball",
    "eurohockey-web": "https://eurohockey.org/calendar",
    "microplus-timing": "https://results.microplustimingservices.com",
    "fivb-web": "https://en.volleyballworld.com",
    "volleyballworld": "https://en.volleyballworld.com",
    "ehf-web": "https://old.eurohandball.com/events/competitions",
    "fih-web": "https://www.fih.hockey",
    "altiusrt": "https://www.altiusrt.com",
    "world-netball-web": "https://netball.sport",
    "netball-australia-web": "https://netball.com.au",
    "world-lacrosse-web": "https://worldlacrosse.sport",
    "click-tt": "https://www.mytischtennis.de",
    "tischtennislive": "https://bettv.tischtennislive.de",
    "tournamentsoftware": "https://www.tournamentsoftware.com",
    "rankedin": "https://rankedin.com",
    "wst-web": "https://www.wst.tv",
    "pdc-web": "https://www.pdc.tv",
    "ufc-web": "https://www.ufc.com/events",
    "bha-web": "https://www.britishhorseracing.com",
    "liquipedia": "https://liquipedia.net",
    "startgg": "https://www.start.gg",
    "world-athletics-web": "https://worldathletics.org",
    "fis-web": "https://www.fis-ski.com",
    "uci-web": "https://www.uci.org",
    "aso-letour": "https://www.letour.fr",
    "sackmann-tennis": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_2026.csv",
    "retrosheet": "https://www.retrosheet.org",
    "sports-reference": "https://www.sports-reference.com",
    "dataproject-wcm": "https://www.dataproject.com",
    "cetus-web": "https://www.cetus.fi",
    "nba-japan-web": "https://www.badminton.or.jp",
    "jla-web": "https://www.lacrosse.gr.jp",
    "meadowlands-web": "https://www.playmeadowlands.com/race-day-information/results",
    "delaware-lbj-web": "https://www.littlebrownjug.com",
    "bwf-match-data-github": "https://raw.githubusercontent.com/SahilMotyar/bwf-match-data/master/README.md",
    "gri-web": "https://www.grireland.ie",
    "hrnsw-web": "https://www.hrnsw.com.au",
    "usta-web": "https://racing.ustrotting.com",
    "standardbred-canada-web": "https://standardbredcanada.ca",
    "gbgb-web": "https://www.gbgb.org.uk",
    "letrot-web": "https://www.letrot.com",
    "equidia-web": "https://www.equidia.fr",
    "pga-tour-web": "https://www.pgatour.com",
    "europeantour-web": "https://www.europeantour.com",
    "cyclingnews": "https://www.cyclingnews.com",
    "opentrack": "https://opentrack.run",
    "ibu-web": "https://www.biathlonresults.com",
    "rte-cycling": "https://www.rte.ie/sport/results/cycling/",
    "nrl-draw-web": "https://www.nrl.com/draw/",
    "england-hockey-web": "https://www.englandhockey.co.uk",
    "lacrosse-canada-web": "https://www.lacrosse.ca",
    "fiaf2-web": "https://www.fiaformula2.com/Standings/Driver",
    "fiaf3-web": "https://www.fiaformula3.com/Standings/Driver",
    "fia-web": "https://www.fia.com",
    "scottish-hockey-web": "https://scottish-hockey.org.uk",
    "gpcqm-web": "https://gpcqm.ca/grand-prix-montreal/",
    "woodbine-mohawk-web": "https://woodbine.com/mohawk/",
    "uefa-futsal-web": "https://www.uefa.com/uefafutsalchampionsleague/",
    "wta-web": "https://www.wtatennis.com",
    "lolesports-web": "https://lolesports.com",
    "valorantesports-web": "https://valorantesports.com",
    "overwatch-esports-web": "https://overwatchesports.com",
    "cdl-web": "https://callofdutyleague.com",
    "cue-tracker": "https://cuetracker.net",
    "futsalplanet": "https://www.futsalplanet.com",
    "hbl-web": "https://www.liquimoly-hbl.de",
    "nll-web": "https://www.nll.com",
    "pll-web": "https://premierlacrosseleague.com",
    "mls-web": "https://www.mlssoccer.com",
    "nwsl-web": "https://www.nwslsoccer.com",
    "usl-web": "https://www.uslsoccer.com",
    "a-league-web": "https://www.aleague.com.au",
    "jleague-web": "https://www.jleague.jp",
    "kleague-web": "https://www.kleague.com",
    "liga-mx-web": "https://www.ligabbva.mx",
    "conmebol-web": "https://www.conmebol.com",
    "concacaf-web": "https://www.concacaf.com",
    "caf-web": "https://www.cafonline.com",
    "afc-web": "https://www.the-afc.com",
    "efl-web": "https://www.efl.com",
    "spfl-web": "https://spfl.co.uk",
    "dfb-web": "https://www.dfb.de",
    "eredivisie-web": "https://eredivisie.eu",
    "liga-portugal-web": "https://www.ligaportugal.pt",
    "allsvenskan-web": "https://www.allsvenskan.se",
    "eliteserien-web": "https://www.eliteserien.no",
    "denmark-superliga-web": "https://www.superliga.dk",
    "austria-bundesliga-web": "https://www.bundesliga.at",
    "superliga-web": "https://www.superliga.rs",
    "hnl-web": "https://hnl.hr",
    "prvaliga-web": "https://www.prvaliga.si",
    "ekstraklasa-web": "https://www.ekstraklasa.org",
    "romania-superliga-web": "https://www.lpf.ro",
    "spl-web": "https://spl.sa",
    "thaileague-web": "https://thaileague.co.th",
    "psl-web": "https://www.psl.co.za",
    "cfl-web": "https://www.cfl.ca",
    "acb-web": "https://www.acb.com",
    "lnbp-web": "https://lnbp.mx",
    "del-web": "https://www.penny-del.org",
    "liiga-web": "https://liiga.fi",
    "shl-web": "https://www.shl.se",
    "chl-web": "https://www.championshockeyleague.com",
    "npb-web": "https://npb.jp",
    "kbo-web": "https://www.koreabaseball.com",
    "prem-rugby-web": "https://www.premiershiprugby.com",
    "lnr-web": "https://www.lnr.fr",
    "super-rugby-web": "https://super.rugby",
    "ultimate-rugby": "https://www.ultimaterugby.com",
    "cev-web": "https://www.cev.eu",
    "plusliga-web": "https://www.plusliga.pl",
    "lib-web": "https://www.legavolley.it",
    "asobal-web": "https://www.asobal.es",
    "lnh-web": "https://www.lnh.fr",
    "tophaandbold-web": "https://tophaandbold.dk",
    "lnf-web": "https://lnfoficial.com.br/talentos-lnf/tabela-de-jogos/",
    "lnf-oficial-web": "https://www.lnf.com.br",
    "wikipedia-lnbp-web": "https://es.wikipedia.org/wiki/Liga_Nacional_de_Baloncesto_Profesional_de_M%C3%A9xico_2026",
    "diamond-league-pdf": "https://ath-wdl-archive.azureedge.net/2026/paris/ATH-------------------------------_MUL_1.0.PDF",
    "tischtennislive": "https://bettv.tischtennislive.de/?L1=Ergebnisse&L2=TTStaffeln&L2P=21912&L3=Spielbericht&L3P=1036821",
    "ttbl-web": "https://www.ttbl.de/bundesliga/gameschedule/2026-2027/2/all",
    "wikipedia-all-england-web": "https://en.wikipedia.org/wiki/2026_All_England_Open",
    "wikipedia-uefa-futsal-web": "https://en.wikipedia.org/wiki/2025%E2%80%9326_UEFA_Futsal_Champions_League",
    "wikipedia-lol-worlds-web": "https://en.wikipedia.org/wiki/2025_League_of_Legends_World_Championship",
    "wikipedia-fifa-futsal-web": "https://en.wikipedia.org/wiki/2024_FIFA_Futsal_World_Cup",
    "meadowlands-web": "https://playmeadowlands.com/race-day-information/results/",
    "cetus-web": "https://www.cetus.fi/kilpaurheilu/vesipallo/miesten-edustusjoukkueen-ottelut/",
    "club-menangle-web": "https://www.clubmenangle.com.au/perfect-record-remains-intact/",
    "harrington-web": "https://harringtonraceway.com/uncategorized/disturbed-hanover-teague-headline-wednesday-program/",
    "wikipedia-indonesia-open-web": "https://en.wikipedia.org/wiki/2026_Indonesia_Open",
    "kompas-web": "https://www.kompas.com/badminton/read/2026/06/07/17015878/hasil-final-polytron-indonesia-open-2026-jonatan-christie-runner-up",
    "cbf-fifa-futsal-web": "https://www.cbf.com.br/selecao-brasileira/noticias/detalhes/futsal/conheca-os-nossos-hexacampeoes-mundiais-de-futsal",
    "afa-fifa-futsal-web": "https://www.afa.com.ar/es/posts/argentina-es-subcampeon-del-mundial-de-futsal",
    "nordic-waterpolo-native": "https://nordicwaterpololeague.com/results-and-standings-final-eight/",
    "ettu-news-results": "https://www.ettu.org/france-edge-germany-in-thriller-to-claim-under-15-girls-teams-title/",
    "fftt-web": "https://www.fftt.com/actualites/france-jeunes/championnats-deurope-jeunes-les-bleuets-realisent-un-triple-historique-par-equipes/",
    "kpga-web": "https://www.kpga.co.kr/tours/leaderboard/?srhGameId=202611000015M&srhYear=2026&subType=leaderboard&tourId=11",
    "rocketleague-recaps": "https://www.rocketleague.com/news/karmine-corp-clinch-the-win-for-a-home-crowd-at-the-rocket-league-paris-major",
    "blizzard-owcs-recaps": "https://esports.overwatch.com/en-us/news/champions-clash-viewers-guide",
    "world-aquatics-web": "https://www.worldaquatics.com/competitions/5135/men-s-water-polo-world-cup-2026-division-2/results?event=a76c06d2-2982-4fb1-8bee-b48b44d6cbc2&unit=semifinals",
    "wikipedia-wa-wp-web": "https://en.wikipedia.org/wiki/2026_Men%27s_Water_Polo_World_Cup",
    "pgl-web": "https://www.pglesports.com/cs2/pgl-bucharest-2026/",
    "wikipedia-rlcs-web": "https://en.wikipedia.org/wiki/Rocket_League_Championship_Series",
    "wikipedia-vct-web": "https://en.wikipedia.org/wiki/Valorant_Champions_Tour",
    "ewc-owcs-web": "https://www.esportsworldcup.com/en/competitions/2026/overwatch2",
    "dttb-web": "https://www.tischtennis.de/news/jem-die-spiele-der-deutschen-am-dienstag-1.html",
    "skidskytte-web": "https://www.skidskytte.se/folj-oss/nyheter/nyheter/2026-01-18-dubbla-pallplatser-for-sverige-i-jaktstarterna",
    "wikipedia-korean-tour-web": "https://en.wikipedia.org/wiki/2026_Korean_Tour",
    "wikipedia-irish-greyhound-derby-web": "https://en.wikipedia.org/wiki/2025_Irish_Greyhound_Derby",
    "wikipedia-owcs-world-finals-web": "https://en.wikipedia.org/wiki/Overwatch_Champions_Series",
    "formula-e-web": "https://www.fiaformulae.com",
    "fiawec-web": "https://www.fiawec.com",
    "crash-net": "https://www.crash.net",
    "isl-web": "https://www.indiansuperleague.com",
    "apf-web": "https://www.apf.org.py",
    "anfp": "https://www.anfp.cl",
    "chile-anfp-web": "https://www.anfp.cl",
    "dimayor-web": "https://dimayor.com.co",
    "liga-profesional-web": "https://www.ligaprofesional.ar",
    "tenfield-stats": "https://www.tenfield.com.uy",
    "nacion-web": "https://www.nacion.com",
    "varzesh3-web": "https://www.varzesh3.com",
    "kawarji-web": "https://www.kawrji.com",
    "championat-asia": "https://www.championat.com",
    "yahoo-sportsnavi": "https://sports.yahoo.co.jp",
    "yahoo-taiwan": "https://tw.sports.yahoo.com",
    "sporting-life": "https://www.sportinglife.com",
    "sport-de-web": "https://www.sport.de",
    "soccerpunter-web": "https://www.soccerpunter.com",
    "futbol24-web": "https://www.futbol24.com",
    "the-sports-org": "https://www.the-sports.org",
    "abc-sport": "https://www.abc.net.au/news/sport",
    "sanctioning-bodies": "https://www.ibf-usba.org",
    "ettu-web": "https://www.ettu.org",
    "nordic-wpl-web": "https://nordicwaterpololeague.com",
    "eurosport-volleyball": "https://www.tntsports.co.uk",
    "pcs-web": "https://www.procyclingstats.com",
    "fcpro-web": "https://www.ea.com/games/ea-sports-fc/fc-pro",
    "total-waterpolo": "https://total-waterpolo.com",
    "vpfl-web": "https://www.volleyball.or.jp",
    "vpf-web": "https://www.volleyball.or.jp",
    "volleytimes-web": "https://volleytimes.com",
    "golmates-web": "https://golmates.com",
    "sfl-web": "https://sfl.ch",
    "fortuna-liga-cz-web": "https://www.fortunaliga.cz",
    "futbalnet": "https://www.futbalnet.sk",
    "nfsbih-web": "https://www.nfsbih.ba",
    "parvaliga-web": "https://prvafudbalskaliga.me",
    "pflk-web": "https://pflk.kz",
    "a-pfg-web": "https://fpbg.bg",
    "moneypuck": "https://moneypuck.com",
}

OPENLIGA_BY_COMP = {row["competition_id"]: row["shortcut"] for row in OPENLIGADB_LEAGUES}
TSDB_BY_COMP = {row["competition_id"]: row["source_competition_id"] for row in THESPORTSDB_LEAGUES}
OPENFOOTBALL_BY_COMP = {row["competition_id"]: row["paths"] for row in OPENFOOTBALL_FILES}

PULSELIVE_BY_SPORT = {
    "rugby": "https://api.wr-rims-prod.pulselive.com/rugby/v3/match?pageSize=20&sport=mru",
    "rugby-union": "https://api.wr-rims-prod.pulselive.com/rugby/v3/match?pageSize=20&sport=mru",
    "motorsport": "https://api.motogp.pulselive.com/motogp/v1/results/seasons",
}

# Same-family public JSON used by the official sites (not new providers).
FAMILY_PUBLIC_JSON = {
    "ibu-web": [
        "https://www.biathlonresults.com/modules/sportapi/api/Events?SeasonId=2526",
        "https://www.biathlonresults.com/modules/sportapi/api/Events?SeasonId=2425",
    ],
    "liiga-web": [
        "https://liiga.fi/api/v1/games?tournament=runkosarja",
    ],
    "formula-e-web": [
        "https://api.formula-e.pulselive.com/formula-e/v1/events",
    ],
    "sporting-life": [
        "https://www.sportinglife.com/api/horse-racing/racing/results",
        "https://www.sportinglife.com/api/greyhounds/results",
    ],
    "gbgb-web": [
        "https://api.gbgb.org.uk/api/results",
    ],
    "acb-web": [
        "https://api2.acb.com/api/v1/calendar",
    ],
}

# Hostnames invented by slug inference that do not match the mapped family site.
CANONICAL_HOST_FIX = {
    "a-league.com.au": "https://www.aleague.com.au",
}

COMPETITION_PAGE_URLS = {
    ("ehf-web", "ehf-champions-league"): "https://old.eurohandball.com/ec/00-01/cl/men/2026-27/round/1/Group%2BPhase",
    ("ehf-web", "ehf-competitions"): "https://old.eurohandball.com/events/competitions",
    ("dataproject-wcm", "italy-superlega"): "https://www.legavolley.it/calendario",
    ("dataproject-web", "italy-superlega"): "https://www.legavolley.it/calendario",
    ("dataproject-web", "plusliga"): "https://plusliga.pl/games",
    ("dataproject-web", "cev-eurovolley-men"): "https://www-old.cev.eu/Competition-Area/CompetitionView.aspx?ID=1572",
    ("futbalnet", "slovakia-super-liga"): "https://sportnet.sme.sk/futbalnet/z/ulk/s/nike-liga/vysledky/",
    ("aiff-web", "india-super-league"): "https://www.the-aiff.com/competitions/isl",
    ("hbl-web", "germany-handball-bundesliga"): "https://www.liquimoly-hbl.de/de/hbl-gmbh/content/hbl-gmbh-ver%C3%B6ffentlicht-vorl%C3%A4ufige-spielpl%C3%A4ne-der-saison-202627-von-opel-handball-bundesliga-und-2-hbl",
    ("ibu-web", "biathlon"): "https://www.biathlonresults.com/modules/sportapi/api/Events?SeasonId=2627",
    ("rte-cycling", "tour-de-france"): "https://www.rte.ie/sport/results/cycling/",
    ("rte-cycling", "uci-calendar"): "https://www.rte.ie/sport/results/cycling/",
    ("world-athletics-web", "wa-calendar"): "https://worldathletics.org/competition/calendar-results",
    ("nrl-draw-web", "nrl"): "https://www.nrl.com/draw/?competition=111&season=2026",
    ("england-hockey-web", "fih-eurohockey"): "https://www.englandhockey.co.uk/competitions/international",
    ("lacrosse-canada-web", "world-lacrosse"): "https://www.lacrosse.ca/",
    ("fiaf2-web", "formula-2"): "https://www.fiaformula2.com/Standings/Driver",
    ("fiaf3-web", "formula-3"): "https://www.fiaformula3.com/Standings/Driver",
    ("fia-web", "formula-2"): "https://www.fia.com/events/formula-2-championship/season-2026/melbourne/sprint-race-classification",
    ("fia-web", "formula-3"): "https://www.fia.com/events/formula-3-championship/season-2026/melbourne/sprint-race-classification",
    ("scottish-hockey-web", "fih-eurohockey"): "https://scottish-hockey.org.uk/resounding-victory-over-turkiye-for-scotland-men-in-rome/",
    ("denmark-superliga-web", "denmark-superliga"): "https://www.superliga.dk/kampprogram",
    ("allsvenskan-web", "sweden-allsvenskan"): "https://www.allsvenskan.se/matcher",
    ("conmebol-web", "copa-libertadores"): "https://www.conmebol.com/es/copa-libertadores/",
    ("conmebol-web", "copa-sudamericana"): "https://www.conmebol.com/es/copa-sudamericana/",
    ("nwsl-web", "usa-nwsl"): "https://www.nwslsoccer.com/schedule",
    ("usl-web", "usa-usl-championship"): "https://www.uslchampionship.com",
    ("a-league-web", "australia-a-league"): "https://www.aleague.com.au/fixtures",
    ("a-league-web", "australia-a-league-women"): "https://www.aleague.com.au/fixtures",
    ("netball-australia-web", "ssn-australia"): "https://netball.com.au",
    ("superliga-web", "serbia-superliga"): "https://www.superliga.rs/sezona/raspored-i-rezultati/",
    ("caf-web", "caf-champions-league"): "https://www.cafonline.com/caf-champions-league/",
    ("cev-web", "cev-eurovolley-men"): "https://www.cev.eu/calendar/",
    ("rte-rugby", "france-top-14"): "https://www.rte.ie/sport/results/rugby/top-14/43093/results/",
    ("super-rugby-html", "super-rugby"): "https://super.rugby/superrugby/match-centre/?competition=205&season=2026",
    ("eliteprospects", "finland-liiga"): "https://www.eliteprospects.com/league/liiga/scores/2026-2027",
    ("volleyballworld", "plusliga"): "https://en.volleyballworld.com/volleyball/competitions/plusliga/",
    ("cev-competition-area", "cev-eurovolley-men"): "https://www-old.cev.eu/Competition-Area/CompetitionView.aspx?ID=1572",
    ("uci-web", "uci-calendar"): "https://www.uci.org",
    ("aso-letour", "tour-de-france"): "https://www.letour.fr/en/rankings",
    ("bha-web", "bha-meetings"): "https://www.britishhorseracing.com/racing/results/",
    ("gbgb-web", "gbgb-meetings"): "https://www.gbgb.org.uk/results/",
    ("wst-web", "wst-events"): "https://www.wst.tv/matches",
    ("nll-web", "nll"): "https://www.nll.com/schedule/",
    ("world-netball-web", "world-netball"): "https://netball.sport/events",
    ("tournamentsoftware", "bwf-and-national-events"): "https://bwfworldtour.tournamentsoftware.com",
    ("tournamentsoftware", "national-and-club"): "https://www.tournamentsoftware.com/find/tournament",
    ("rankedin", "national-and-club"): "https://rankedin.com/en/tournaments",
    ("click-tt", "germany-click-tt"): "https://www.mytischtennis.de/clicktt/",
    ("omega-timing", "world-aquatics-events"): "https://www.omegatiming.com/Sport",
    ("omega-timing", "world-aquatics-meets"): "https://www.omegatiming.com/Sport",
    ("prod2-web", "france-pro-d2"): "https://prod2.lnr.fr/calendrier-et-resultats",
    ("acb-web", "spain-acb"): "https://www.acb.com/es/liga/calendario",
    ("formula-e-web", "formula-e"): "https://www.fiaformulae.com/en/results-and-standings",
    ("world-netball-web", "world-netball"): "https://netball.sport/events-and-results/commonwealth-games/",
    ("eurohockey-web", "fih-eurohockey"): "https://www.eurohockey.org/calendar/event?id=c4d5b17a-29e1-4398-9bb0-72551b896742",
    ("nll-web", "nll"): "https://www.nll.com/schedule/scores/",
    ("eurosport-volleyball", "plusliga"): "https://eurosport.tvn24.pl/siatkowka/plusliga/2025-2026/kalendarz-wyniki.shtml",
    ("pcs-web", "uci-calendar"): "https://www.procyclingstats.com/race/gp-montreal/2026/result",
    ("sporting-life", "bha-meetings"): "https://www.sportinglife.com/racing/results/2026-09-17",
    ("fcpro-web", "competitive-ea-fc"): "https://www.ea.com/games/ea-sports-fc/fc-pro/news/fc-pro-world-championship-26-review",
    ("gri-web", "ireland-gri-meetings"): "https://www.grireland.ie/results/",
    ("gri-web", "irish-greyhound-derby"): "https://www.grireland.ie/results/view-results/?date=27-Sep-25&track=SPK",
    ("total-waterpolo", "nordic-water-polo-league"): "https://total-waterpolo.com/nordic-league-men-2025-26/",
    ("netballpass", "ssn-australia"): "https://www.netballpass.com/results/2026/suncorp-super-netball",
    ("futsalplanet", "brazil-lnf"): "http://www.futsalplanet.com/competitions.aspx?com=2737&cou=15&sea=2026",
    ("gbgb-web", "gbgb-meetings"): "https://www.gbgb.org.uk/racing/results/",
    ("fis-web", "fis-disciplines"): "https://www.fis-ski.com/DB/general/results.html?sectorcode=SB&raceid=24016&seasoncode=2026",
    ("ettu-web", "ettu-events"): "https://www.ettu.org/past-events/",
}

FAMILY_FIXTURE_PATHS = {
    "acb-web": "/partidos",
    "nwsl-web": "/schedule",
    "usl-web": "/schedule",
    "hbl-web": "/spielplan",
    "allsvenskan-web": "/spelschema",
    "denmark-superliga-web": "/kampprogram",
    "superliga-web": "/sezona/raspored-i-rezultati/",
    "nll-web": "/schedule/",
    "netball-australia-web": "/fixtures-results",
    "ibu-web": "/calendar",
    "gbgb-web": "/results",
    "lnr-web": "/calendrier",
    "liga-profesional-web": "/torneo/fixture",
    "nba-web": "/games",
    "nrl-web": "/draw",
    "plusliga-web": "/games",
    "a-league-web": "/fixtures",
    "futbalnet": "/",
    "sporting-life": "/racing/results",
    "wnba-web": "/schedule",
    "startgg": "/",
    "click-tt": "/",
    "tischtennislive": "/",
    "nordic-wpl-web": "/",
    "cetus-web": "/",
}

LIQUIPEDIA_WIKI = {
    "tier1": "counterstrike",
    "professional": "dota2",
    "worlds-msi-regional": "leagueoflegends",
    "lol-world-championship": "leagueoflegends",
    "vct": "valorant",
    "cdl-majors": "callofduty",
    "owcs-historical": "overwatch",
    "owcs-world-finals": "overwatch",
    "rlcs": "rocketleague",
    "competitive-ea-fc": "easportsfc",
    "cross-game-wiki": "counterstrike",
}

LIQUIPEDIA_PAGE = {
    "lol-world-championship": "World_Championship/2025",
    "vct": "Masters_Santiago_2026",
    "owcs-historical": "Overwatch_Champions_Series/2026/Midseason_Championship",
    "owcs-world-finals": "Overwatch_Champions_Series/2025/World_Finals",
    "rlcs": "Rocket_League_Championship_Series/2026/Paris_Major",
    "tier1": "PGL/2026/Bucharest",
}


def adapter_key_for(family: str, sport_id: str = "") -> str:
    if family == "pulselive" and sport_id == "motorsport":
        return "generic-http"
    if family == "bbc-sport":
        return "bbc-sport"
    if family in {"click-tt", "click-tt-remix"}:
        return "click-tt-remix"
    if family == "espn-html":
        return "espn-scoreboard"
    if family == "soccerway":
        return "soccerway-html"
    if family == "aiff-web":
        return "aiff-web"
    if family in {
        "rte-rugby",
        "super-rugby-html",
        "eliteprospects",
        "volleyballworld",
        "cev-competition-area",
        "dataproject-web",
        "dataproject-wcm",
        "prod2-web",
        "formula-e-web",
        "netballpass",
        "world-netball-web",
        "futsalplanet",
        "gbgb-web",
        "fis-web",
        "eurohockey-web",
        "ettu-web",
        "nll-web",
        "eurosport-volleyball",
        "pcs-web",
        "fcpro-web",
        "gri-web",
        "total-waterpolo",
        "sporting-life",
        "hbl-web",
        "ibu-web",
        "rte-cycling",
        "ufc-web",
        "world-athletics-web",
        "nrl-draw-web",
        "standardbred-canada-web",
        "hrnsw-web",
        "letrot-web",
        "equidia-web",
        "england-hockey-web",
        "lacrosse-canada-web",
        "fiaf2-web",
        "fiaf3-web",
        "fia-web",
        "aso-letour",
        "scottish-hockey-web",
        "gpcqm-web",
        "woodbine-mohawk-web",
        "uefa-futsal-web",
        "lnf-web",
        "wikipedia-lnbp-web",
        "diamond-league-pdf",
        "tischtennislive",
        "ttbl-web",
        "wikipedia-all-england-web",
        "wikipedia-uefa-futsal-web",
        "wikipedia-lol-worlds-web",
        "wikipedia-fifa-futsal-web",
        "meadowlands-web",
        "cetus-web",
        "club-menangle-web",
        "harrington-web",
        "wikipedia-indonesia-open-web",
        "kompas-web",
        "cbf-fifa-futsal-web",
        "afa-fifa-futsal-web",
        "nordic-waterpolo-native",
        "ettu-news-results",
        "fftt-web",
        "kpga-web",
        "rocketleague-recaps",
        "blizzard-owcs-recaps",
        "world-aquatics-web",
        "wikipedia-wa-wp-web",
        "pgl-web",
        "wikipedia-rlcs-web",
        "wikipedia-vct-web",
        "ewc-owcs-web",
        "dttb-web",
        "skidskytte-web",
        "wikipedia-korean-tour-web",
        "wikipedia-irish-greyhound-derby-web",
        "wikipedia-owcs-world-finals-web",
    }:
        return family
    if family == "acb-web":
        return "acb-html"
    return JSON_ADAPTERS.get(family, "generic-http")


def source_type_for(method: str, family: str = "") -> str:
    text = f"{method} {family}".lower()
    if "rss" in text or "atom" in text:
        return "RSS/feed"
    if "timing" in text:
        return "timing/results system"
    if "json" in text or "api" in text or "unauthenticated json" in text:
        return "official API" if "api" in text else "public JSON"
    if "html" in text or "spa" in text:
        return "public HTML"
    if "csv" in text or "zip" in text or "github" in text:
        return "other verified public source"
    return "other verified public source"


def polling_class_for(row: dict) -> str:
    live = str(row.get("live") or "").strip().lower()
    if live in {"y", "yes", "inferred"}:
        return "LIVE"
    if live in {"event", "session", "meeting", "timing", "html", "when listed", "when published"}:
        return "NEAR_LIVE"
    fixtures = str(row.get("fixtures") or "").strip().lower()
    if fixtures in {"y", "yes", "partial"}:
        return "NORMAL"
    return "SLOW"


POLL_SECONDS = {
    "LIVE": 60,
    "NEAR_LIVE": 180,
    "NORMAL": 900,
    "SLOW": 3600,
}


_COMPOUND_SLUG_TLDS = (
    ("-com-br", ".com.br"),
    ("-com-au", ".com.au"),
    ("-com-uy", ".com.uy"),
    ("-co-uk", ".co.uk"),
    ("-co-th", ".co.th"),
    ("-org-uk", ".org.uk"),
    ("-org-au", ".org.au"),
    ("-or-jp", ".or.jp"),
    ("-co-jp", ".co.jp"),
    ("-com-mx", ".com.mx"),
)


def _url_from_source_slug(blob: str) -> Optional[str]:
    text = (blob or "").lower()
    for slug, tld in _COMPOUND_SLUG_TLDS:
        found = re.search(rf"([a-z0-9](?:[a-z0-9-]{{0,40}}[a-z0-9])?){re.escape(slug)}", text)
        if found:
            return "https://" + found.group(1) + tld
    found = re.search(
        r"\b([a-z0-9](?:[a-z0-9-]{1,50}))-(com|org|net|edu|gov|sport|tv|io|info)\b",
        text,
    )
    if found:
        return f"https://{found.group(1)}.{found.group(2)}"
    if re.search(r"\bsuper\.rugby\b", text) or "super-rugby-web" in text or re.search(r"\bsuper-rugby fixtures", text):
        return "https://super.rugby"
    return None


def _with_source_path(url: str, blob: str, family: str = "") -> str:
    text = (blob or "").lower()
    host = (url or "").lower()
    if "sportinglife.com" in host or "sporting-life" in text:
        if "greyhound" in text:
            return "https://www.sportinglife.com/greyhounds/results"
        if "racing" in text or "horse" in text:
            return "https://www.sportinglife.com/racing/results"
    if not url:
        return url
    parsed_path = ""
    try:
        from urllib.parse import urlparse

        parsed_path = (urlparse(url).path or "").rstrip("/")
    except Exception:
        parsed_path = ""
    suffix = FAMILY_FIXTURE_PATHS.get(family or "")
    if suffix and parsed_path in {"", "/"}:
        return url.rstrip("/") + suffix
    if "nwslsoccer.com" in host and "schedule" in text and "/schedule" not in host:
        return url.rstrip("/") + "/schedule"
    if "scoreboard" in text and "/scoreboard" not in host and "espn" in host:
        return url.rstrip("/") + "/scoreboard"
    if "gbgb.org.uk" in host and "results" in text and "/result" not in host:
        return url.rstrip("/") + "/results"
    return url


def infer_url(family: str, source: str, probe: str = "", sport_id: str = "") -> Optional[str]:
    if family == "pulselive":
        return PULSELIVE_BY_SPORT.get(sport_id, FAMILY_URLS.get(family))
    if family == "espn-html":
        from collector.adapters_espn import ESPN_HTML

        blob = f"{source} {probe}"
        if "nfl" in blob.lower() and "college" not in blob.lower() and "ncaa" not in blob.lower():
            return ESPN_HTML["nfl"]
        if "college" in blob.lower() or "ncaa" in blob.lower():
            return ESPN_HTML["ncaa-football"]
        if "ufc" in blob.lower():
            return ESPN_HTML["ufc"]
    blob = f"{source} {probe}"
    found = re.search(r"https?://[^\s,;]+", blob)
    if found:
        return _with_source_path(found.group(0).rstrip(").,]"), blob, family)
    found = re.search(
        r"\b([a-z0-9][a-z0-9.-]+\.(?:com\.br|com\.au|com\.uy|co\.th|co\.uk|or\.jp|co\.jp|com|org|net|edu|gov|sport|rugby|tv|io|info|uk|au|de|fr|it|es|nl|pt|br|jp|kr|fi|se|no|dk|ch|at|cz|pl|ru|mx|cl|ar|za|sa|th|vn|bg|me|uy))(?:/[^\s]*)?(?=\s|$|[),;])",
        blob,
        re.I,
    )
    if found:
        host = found.group(1)
        if not host.startswith("http"):
            host = "https://" + host
        return _with_source_path(host, blob, family)
    slugged = _url_from_source_slug(blob)
    if slugged:
        return _with_source_path(slugged, blob, family)
    if family in FAMILY_URLS:
        return _with_source_path(FAMILY_URLS[family], blob, family)
    return None


def verified_source_competition_id(family: str, competition_id: str, source_name: str = "") -> Optional[str]:
    if family == "openligadb":
        return OPENLIGA_BY_COMP.get(competition_id)
    if family == "thesportsdb":
        mapped = TSDB_BY_COMP.get(competition_id)
        if mapped:
            return mapped
        found = re.search(r"\bid\s+(\d{3,6})\b", source_name or "", re.I)
        if found:
            return found.group(1)
    if family == "openfootball":
        return competition_id
    return None


BBC_COMPETITION_PATH = {
    "argentina-primera": "/sport/football/argentine-primera-division/scores-fixtures",
    "denmark-superliga": "/sport/football/danish-superliga/scores-fixtures",
    "sweden-allsvenskan": "/sport/football/swedish-allsvenskan/scores-fixtures",
    "mexico-liga-mx": "/sport/football/mexican-liga-mx/scores-fixtures",
    "australia-a-league": "/sport/football/australian-a-league/scores-fixtures",
    "australia-a-league-women": "/sport/football/womens-a-league/scores-fixtures",
    "usa-nwsl": "/sport/football/us-nwsl/scores-fixtures",
    "afc-champions-league": "/sport/football/afc-champions-league/scores-fixtures",
    "caf-champions-league": "/sport/football/caf-champions-league/scores-fixtures",
    "copa-libertadores": "/sport/football/copa-libertadores/scores-fixtures",
    "copa-sudamericana": "/sport/football/copa-sudamericana/scores-fixtures",
    "india-super-league": "/sport/football/indian-super-league/scores-fixtures",
    "czech-first-league": "/sport/football/czech-first-league/scores-fixtures",
    "france-top-14": "/sport/rugby-union/top-14/scores-fixtures",
    "france-pro-d2": "/sport/rugby-union/pro-d2/scores-fixtures",
    "super-rugby": "/sport/rugby-union/super-rugby/scores-fixtures",
    "super-league": "/sport/rugby-league/super-league/scores-fixtures",
    "nrl": "/sport/rugby-league/nrl/scores-fixtures",
    "atp-tour": "/sport/tennis",
    "wta-tour": "/sport/tennis",
    "bha-meetings": "/sport/horse-racing/results",
    "gbgb-meetings": "/sport/horse-racing",
    "wst-events": "/sport/snooker",
    "world-netball": "/sport/netball",
    "ssn-australia": "/sport/netball",
    "fis-disciplines": "/sport/winter-sports",
    "uci-calendar": "/sport/cycling",
    "wa-calendar": "/sport/athletics",
    "all-england-open": "/sport/badminton/live/cwy8nzqwkn9t",
    "tour-de-france": "/sport/cycling",
    "biathlon": "/sport/winter-sports",
    "formula-2": "/sport/formula1",
    "formula-3": "/sport/formula1",
}


def extra_config(family: str, competition_id: str) -> Dict:
    cfg: Dict = {}
    if family == "openfootball":
        paths = OPENFOOTBALL_BY_COMP.get(competition_id)
        if paths:
            cfg["paths"] = paths
    if family == "espn-html":
        from collector.adapters_espn import ESPN_HTML

        espn_url = ESPN_HTML.get(competition_id)
        if espn_url:
            cfg["url"] = espn_url
    if family == "liquipedia":
        from urllib.parse import quote

        wiki = LIQUIPEDIA_WIKI.get(competition_id)
        page = LIQUIPEDIA_PAGE.get(competition_id) or "Liquipedia:Matches"
        if wiki:
            cfg["wiki"] = wiki
            cfg["page"] = page
            cfg["url"] = (
                f"https://liquipedia.net/{wiki}/api.php?action=parse&page={quote(page, safe='')}&prop=text&format=json&redirects=1"
            )
    json_urls = FAMILY_PUBLIC_JSON.get(family)
    if json_urls:
        cfg["json_urls"] = list(json_urls)
    page = COMPETITION_PAGE_URLS.get((family, competition_id))
    if page:
        cfg["url"] = page
    if family == "omega-timing":
        cfg["source_type"] = "XML/HTML"
    if family == "fotmob":
        from collector.adapters_fotmob import FOTMOB_LEAGUES

        spec = FOTMOB_LEAGUES.get(competition_id) or {}
        if spec.get("ids"):
            cfg["fotmob_league_ids"] = list(spec["ids"])
            cfg["fotmob_league_name"] = spec.get("name")
        elif spec.get("id") is not None:
            cfg["fotmob_league_id"] = spec["id"]
            cfg["fotmob_league_name"] = spec.get("name")
        cfg["url"] = FAMILY_URLS["fotmob"]
    if family == "sofascore-web":
        from collector.adapters_sofascore import SOFA_COMPETITIONS

        spec = SOFA_COMPETITIONS.get(competition_id) or {}
        cfg["sofascore_sport"] = spec.get("sport")
        if spec.get("unique_id") is not None:
            cfg["sofascore_unique_id"] = spec["unique_id"]
        cfg["url"] = FAMILY_URLS["sofascore-web"]
    if family == "pga-graphql":
        cfg["tour_code"] = "S" if competition_id == "korn-ferry-tour" else "R"
        cfg["url"] = FAMILY_URLS["pga-graphql"]
        cfg["http_method"] = "POST"
    if family == "sportscore":
        from collector.adapters_sportscore import ATTRIBUTION, SPORTSCORE_COMPETITIONS

        spec = SPORTSCORE_COMPETITIONS.get(competition_id) or {}
        cfg["attribution"] = ATTRIBUTION
        cfg["sportscore_sport"] = spec.get("sport")
        cfg["sportscore_slugs"] = spec.get("slugs") or []
        cfg["url"] = FAMILY_URLS["sportscore"]
    if family == "wta-json":
        cfg["tournaments"] = []
        cfg["url"] = "https://api.wtatennis.com/tennis/tournaments"
    if family == "bbc-sport":
        path = BBC_COMPETITION_PATH.get(competition_id)
        if path:
            cfg["url"] = "https://www.bbc.com" + path
    if family == "sporting-events":
        from collector.adapters_sporting_events import ATTRIBUTION, COMPETITION_DATASET

        cfg["attribution"] = ATTRIBUTION
        cfg["dataset"] = COMPETITION_DATASET.get(competition_id)
        cfg["url"] = FAMILY_URLS["sporting-events"]
    if family == "worldcup26-api":
        from collector.adapters_worldcup26 import SLUG_BY_COMP

        cfg["league_slug"] = SLUG_BY_COMP.get(competition_id)
        cfg["url"] = FAMILY_URLS["worldcup26-api"]
    if family == "sportsrc":
        from collector.adapters_sportsrc import LEAGUE_BY_COMP

        cfg["league"] = LEAGUE_BY_COMP.get(competition_id)
        cfg["url"] = FAMILY_URLS["sportsrc"]
    if family == "soccerway":
        from collector.adapters_soccerway import BASE, COMPETITION_PATHS

        path = COMPETITION_PATHS.get(competition_id)
        if path:
            cfg["url"] = BASE + path.rstrip("/") + "/results/"
        else:
            cfg["url"] = FAMILY_URLS["soccerway"]
    if family == "aiff-web":
        from collector.adapters_aiff import COMPETITION_PAGES

        spec = COMPETITION_PAGES.get(competition_id) or {}
        cfg["url"] = spec.get("url") or FAMILY_URLS["aiff-web"]
    if family == "rte-rugby":
        from collector.adapters_rte_rugby import BASE, COMPETITION_SPECS

        spec = COMPETITION_SPECS.get(competition_id) or {}
        path = spec.get("path") or ""
        cfg["url"] = (BASE + path + "results/") if path else FAMILY_URLS["rte-rugby"]
        cfg["path"] = path
    if family == "super-rugby-html":
        cfg["url"] = FAMILY_URLS["super-rugby-html"]
    if family == "eliteprospects":
        from collector.adapters_eliteprospects import BASE, LEAGUE_SLUGS

        spec = LEAGUE_SLUGS.get(competition_id) or {}
        slug = spec.get("slug")
        cfg["url"] = f"{BASE}/league/{slug}/scores/2026-2027" if slug else FAMILY_URLS["eliteprospects"]
    if family == "volleyballworld":
        from collector.adapters_volleyballworld import BASE, SLUGS

        spec = SLUGS.get(competition_id) or {}
        slug = spec.get("slug")
        cfg["url"] = f"{BASE}/volleyball/competitions/{slug}/" if slug else FAMILY_URLS.get("volleyballworld") or BASE
    if family == "cev-competition-area":
        from collector.adapters_cev_competition_area import COMPETITION_IDS

        ids = COMPETITION_IDS.get(competition_id) or ["1572"]
        cfg["url"] = f"https://www-old.cev.eu/Competition-Area/CompetitionView.aspx?ID={ids[0]}"
        cfg["competition_area_id"] = ids[0]
    if family == "superliga-web" and competition_id == "serbia-superliga":
        cfg["html_urls"] = [
            "https://www.superliga.rs/sezona/raspored-i-rezultati/",
            "https://fss.rs/takmicenje/mozzart-bet-super-liga-srbije-26-27/?script=lat",
            "https://fss.rs/delegiranje/mozzart-bet-super-liga-srbije-26-27-delegiranje/?script=lat",
        ]
    if family == "tournamentsoftware":
        cfg.setdefault("url", "https://www.tournamentsoftware.com/sport/tournaments")
    if family == "rankedin":
        cfg.setdefault("url", "https://rankedin.com/en/tournament")
    if family == "click-tt":
        cfg.setdefault("url", "https://www.mytischtennis.de/clicktt/")
    shortcut = verified_source_competition_id(family, competition_id)
    if shortcut:
        cfg["source_competition_id"] = shortcut
    return cfg
