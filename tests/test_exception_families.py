"""Recorded-fixture proofs for previously HEALTHY_EMPTY official families."""

from collector.adapters import FetchRequest, FetchResult
from collector.adapters_csv import SackmannTennisAdapter
from collector.adapters_generic import GenericHttpAdapter
from collector.html_parse import parse_html, walk_json_events


IBU_EVENTS = [
    {"EventId": "BT2526E1", "ShortDescription": "Oberhof", "StartDate": "2026-01-07T10:00:00Z"},
    {"EventId": "BT2526E2", "ShortDescription": "Ruhpolding", "StartDate": "2026-01-14T10:00:00Z"},
]

LIIGA_GAMES = [
    {"homeTeam": {"name": "HIFK"}, "awayTeam": {"name": "Tappara"}, "start": "2026-01-10T16:30:00Z"},
    {"homeTeam": {"name": "Ilves"}, "awayTeam": {"name": "Lukko"}, "start": "2026-01-11T16:30:00Z"},
]

SPORTING_LIFE = {
    "meetings": [
        {
            "name": "Ascot",
            "races": [{"raceNumber": 1, "course": "Ascot", "offTime": "2024-06-22T13:30:00Z"}],
        }
    ]
}

FUTBALNET_HTML = """
<html><body>
<table>
<tr><td>Slovan Bratislava</td><td>3-1</td><td>Spartak Trnava</td></tr>
<tr><td>DAC Dunajska Streda</td><td>2-0</td><td>MSK Zilina</td></tr>
</table>
</body></html>
"""

JSONLD_HTML = """
<html><script type="application/ld+json">
{"@type":"SportsEvent","name":"Racing 92 vs Stade Toulousain","homeTeam":{"name":"Racing 92"},"awayTeam":{"name":"Stade Toulousain"},"startDate":"2025-05-17T19:05:00Z"}
</script></html>
"""

SACKMANN_CSV = """tourney_name,tourney_date,winner_name,loser_name,round,match_num
Wimbledon,20240714,Carlos Alcaraz,Novak Djokovic,F,1
"""


def test_ibu_json_becomes_canonical_events():
    adapter = GenericHttpAdapter(
        getter=lambda url: FetchResult(ok=True, http_status=200, payload=IBU_EVENTS),
        text_getter=lambda url, timeout=None: FetchResult(ok=False, http_status=500),
    )
    result = adapter.fetch(
        FetchRequest(
            capability="snapshot",
            competition_id="biathlon",
            source_config={
                "url": "https://www.biathlonworld.com/calendar",
                "json_urls": ["https://www.biathlonresults.com/modules/sportapi/api/Events?SeasonId=2526"],
            },
            upstream_family="ibu-web",
        )
    )
    assert result.ok
    assert len(result.events) >= 2
    assert result.events[0]["home"]["name"] == "Oberhof"


def test_liiga_json_becomes_canonical_events():
    events = walk_json_events(LIIGA_GAMES)
    assert events
    assert events[0]["home"]["name"] == "HIFK"
    assert events[0]["away"]["name"] == "Tappara"


def test_event_quality_rejects_futsal_football_leak_and_national_team_as_league():
    from collector.event_quality import event_is_valid

    assert not event_is_valid(
        {"home": {"name": "FC Levadia Tallinn"}, "away": {"name": "Tammeka Tartu"}},
        sport_id="futsal",
        competition_id="fifa-futsal-when-listed",
    )
    assert not event_is_valid(
        {"home": {"name": "Serbia"}, "away": {"name": "Greece"}, "start_time": "2026-09-24"},
        sport_id="football",
        competition_id="serbia-superliga",
    )
    assert event_is_valid(
        {"home": {"name": "Crvena zvezda"}, "away": {"name": "Mačva"}, "start_time": "2026-07-17"},
        sport_id="football",
        competition_id="serbia-superliga",
    )


def test_rank_families_puts_working_ahead_of_empty():
    from collector.source_matrix import rank_families

    ranked = rank_families(
        [
            {"family": "official-empty", "status": "EMPTY_ARCHIVE", "priority": 1},
            {"family": "espn-html", "status": "WORKING", "priority": 4},
            {"family": "thesportsdb", "status": "WORKING", "priority": 1},
        ]
    )
    assert [row["family"] for row in ranked[:2]] == ["thesportsdb", "espn-html"]
    from collector.adapters_sportscore import ATTRIBUTION, SportScoreAdapter

    payload = {
        "matches": [
            {
                "home": "Birmingham Legion",
                "away": "New Mexico United",
                "home_score": "4",
                "away_score": "4",
                "status": "finished",
                "time": "2026-09-17T00:30:00+00:00",
                "competition": "USL Championship",
                "url": "/football/match/birmingham-legion-vs-new-mexico-united/",
            },
            {
                "home": "Other",
                "away": "Club",
                "home_score": "1",
                "away_score": "0",
                "status": "finished",
                "time": "2026-09-17T00:00:00+00:00",
                "competition": "Premier League",
                "url": "/football/match/other/",
            },
        ]
    }
    adapter = SportScoreAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="usa-usl-championship"))
    assert len(result.events) == 1
    assert result.events[0]["home"]["name"] == "Birmingham Legion"
    assert result.events[0]["extra"]["attribution"]["text"] == ATTRIBUTION["text"]
    assert result.events[0]["extra"]["attribution"]["url"] == "https://sportscore.com/"
    assert result.events[0]["extra"]["upstream_family"] == "thesports"


def test_wta_json_parses_2026_match():
    from collector.adapters_wta import WtaJsonAdapter

    payload = {
        "matches": [
            {
                "MatchID": "RS1",
                "MatchState": "F",
                "MatchTimeStamp": "2026-01-11T23:00:00+00:00",
                "PlayerNameFirstA": "Nikola",
                "PlayerNameLastA": "Bartunkova",
                "PlayerNameFirstB": "Selena",
                "PlayerNameLastB": "Janicijevic",
                "ScoreSet1A": "6",
                "ScoreSet1B": "3",
                "ScoreSet2A": "6",
                "ScoreSet2B": "3",
                "Venue": {"name": "Court 7"},
            }
        ]
    }
    adapter = WtaJsonAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="wta-tour"))
    assert result.events
    assert result.events[0]["home"]["name"] == "Nikola Bartunkova"
    assert result.events[0]["score"]["home"] == 2


def test_omega_athlete_xml():
    from collector.adapters_omega import parse_omega_xml

    xml = """
    <Results>
      <Event Name="Women 100 Butterfly" Date="2025-10-12">
        <Athlete Name="Gretchen Walsh" Rank="1" Time="54.43"/>
        <Athlete Name="Alexandra Perkins" Rank="2" Time="56.76"/>
      </Event>
    </Results>
    """
    events = parse_omega_xml(xml, "world-aquatics-meets")
    assert events[0]["home"]["name"] == "Gretchen Walsh"
    assert events[0]["away"]["name"] == "Women 100 Butterfly"


def test_sporting_life_races_become_canonical_events():
    events = walk_json_events(SPORTING_LIFE)
    assert events
    assert events[0]["away"]["name"] == "Ascot"


def test_futbalnet_table_scores():
    events = parse_html(FUTBALNET_HTML, "https://sportnet.sme.sk/futbalnet/l/nike-liga/vysledky/")
    assert len(events) >= 2
    names = {event["home"]["name"] for event in events}
    assert "Slovan Bratislava" in names


def test_jsonld_single_sports_event_is_enough():
    events = parse_html(JSONLD_HTML, "https://www.lnr.fr/calendrier")
    assert events
    assert events[0]["home"]["name"] == "Racing 92"


SOCCERWAY_HTML = """
<html><head><title>A-League Women results</title></head><body>
<script>
                data: `SA\u00f71\u00ac~ZA\u00f7AUSTRALIA: A-League Women\u00acZL\u00f7/australia/a-league-women/\u00ac~AA\u00f7x1\u00acAD\u00f71778931000\u00acAE\u00f7Melbourne City W\u00acAF\u00f7Wellington Phoenix W\u00acAG\u00f73\u00acAH\u00f71\u00acAC\u00f73`
</script>
</body></html>
"""

SUPERLIGA_HTML = """
<html><body>
<a href="/utakmica/1-kolo">
<div class="widget-single-match pt-3 pb-3">
<div class="match-date">17.07.2026.</div>
<div class="match-home text-end"> Crvena zvezda</div>
<div class="match-result text-center">5:0</div>
<div class="match-away text-start"> Mačva</div>
</div>
</a>
</body></html>
"""

SPORTNET_HTML = """
<html><title>Niké liga (2026/2027) - výsledky</title><body>
<p class="sc-13af45a1-0 sc-1a8c9693-4 fiyIXH feqZwg">ŠK Slovan Bratislava futbal</p>
<p class="sc-13af45a1-0 sc-1a8c9693-4 fiyIXH feqZwg">MŠK Žilina</p>
<p class="sc-13af45a1-0 sc-bd9bf7ce-2 fiyIXH inmneS">3</p>
<p class="sc-13af45a1-0 sc-bd9bf7ce-2 fiyIXH inmneS">3</p>
<p class="sc-13af45a1-2 izDkez">13.09. 19:00</p>
<p class="sc-13af45a1-4 gXnkGD">Koniec</p>
</body></html>
"""


def test_soccerway_embedded_feed_parses_requested_competition_only():
    from collector.adapters_soccerway import parse_soccerway_html

    events = parse_soccerway_html(
        SOCCERWAY_HTML,
        competition_id="australia-a-league-women",
        path_hint="/australia/a-league-women/",
    )
    assert events
    assert events[0]["home"]["name"] == "Melbourne City W"
    assert events[0]["away"]["name"] == "Wellington Phoenix W"
    assert events[0]["score"]["home"] == 3
    assert events[0]["status"] == "finished"


def test_superliga_odigrano_match_card():
    from collector.adapters_sites import parse_superliga

    events = parse_superliga(SUPERLIGA_HTML)
    assert events
    assert events[0]["home"]["name"] == "Crvena zvezda"
    assert events[0]["away"]["name"] == "Mačva"
    assert events[0]["score"]["home"] == 5
    assert str(events[0]["start_time"]).startswith("2026-07-17")


def test_sportnet_nike_liga_result_row():
    from collector.adapters_sites import parse_sportnet

    events = parse_sportnet(SPORTNET_HTML)
    assert events
    assert "Slovan" in events[0]["home"]["name"]
    assert "Žilina" in events[0]["away"]["name"]
    assert events[0]["score"] == {"home": 3, "away": 3}


def test_aiff_isl_fixtures_payload():
    from collector.adapters_aiff import parse_aiff_fixtures

    payload = {
        "fixtures": [
            {
                "id": "CMS1",
                "match_date": "2026-05-16",
                "time": "17:00",
                "team1_name": "Chennaiyin FC",
                "team2_name": "Bengaluru Football Club",
                "team1_score": 1,
                "team2_score": 2,
                "slug": "isl",
                "tournament_name": "Indian Super League 2025-26",
                "ft": True,
                "over": True,
            }
        ]
    }
    events = parse_aiff_fixtures(payload, competition_id="india-super-league", slug="isl")
    assert events[0]["home"]["name"] == "Chennaiyin FC"
    assert events[0]["score"]["away"] == 2


def test_sackmann_listed_file_is_working():
    adapter = SackmannTennisAdapter(
        text_getter=lambda url, timeout=None: FetchResult(ok=True, http_status=200, payload=SACKMANN_CSV)
        if "listed" in url
        else FetchResult(ok=False, http_status=404, error="http 404"),
        getter=lambda url: FetchResult(
            ok=True,
            http_status=200,
            payload=[{"name": "atp_matches_2024.csv", "download_url": "https://example.test/listed-atp.csv"}],
        )
        if "api.github.com" in url
        else FetchResult(ok=False, http_status=404),
    )
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="atp-tour", source_config={"url": "https://missing.csv"}))
    assert result.ok
    assert result.events[0]["home"]["name"] == "Carlos Alcaraz"


RTE_HTML = """
<html><body>
<h2 class="date">Sun 31 May 2026</h2>
<a class="match-item row status-finished" data-matchID="5917001" href="/sport/results/rugby/top-14/43093/report-5917001/">
<div class="small-12 columns match-header">
<span class="match-heading match-time-status">FT</span>
<span class="match-heading match-tournament">Top 14</span>
</div>
<div class="match-body">
<span class="team-name team-home  hide-for-small-only">ASM Clermont Auvergne</span>
<p class="match-main-info">13 - 41</p>
<span class="team-name team-away hide-for-small-only">Racing 92</span>
</div>
<div class="small-12 columns match-footer"><p>Stade Marcel-Michelin</p></div>
</a>
<h2 class="date">Sat 19 Sep 2026</h2>
<a class="match-item row status-notstarted" data-matchID="5917333">
<span class="match-heading match-tournament">Top 14</span>
<span class="team-name team-home  hide-for-small-only">Castres Olympique</span>
<p class="match-main-info">13:30</p>
<span class="team-name team-away hide-for-small-only">Toulon</span>
<div class="small-12 columns match-footer"><p>Stade Pierre Fabre</p></div>
</a>
</body></html>
"""

SUPER_RUGBY_PACK = """
<html><body>
<h1>Highlanders 25-23 Crusaders</h1>
<p>13/02/2026 Super Rugby Pacific Round 1</p>
</body></html>
"""

EP_HTML = """
<html><script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"games":[
  {"id":"g1","dateTime":"2026-09-17T15:30:00+0000","homeTeam":{"name":"TPS"},"visitingTeam":{"name":"Tappara"},"homeTeamScore":4,"visitingTeamScore":0,"league":{"name":"Liiga","slug":"liiga"}},
  {"id":"g2","date":"2026-09-16","homeTeam":{"name":"Karpat"},"awayTeam":{"name":"Ilves"},"homeTeamScore":3,"awayTeamScore":4,"overtime":true,"league":{"name":"Liiga","slug":"liiga"}}
]}}}
</script></html>
"""

VW_MATCH_HTML = """
<html><head><title>Asseco Resovia vs ZAKSA - PlusLiga | Volleyball World</title></head>
<body><p>Final 3-1</p><time datetime="2026-04-30T18:00">30 Apr 2026</time></body></html>
"""

CEV_HTML = """
<html><body>
<legend><b>Day 1</b> (From: <span>10/09/2026</span>)</legend>
<div id="ctl00_userControl_RADLIST_Legs_ctrl0_RADLIST_Matches_ctrl0_div_match">
<span id="x_Label2"><font>Italy</font></span>
<span id="x_Label4"><font>Sweden</font></span>
<span id="x_LB_SetCasa"><font>3</font></span>
<span id="x_LB_SetOspiti"><font>0</font></span>
<span id="x_LB_DataOra"><font>10/09/2026 21:05</font></span>
<span id="x_LB_Palasport"><font>Arena Piazza del Plebiscito, Naples</font></span>
<a href="MatchPage.aspx?mID=84508">MFA-01</a>
</div>
<div id="ctl00_userControl_RADLIST_Legs_ctrl2_RADLIST_Matches_ctrl0_div_match">
<span id="y_Label2"><font>Czechia</font></span>
<span id="y_Label4"><font>Greece</font></span>
<span id="y_LB_SetCasa">3</span>
<span id="y_LB_SetOspiti">1</span>
<span id="y_LB_DataOra">11/09/2026 16:00</span>
<span id="y_LB_Palasport">Palapanini, Modena</span>
<a href="MatchPage.aspx?mID=84509">MFA-02</a>
</div>
</body></html>
"""


def test_rte_top14_match_items():
    from collector.adapters_rte_rugby import parse_rte_rugby

    events = parse_rte_rugby(RTE_HTML, tokens=("top 14",))
    assert events
    assert events[0]["home"]["name"] == "ASM Clermont Auvergne"
    assert events[0]["away"]["name"] == "Racing 92"
    assert events[0]["score"] == {"home": 13, "away": 41}
    assert str(events[0]["start_time"]).startswith("2026-05-31")
    scheduled = [row for row in events if row["status"] == "scheduled"]
    assert scheduled
    assert scheduled[0]["home"]["name"] == "Castres Olympique"
    assert scheduled[0]["venue"] == "Stade Pierre Fabre"


def test_super_rugby_match_pack_scoreline():
    from collector.adapters_super_rugby_html import parse_super_rugby_pack

    events = parse_super_rugby_pack(SUPER_RUGBY_PACK, "https://super.rugby/superrugby/match-centre/match-packs/2026-srp-rd1/highlanders")
    assert events[0]["home"]["name"] == "Highlanders"
    assert events[0]["score"] == {"home": 25, "away": 23}
    assert str(events[0]["start_time"]).startswith("2026-02-13")
    pdf = "%PDF-1.4 " + "\x00".join(list("Highlanders 25-23 Crusaders 13/02/2026"))
    pdf_events = parse_super_rugby_pack(pdf, "https://super.rugby/pack.pdf")
    assert pdf_events[0]["score"] == {"home": 25, "away": 23}


def test_eliteprospects_liiga_games():
    from collector.adapters_eliteprospects import parse_eliteprospects_games

    events = parse_eliteprospects_games(EP_HTML, slug="liiga", names=("liiga",), season="2026-2027")
    assert events[0]["home"]["name"] == "TPS"
    assert events[0]["score"] == {"home": 4, "away": 0}
    ot = [row for row in events if row.get("ot")]
    assert ot and ot[0]["away"]["name"] == "Ilves"


def test_volleyballworld_plusliga_match_title():
    from collector.adapters_volleyballworld import parse_vw_match_page

    events = parse_vw_match_page(VW_MATCH_HTML, "https://en.volleyballworld.com/volleyball/competitions/plusliga/schedule/24786/", ("plusliga",))
    assert events[0]["home"]["name"] == "Asseco Resovia"
    assert "ZAKSA" in events[0]["away"]["name"]
    assert events[0]["score"] == {"home": 3, "away": 1}


def test_cev_competition_area_match_rows():
    from collector.adapters_cev_competition_area import parse_cev_competition_area

    events = parse_cev_competition_area(CEV_HTML, competition_id="cev-eurovolley-men")
    assert len(events) >= 2
    italy = events[0]
    assert italy["home"]["name"] == "Italy"
    assert italy["away"]["name"] == "Sweden"
    assert italy["score"] == {"home": 3, "away": 0}
    assert italy["id"] == "84508"
    assert str(italy["start_time"]).startswith("2026-09-10")
    assert "Naples" in (italy.get("venue") or "")


PROD2_HTML = """<score-slider :matches='[{"id":1,"status":"finished","hosting_club":{"name":"Aurillac"},"visiting_club":{"name":"CA Brive"},"score":[28,29],"timer":{"firstPeriodStartDate":"2026-09-12T18:30:00Z"},"week":{"name":"J4"}}]'></score-slider>"""

ACB_HTML = """
<h3>26 de septiembre de 2026</h3>
<div class="RoundMatch roundMatch">
<span class="teamName--fullName">Surne Bilbao</span>
<span class="teamName--fullName">Kids&amp;Us Manresa</span>
</div>
"""

FE_HTML = """
<div>16 Aug 2026 London</div>
<div class="driver-name">Taylor Barnard</div>
<div class="driver-name">Nyck de Vries</div>
"""

NP_HTML = """
<div class="team"><img alt="Adelaide Thunderbirds"></div>
<div class="score first"><span class="number">61</span></div>
<div class="score"><span class="number">40</span></div>
<div class="team"><img alt="Melbourne Vixens"></div>
<span data-time-to-local="1751616000"></span>
"""

FP_HTML = """
<tr><td>02/09/2026</td><td><b><span>Tubarão Futsal</span></b></td><td><b><span>Jaraguá Futsal</span></b></td>
<td><b><span>0</span></b></td><td><b><span>1</span></b></td></tr>
"""

GBGB_JSON = {
    "items": [
        {
            "trackName": "Newcastle",
            "raceNumber": 12,
            "raceDate": "17/09/2026",
            "raceTime": "21:04",
            "greyhoundName": "A Dog",
            "resultPosition": 1,
            "meetingId": 99,
        }
    ]
}


def test_remainder_official_parsers():
    from collector.adapters_official import parse_acb, parse_futsalplanet, parse_gbgb, parse_netballpass, parse_prod2, parse_formula_e

    prod2 = parse_prod2(PROD2_HTML)
    assert prod2[0]["home"]["name"] == "Aurillac"
    assert prod2[0]["score"] == {"home": 28, "away": 29}
    acb = parse_acb(ACB_HTML)
    assert acb[0]["home"]["name"] == "Surne Bilbao"
    assert "Manresa" in acb[0]["away"]["name"]
    fe = parse_formula_e(FE_HTML, "https://www.fiaformulae.com/en/results-and-standings?season=12&round=17-london")
    assert fe[0]["home"]["name"] == "Taylor Barnard"
    np = parse_netballpass(NP_HTML)
    assert np[0]["score"] == {"home": 61, "away": 40}
    fp = parse_futsalplanet(FP_HTML, "brazil-lnf")
    assert fp[0]["away"]["name"] == "Jaraguá Futsal"
    gbgb = parse_gbgb(GBGB_JSON)
    assert gbgb[0]["away"]["name"] == "Newcastle"
    assert str(gbgb[0]["start_time"]).startswith("2026-09-17")
    from collector.adapters_official import parse_fis
    fis = parse_fis('<span class="result-card__name">PAYER Sabine</span>')
    assert fis[0]["home"]["name"] == "Sabine Payer"


def test_closure_parsers():
    from collector.adapters_official import parse_eurohockey, parse_nll, parse_world_netball
    from collector.adapters_closure import parse_fcpro, parse_gri_meetings, parse_hbl_schedule, parse_pcs_result, parse_sportinglife_greyhounds, parse_sportinglife_race

    nll = parse_nll(
        """<h2>Saturday, May 2nd 2026</h2>
        <div>Halifax Thunderbirds</div><div>12 - 7</div><div>Georgia Swarm</div>
        <h2>Sunday, May 3rd 2026</h2>
        <div>Toronto Rock</div><div>6 - 11</div><div>San Diego Seals</div>"""
    )
    assert any(e["home"]["name"] == "Halifax Thunderbirds" and e["score"]["home"] == 12 for e in nll)
    wn = parse_world_netball(
        "<table><tr><td>Saturday 25th July (9am BST) Day 1 Pool B</td><td>NEW ZEALAND</td><td>74 – 44</td><td>SCOTLAND</td></tr></table>"
    )
    assert wn[0]["home"]["name"].lower().startswith("new zealand")
    assert wn[0]["score"] == {"home": 74, "away": 44}
    eh = parse_eurohockey("SUI Switzerland 2 FT 3 CRO Croatia 09/07/2026 - 08:00")
    assert eh[0]["home"]["name"] == "Switzerland"
    assert eh[0]["score"]["away"] == 3
    sl = parse_sportinglife_race(
        "<h1>Sky Sports Racing Virgin 512 Nursery</h1>16:20 Southwell 1 st 2 (11) Crowned 2 9-9",
        "https://www.sportinglife.com/racing/results/2026-09-17/southwell/939367/x",
    )
    assert sl[0]["away"]["name"] == "Southwell"
    gh = parse_sportinglife_greyhounds(
        "Yesterday's Results Nottingham Fast Results 11:25 Hove Fast Results 18:08 Newcastle Fast Results 18:37",
        "https://www.sportinglife.com/greyhounds/results/2026-09-17",
    )
    assert any(e["away"]["name"] == "Newcastle" for e in gh)
    hbl = parse_hbl_schedule(
        "Opel Handball-Bundesliga TVB Stuttgart vs Bergischer HC THW Kiel vs TBV Lemgo Lippe"
    )
    assert any(e["home"]["name"] == "TVB Stuttgart" for e in hbl)
    pcs = parse_pcs_result(
        "<h1>Grand Prix Cycliste de Montréal</h1><p>13 September 2026</p><table><tr><td>1</td><td>del Toro Isaac</td></tr></table>"
    )
    assert "del Toro" in pcs[0]["home"]["name"]
    fc = parse_fcpro("Bonanno 12-5 HHezerS")
    assert fc[0]["score"] == {"home": 12, "away": 5}
    gri = parse_gri_meetings("Enniscorthy 17 Sep 2026 View Results")
    assert gri[0]["home"]["name"] == "Enniscorthy"
    assert str(gri[0]["start_time"]).startswith("2026-09-17")
    from collector.adapters_final import parse_ibu_events_xml
    from collector.adapters_mass import (
        parse_aso_rankings,
        parse_diamond_league_pdf,
        parse_f2_standings,
        parse_gpcqm,
        parse_hrnsw_meetings,
        parse_lacrosse_canada_recap,
        parse_lnbp_wiki,
        parse_lnf_tabela,
        parse_scottish_hockey,
        parse_woodbine_recap,
    )

    f2 = parse_f2_standings(
        '<a href="/en/racing/2026/melbourne">Melbourne</a></div><div class="x">06 - 08 Mar</div>'
        '<a href="/en/racing/2026/spa-francorchamps">Spa-Francorchamps</a></div><div class="x">17 - 19 Jul</div>'
    )
    assert any(e["home"]["name"] == "Melbourne Sprint Race" for e in f2)
    assert any("Spa-Francorchamps Feature Race" in e["home"]["name"] for e in f2)
    aso = parse_aso_rankings(
        "<title>Official classifications of Tour de France 2026 - Stage 21</title>"
        '<a class="rankingTables__row__profile--name">T. POGACAR</a>'
        '<a class="rankingTables__row__profile--name">J. VINGEGAARD</a>'
        "<span>Stage 1</span>"
    )
    assert aso[0]["home"]["name"] == "T. POGACAR"
    hr = parse_hrnsw_meetings("PENRITH Night 17/09/2026 Results TABCORP PK MENANGLE Day 15/09/2026 Results")
    assert any(e["home"]["name"] == "Penrith" for e in hr)
    assert any(e["home"]["name"] == "Menangle" for e in hr)
    sh = parse_scottish_hockey("9th July 2026 Scotland men The 6-1 win against Turkiye gives the team momentum")
    assert sh[0]["home"]["name"] == "Scotland"
    assert sh[0]["score"]["home"] == 6

    ibu = parse_ibu_events_xml(
        """<ArrayOfSportEvent><SportEvent>
        <Description>BMW IBU World Cup Biathlon 2 Hochfilzen</Description>
        <Organizer>Hochfilzen</Organizer>
        <StartDate>2026-11-30T12:00:00Z</StartDate>
        <EventClassificationId>BTSWRLCP</EventClassificationId>
        </SportEvent></ArrayOfSportEvent>"""
    )
    ibu_json = parse_ibu_events_xml(
        '[{"Description":"BMW IBU World Cup Biathlon Hochfilzen","Organizer":"Hochfilzen","StartDate":"2026-11-30T12:00:00Z","EventClassificationId":"BTSWRLCP"}]'
    )
    assert ibu_json[0]["away"]["name"] == "Hochfilzen"
    gpcqm = parse_gpcqm("Isaac DEL TORO won Grand Prix Cycliste de Montreal in 5:13:16")
    assert gpcqm[0]["home"]["name"] == "Isaac Del Toro"
    lac = parse_lacrosse_canada_recap('Final Score: CAN 5 | JPN 4 (OT) datePublished":"2026-07-29')
    assert lac[0]["score"] == {"home": 5, "away": 4}
    wood = parse_woodbine_recap("Woodbine Mohawk Park Redland Rocket Man Simcoe September 12, 2026")
    assert wood[0]["home"]["name"] == "Woodbine Mohawk"
    lnf = parse_lnf_tabela("27/07/2026 segunda 18:00 São José SJF 2 X 5 VER RELATÓRIO Atlântico ATL Ginásio Amario")
    assert lnf[0]["home"]["name"] == "São José"
    assert lnf[0]["score"] == {"home": 2, "away": 5}
    lnbp = parse_lnbp_wiki("Fuerza Regia 105-94 Freseros Arena Mobil Sáb 15 ago 2026")
    assert lnbp[0]["home"]["name"] == "Fuerza Regia"
    assert lnbp[0]["score"]["home"] == 105
    dl = parse_diamond_league_pdf("1 BROMELL Trayvon USA 10 JUL 1995 8 0.131 9.91 SB Meeting de Paris")
    assert dl[0]["home"]["name"] == "Trayvon Bromell"
    from collector.adapters_mass import parse_equidia_arrivee
    eq = parse_equidia_arrivee("2026-09-17 - PARIS-VINCENNES FAWAZ MIL - Arrivé : 1er")
    assert eq[0]["home"]["name"] == "Paris Vincennes"
    from collector.adapters_mass import (
        parse_cetus_nwpl,
        parse_harrington_recap,
        parse_menangle_recap,
        parse_ttbl,
        parse_ttl_spielbericht,
        parse_wiki_all_england,
        parse_wiki_fifa_futsal,
        parse_wiki_indonesia_open,
        parse_wiki_lol_worlds,
        parse_wiki_uefa_futsal,
        parse_meadowlands_charts,
    )
    ttl = parse_ttl_spielbericht("Ajax Olympischer Punkte 3:7 02.09.2026")
    assert ttl[0]["score"] == {"home": 3, "away": 7}
    ttbl = parse_ttbl("Saarbrücken-TT 3 Post SV Mühlhausen 1 Fr., 21.08.2026")
    assert ttbl[0]["score"]["home"] == 3
    ae = parse_wiki_all_england("Lin Chun-yi Lakshya Sen 21 22 21-15")
    assert ae[0]["home"]["name"] == "Lin Chun-Yi"
    indo = parse_wiki_indonesia_open("Victor Lai Jonatan Christie 21-19 21-8")
    assert indo[0]["away"]["name"] == "Jonatan Christie"
    uefa = parse_wiki_uefa_futsal("Sporting CP Palma 2-0")
    assert uefa[0]["score"] == {"home": 2, "away": 0}
    worlds = parse_wiki_lol_worlds("T1 wins series 3-2 against KT Rolster")
    assert worlds[0]["away"]["name"] == "KT Rolster"
    fifa = parse_wiki_fifa_futsal("Futsal Brazil Argentina 2-1")
    assert fifa[0]["score"] == {"home": 2, "away": 1}
    from collector.adapters_mass import (
        parse_fifa_futsal_wc_recap,
        parse_nordic_final_eight,
        parse_ettu_youth_final,
        parse_rlcs_recap,
        parse_owcs_recap,
        parse_wa_water_polo,
        parse_pgl_bucharest,
        parse_kpga_leaderboard,
    )
    cbf = parse_fifa_futsal_wc_recap(
        "Copa do Mundo da FIFA de Futsal Uzbekistan 2024 Final Brasil 2 a 1 Argentina Ferrão Rafa Santos"
    )
    assert cbf and cbf[0]["score"] == {"home": 2, "away": 1}
    america = parse_fifa_futsal_wc_recap("Copa América de Futsal Brasil 2 a 1 Argentina amistoso")
    assert america == []
    nwpl = parse_nordic_final_eight("White Sharks Hannover16 Rapid Bucaresti14 Tenerife Echeyde17 Galatasaray SK20 2025-05-31")
    assert any(e["away"]["name"] == "Galatasaray" and e["score"]["away"] == 20 for e in nwpl)
    ettu = parse_ettu_youth_final("ETTU European Youth Championships Under 15 Girls France 3-2 Germany")
    assert ettu[0]["score"] == {"home": 3, "away": 2}
    rl = parse_rlcs_recap("RLCS Paris Major Grand Final Karmine Corp 4-1 Twisted Minds")
    assert rl[0]["score"] == {"home": 4, "away": 1}
    ow = parse_owcs_recap("OWCS Stage 1 NA Grand Final Dallas Fuel 4-1 Spacestation")
    assert ow[0]["score"] == {"home": 4, "away": 1}
    wa = parse_wa_water_polo("France 11-15 Montenegro Montenegro 19-17 Georgia")
    assert len(wa) == 2
    pgl = parse_pgl_bucharest("PGL Bucharest 2026 Grand Final FUT 3-1 Astralis")
    assert pgl[0]["home"]["name"] == "FUT"
    kpga = parse_kpga_leaderboard("KPGA leaderboard 1 KOR Jung Han-mil -12")
    assert kpga and "Jung" in kpga[0]["home"]["name"]
    from collector.adapters_mass import parse_wiki_rlcs, parse_wiki_vct, parse_ewc_owcs, parse_skidskytte_ruhpolding, parse_wiki_korean_tour
    rlcs = parse_wiki_rlcs("Rocket League Championship Series Paris Major Karmine Corp 4-1 Twisted Minds")
    assert rlcs[0]["score"] == {"home": 4, "away": 1}
    vct = parse_wiki_vct("2026 Masters Santiago Nongshim RedForce 3 0 Paper Rex")
    assert vct[0]["score"] == {"home": 3, "away": 0}
    ewc = parse_ewc_owcs("OWCS Midseason Championship ZETA DIVISION def. Twisted Minds 4-2")
    assert ewc[0]["score"] == {"home": 4, "away": 2}
    dttb = parse_ettu_youth_final("JEM-Team-Finals U15-Maedchen Finale Deutschland - Frankreich 2:3 Eva Lam")
    assert dttb and dttb[0]["score"] == {"home": 3, "away": 2}
    ski = parse_skidskytte_ruhpolding("Ruhpolding jaktstart Hanna Oberg slappte Lou Jeanmonnot forbi sig")
    assert ski and ski[0]["home"]["name"] == "Lou Jeanmonnot"
    ktour = parse_wiki_korean_tour(
        "2026 Korean Tour 19 Apr DB Insurance Promy Open Gangwon 1,000,000,000 Lee Sang-yeop (2) "
        "26 Apr Woori Financial Group Championship Gyeonggi 1,500,000,000 Chan Choi (1)"
    )
    assert ktour[0]["home"]["name"] == "Lee Sang-yeop"
    assert ktour[0]["away"]["name"] == "DB Insurance Promy Open"
    from collector.adapters_closure import parse_gri_derby
    from collector.adapters_mass import parse_owcs_world_finals, parse_wiki_irish_greyhound_derby, parse_wiki_owcs_world_finals
    derby_gri = parse_gri_derby(
        "<h4>Race 8 - 2025 BOYLE Sports Irish Greyhound Derby Final (Grade : AA0) Flat 550</h4>"
        '<tr><td>1.</td><td><img alt="Trap 5"></td>'
        '<td><a href="/results/greyhound-search/greyhound-details/?gid=CHEAP%20SANDWICHES">CHEAP SANDWICHES</a>'
        "<td>29.37</td></tr>"
        '<tr><td>2.</td><td><img alt="Trap 1"></td>'
        '<td><a href="/results/greyhound-search/greyhound-details/?gid=BAREFOOT%20ON%20SONG">BAREFOOT ON SONG</a>'
        "<td>29.58</td></tr> SPK_2025_09_27_08"
    )
    assert derby_gri and derby_gri[0]["home"]["name"] == "Cheap Sandwiches"
    assert str(derby_gri[0]["start_time"]).startswith("2025-09-27")
    derby_wiki = parse_wiki_irish_greyhound_derby(
        "2025 Irish Greyhound Derby Cheap Sandwiches — 1st — 29.37 Barefoot On Song — 2nd — 29.58 27 September 2025 Shelbourne Park"
    )
    assert derby_wiki[0]["home"]["name"] == "Cheap Sandwiches"
    owcs_liq = parse_owcs_world_finals(
        "Overwatch Champions Series 2025 World Finals Grand Final Twisted Minds 4-1 Al Qadsiah"
    )
    assert owcs_liq[0]["score"] == {"home": 4, "away": 1}
    mid = parse_owcs_world_finals("OWCS Midseason Championship ZETA DIVISION 4-2 Twisted Minds")
    assert mid == []
    owcs_wiki = parse_wiki_owcs_world_finals(
        "World Finals' results 2025 Stockholm Twisted Minds 4–1 Al Qadsiah 2024 Stockholm Team Falcons 4–1 Crazy Raccoon"
    )
    assert any(e["home"]["name"] == "Twisted Minds" and e["away"]["name"] == "Al Qadsiah" for e in owcs_wiki)
    cetus = parse_cetus_nwpl("05.12.2025 Cetus Espoo SK Neptun Stockholm 25 - 8")
    cetus = parse_cetus_nwpl("05.12.2025 Cetus Espoo SK Neptun Stockholm 25 - 8")
    assert cetus[0]["score"]["home"] == 25
    men = parse_menangle_recap("Club Menangle Verbici 1:59.6")
    assert men[0]["away"]["name"] == "Verbici"
    harr = parse_harrington_recap("Harrington Raceway Disturbed Hanover 1:53.1")
    assert harr[0]["away"]["name"] == "Disturbed Hanover"
    ml = parse_meadowlands_charts("Meadowlands Just My Mama 1:54.1 August 21, 2026")
    assert ml[0]["away"]["name"] == "Just My Mama"
    assert "Fawaz" in eq[0]["away"]["name"]



