from collector.rich_closure import (
    choose_ibu_race,
    eurohockey_event_ids,
    eurohockey_is_rome,
    fis_sector_from_page,
    formula_e_rounds,
    match_fia_session,
    align_hockey_score,
    parse_altius_competition_matches,
    parse_altius_final_standings,
    parse_altius_index,
    parse_altius_standings,
    parse_altius_teams,
    parse_wec_session_results,
    parse_aquatics_discipline,
    parse_eurohockey_detail,
    parse_fia_classification,
    parse_fia_standings,
    parse_fis_results,
    parse_formula_e_race,
    parse_formula_e_standings,
    parse_ibu_classification,
    parse_leaguepedia_games,
    parse_leaguepedia_players,
    parse_ufc_results,
    parse_world_athletics,
    parse_wec_season_races,
    parse_wec_summary_id,
    parse_wst_frames,
    resolve_fis,
    resolve_wst_uuid,
    wec_prologue_sessions,
    wst_match_links,
)


F2_HTML = """
<table><tr class="table-header"><td>Pos</td><td>Nr</td><td>Driver</td><td>Points</td><td>Team</td>
<td>Time</td><td>Gap previous</td><td>Laps</td><td>Best lap time</td></tr>
<tr><td>1</td><td>2</td><td>J. Durksen PAR</td><td>10</td><td>Invicta Racing</td><td>39:09.726</td><td></td><td>21</td><td>1:30.100</td></tr>
<tr><td>2</td><td>5</td><td>N. Leon MEX</td><td>8</td><td>Campos Racing</td><td>39:11.865</td><td>2.139</td><td>21</td><td>1:30.400</td></tr>
</table>
"""

F2_STANDINGS = """
<table><tr><td>1</td><td>N. TSOLOV BUL</td><td>0 17</td><td>177 pts</td></tr>
<tr><td>1</td><td>Invicta Racing</td><td>300 pts</td></tr></table>
"""

FE_HTML = """
<table><tr class="resultsRow_resultsRow__eu9wl" data-testid="results-row-result">
<td>1</td><th><a href="/en/drivers/jake-dennis">Jake Dennis</a></th>
<td>ANDRETTI FORMULA E</td><td>1</td><td>59:23.013</td><td>25</td></tr>
<tr class="resultsRow_resultsRow__eu9wl" data-testid="results-row-result">
<td>2 Places gained</td><th><a href="/en/drivers/oliver-rowland">Oliver Rowland</a></th>
<td>NISSAN FORMULA E TEAM</td><td>13</td><td>+1.349</td><td>19</td></tr>
</table>
"""

CARGO_GAMES = {
    "cargoquery": [
        {
            "title": {
                "Team1": "T1",
                "Team2": "Top Esports",
                "Team1Side": "blue",
                "WinTeam": "T1",
                "Gamelength": "32:10",
                "GameId": "g1",
                "Team1Picks": "Azir,Orianna",
            }
        }
    ]
}

CARGO_PLAYERS = {
    "cargoquery": [
        {
            "title": {
                "Link": "Faker",
                "Team": "T1",
                "Champion": "Azir",
                "Kills": "4",
                "Deaths": "1",
                "Assists": "8",
                "CS": "280",
                "Gold": "14000",
                "DamageToChampions": "18000",
                "VisionScore": "30",
                "Side": "Blue",
            }
        }
    ]
}


def test_fia_classification_maps_official_columns():
    row = parse_fia_classification(F2_HTML)["classification"][0]
    assert row["position"] == "1"
    assert row["car"] == "2"
    assert row["name"] == "J. Durksen"
    assert row["team"] == "Invicta Racing"
    assert row["time"] == "39:09.726"
    assert row["fastest_lap"] == "1:30.100"
    assert parse_fia_classification(F2_HTML)["classification"][1]["gap"] == "2.139"


def test_fia_standings_keep_drivers_and_points():
    rows = parse_fia_standings(F2_STANDINGS)
    assert rows[0]["team"] == "N. TSOLOV"
    assert rows[0]["points"] == 177
    assert rows[1]["team"] == "Invicta Racing"
    assert rows[1]["points"] == 300


def test_formula_e_race_and_standings():
    race = parse_formula_e_race(FE_HTML)["classification"]
    assert race[0]["name"] == "Jake Dennis"
    assert race[0]["grid"] == "1"
    assert race[0]["points"] == "25"
    assert race[1]["position"] == 2
    assert race[1]["gap"] == "+1.349"
    table = parse_formula_e_standings(FE_HTML)
    assert table[0]["team"] == "Jake Dennis"
    assert table[0]["points"] == 25


def test_leaguepedia_games_and_players():
    game = parse_leaguepedia_games(CARGO_GAMES)[0]
    assert game["winner"] == "T1"
    assert game["duration"] == 1930
    assert game["blue"]["name"] == "T1"
    assert "Azir" in game["picks"]
    player = parse_leaguepedia_players(CARGO_PLAYERS)[0]
    assert player["hero"] == "Azir"
    assert player["kills"] == 4
    assert player["cs"] == "280"
    assert player["vision"] == "30"
    assert "GameId" not in player


def test_ibu_classification_includes_shooting_penalties():
    rows = parse_ibu_classification(
        {"Results": [{"Rank": "1", "Name": "Lou Jeanmonnot", "Nat": "FRA", "TotalTime": "30:12.4", "Behind": "0.0", "Shootings": "0+0+0+1", "ShootingTotal": "1"}]}
    )
    assert rows[0]["name"] == "Lou Jeanmonnot"
    assert rows[0]["shootings"] == "0+0+0+1"
    assert rows[0]["penalties"] == "1"
    assert "IBUId" not in rows[0]


def test_aquatics_match_row_is_a_final_score():
    parsed = parse_aquatics_discipline(
        {
            "Heats": [
                {
                    "Date": "2026-04-12",
                    "PhaseName": "Semifinals",
                    "Name": "Match 71",
                    "Results": [{"TeamHomeName": "France", "TeamAwayName": "Montenegro", "FinalScoreHome": 11, "FinalScoreAway": 15}],
                }
            ]
        },
        home="France",
        away="Montenegro",
        on_date="2026-04-12",
    )
    assert parsed["classification"][0]["points"] == 11
    assert parsed["classification"][1]["name"] == "Montenegro"
    assert parsed["classification"][0]["status"] == "Semifinals"


def test_altius_team_codes_resolve_real_names():
    html = """
    <table><tr><td><a href="/teams/8105">Scotland</a></td><td class="text-center">SCO</td></tr>
    <tr><td><a href="/teams/9">Türkiye</a></td><td class="text-center">TUR</td></tr>
    <tr><td>09 Jul 2026</td><td><a href="/matches/22123">SCO - TUR</a></td></tr></table>
    """
    teams = parse_altius_teams(html)
    assert teams["SCO"] == "Scotland"
    match = parse_altius_index(html, teams)[0]
    assert match["id"] == "22123"
    assert match["away"] == "Türkiye"


def test_wec_season_page_exposes_summary_id_from_the_race_link():
    season = '<a href="/en/race/official-prologue-imola-2026">Prologue</a><a href="/en/race/6-hours-of-imola-2026">Race</a>'
    slugs = [row["slug"] for row in parse_wec_season_races(season)]
    assert "6-hours-of-imola-2026" in slugs
    page = 'livestream 6-hours-of-imola <a href="/en/race/summary/4948">Classification</a> <a href="/en/race/summary/4951">Other</a>'
    assert parse_wec_summary_id(page, "6-hours-of-imola-2026") == "4948"
    replay = '<a href="/en/race/summary/4948">Replay</a><a href="/en/race/summary/4951">Replay</a>'
    assert parse_wec_summary_id(replay, "official-prologue-imola-2026") == ""


def test_fia_best_lap_is_the_lap_time_not_the_clock_column():
    html = """
    <table><tr><td>Pos</td><td>Driver</td><td>Best lap</td><td>Best lap lap</td><td>Best lap time</td><td>Speed trap</td></tr>
    <tr><td>1</td><td>J. Durksen PAR</td><td>1:32.386</td><td>20</td><td>15:11:04</td><td>278.2</td></tr>
    </table>
    """
    row = parse_fia_classification(html)["classification"][0]
    assert row["fastest_lap"] == "1:32.386"
    assert row["status"] == "lap 20"
    assert row["speed_trap"] == "278.2"
    links = ["/events/formula-2-championship/season-2026/melbourne/feature-race-classification"]
    assert match_fia_session("f2", "Melbourne Sprint Race Formula 2", "2026-03-06", links) == "f2:2026:melbourne:sprint"


def test_formula_e_round_date_comes_from_the_tile():
    html = (
        '<a href="/en/results-and-standings?season=12&amp;round=1-sao-paulo">Round 1 São Paulo 06 Dec 2025</a>'
        '<a href="/en/results-and-standings?season=12&amp;round=2-ciudad-de-mexico">Round 2 10 Jan 2026</a>'
    )
    rounds = formula_e_rounds(html)
    assert rounds[0]["date"] == "2025-12-06"
    assert rounds[1]["round"] == "2-ciudad-de-mexico"


FIS_ROW = """
<a href="/DB/general/results.html?sectorcode=CC&raceid=1">Cross-Country</a>
<div>Final</div>
<a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?sectorcode=sb&amp;competitorid=137706">
  <div class="g-lg-1 justify-right bold">1</div>
  <div class="g-lg-1 gray">3</div>
  <div class="g-lg-2 gray">9055032</div>
  <div class="g-lg-10 justify-left bold">PAYER Sabine</div>
  <div class="g-lg-1 justify-left">1992</div>
  <span class="country__name-short">AUT</span>
  <div class="g-lg-2 justify-right blue bold">1:15.99</div>
  <div class="g-lg-2 justify-right">1000.00</div>
</a>
<a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?sectorcode=sb&amp;competitorid=2">
  <div class="g-lg-1 justify-right bold">2</div>
  <div class="g-lg-10 justify-left bold">BUCK Kaylie</div>
  <span class="country__name-short">CAN</span>
  <div class="g-lg-2 justify-right blue bold">1:17.35</div>
  <div class="g-lg-2 justify-right">800.00</div>
</a>
"""


def test_bare_fis_race_id_is_replaced_with_the_verified_sector_id():
    from datetime import datetime

    from collector.rich_public import ensure_rich_source_ids

    class Row:
        competition_id = "fis-disciplines"
        participants_json = '{"home": {"name": "Sabine Payer"}, "away": {"name": "FIS race"}}'
        start_time = datetime(2025, 12, 13)

    extra = {"source_event_ids": {"fis-web": "24016"}, "closure_id_rev": 2, "fis_rev": 3}
    ensure_rich_source_ids(Row(), extra)
    assert extra["source_event_ids"]["fis-web"] == "SB:2026:24016"
    extra = {
        "source_event_ids": {"fis-web": "sabine-payer-fis-race-2025-12-13T00:00:00Z"},
        "closure_id_rev": 2,
        "fis_rev": 6,
    }
    ensure_rich_source_ids(Row(), extra)
    assert extra["source_event_ids"]["fis-web"] == "SB:2026:24016"


def test_fis_sector_comes_from_the_result_page_not_a_generic_winter_code():
    assert fis_sector_from_page(FIS_ROW) == "SB"
    assert fis_sector_from_page(FIS_ROW) != "AL"
    assert resolve_fis("Sabine Payer FIS race", "2025-12-13") == "SB:2026:24016"
    assert resolve_fis("Sabine Payer FIS race", "2026-01-01") == ""
    rows = parse_fis_results(FIS_ROW)["classification"]
    assert rows[0]["name"] == "PAYER Sabine"
    assert rows[0]["nation"] == "AUT"
    assert rows[0]["time"] == "1:15.99"
    assert rows[0]["points"] == "1000.00"
    assert rows[0]["status"] == "Final"
    assert rows[1]["status"] == "Final"


def test_world_athletics_heat_and_final_use_the_official_result_document():
    html = """
    <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"calendarEventsResults":{"competition":{"name":"Australian Championships","startDate":"2026-04-09","endDate":"2026-04-12","venue":"Olympic Park, Sydney (AUS)"},"eventTitles":[{"events":[{"event":"Men's 1500 Metres","eventId":10229502,"races":[{"race":"Round 1 - Heat 1","results":[{"competitor":{"name":"Cameron MYERS"},"mark":"3:39.69","nationality":"AUS","place":"1.","wind":null}]},{"race":"Final","results":[{"competitor":{"name":"Cameron MYERS"},"mark":"3:35.10","nationality":"AUS","place":"1.","wind":"+0.4"}]}]}]}]}}}}</script>
    """
    parsed = parse_world_athletics(html)
    rows = parsed["classification"]
    assert rows[0]["status"].startswith("Round 1 - Heat 1")
    assert rows[0]["mark"] == "3:39.69"
    assert rows[1]["status"] == "Final"
    assert rows[1]["wind"] == "+0.4"
    assert rows[1]["race"] == "Men's 1500 Metres"
    assert parsed["sport_detail"]["rounds"][1]["round"] == "Final"


def test_world_athletics_selected_event_keeps_semifinal_wind():
    html = """
    <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"calendarEventsResults":{"eventTitles":[{"events":[{"event":"Men's 100 Metres","eventId":10229630,"races":[{"race":"Semifinal heat 1","wind":"-0.2","results":[{"competitor":{"name":"Example Runner"},"mark":"10.01","nationality":"USA","place":"1."}]},{"race":"Final","wind":"-0.6","results":[{"competitor":{"name":"Example Runner"},"mark":"9.90","nationality":"USA","place":"1."}]}]}]}]}}}}</script>
    """
    parsed = parse_world_athletics(html, event_id="10229630")
    winds = [row["wind"] for row in parsed["classification"]]
    assert winds == ["-0.2", "-0.6"]


def test_wst_uuid_crosswalk_and_frame_scores():
    listing = '<a href="/match-centre/11111111-2222-3333-4444-555555555555">Judd Trump Ronnie O\'Sullivan 2026-01-18</a>'
    links = wst_match_links(listing)
    assert resolve_wst_uuid(links, "Judd Trump", "Ronnie O'Sullivan", "2026-01-18") == "11111111-2222-3333-4444-555555555555"
    frames = parse_wst_frames("<table><tr><td>1</td><td>78</td><td>0</td><td>78</td></tr><tr><td>2</td><td>64</td><td>55</td></tr></table>")
    assert frames["sport_detail"]["games"][0]["home"] == 78
    assert frames["sport_detail"]["games"][0]["away"] == 0
    assert frames["sport_detail"]["games"][1]["name"] == "Frame 2"


def test_ufc_method_round_and_time():
    html = """
    <p>Song Yadong defeated Umar Nurmagomedov by KO (right uppercut) at 1:48 of Round 2</p>
    <p>Sumudaerji defeated Alex Perez by unanimous decision (29-28, 29-28, 29-28)</p>
    """
    rows = parse_ufc_results(html)["classification"]
    assert rows[0]["name"] == "Song Yadong"
    assert rows[0]["team"] == "Umar Nurmagomedov"
    assert rows[0]["status"] == "KO"
    assert rows[0]["mark"] == "right uppercut"
    assert rows[0]["time"] == "1:48"
    assert rows[0]["position"] == 2
    assert "29-28" in rows[1]["status"]
    paris = """
    Salahdine Parnasse defeats Dan Hooker by TKO, Round 1, 2:25
    Losene Keita defeats Muhammad Naimov by KO, Round 1, 2:54
    Daniil Donchenko defeats Punahele Soriano by Unanimous Decision (30-27, 30-27, 29-28)
    """
    paris_rows = parse_ufc_results(paris)["classification"]
    assert paris_rows[0]["name"] == "Salahdine Parnasse"
    assert paris_rows[0]["status"] == "TKO"
    assert paris_rows[0]["position"] == 1
    assert paris_rows[0]["time"] == "2:25"
    assert "30-27" in paris_rows[2]["status"]
    assert paris_rows[2].get("time") in (None, "")


def test_ufc_parser_rejects_promo_text_as_fighters():
    html = """
    <p>Payton Talbott Free Fight Full Fight defeats Raul Rosas Jr. by KO, Round 1, 2:54</p>
    <p>Barcelos Live now Stories Crypto.com UFC defeats Van by TKO, Round 2, 1:10</p>
    <p>Raoni Barcelos defeats Raul Rosas Jr. by Unanimous Decision (30-27, 30-27, 29-28)</p>
    """
    rows = parse_ufc_results(html)["classification"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Raoni Barcelos"
    assert rows[0]["team"] == "Raul Rosas Jr."


def test_eurohockey_rome_identity_and_standings():
    page = """
    <a href="/calendar/event?id=c4d5b17a-29e1-4398-9bb0-72551b896742">EuroHockey Championship Qualifier I Men 2026 Rome</a>
    <p>Teams Croatia Czechia Italy Portugal Scotland Switzerland Türkiye Ukraine</p>
    <table><tr><td>1</td><td>Scotland</td><td>9</td></tr><tr><td>2</td><td>Croatia</td><td>6</td></tr></table>
    <p>Scotland 3 FT 1 Italy</p>
    """
    assert eurohockey_event_ids(page) == ["c4d5b17a-29e1-4398-9bb0-72551b896742"]
    assert eurohockey_is_rome(page)
    rows = parse_altius_standings(page)
    assert rows[0]["team"] == "Scotland"
    assert rows[0]["points"] == 9
    detail = parse_eurohockey_detail(page)
    assert detail["classification"][0]["name"] == "Scotland"
    assert detail["classification"][0]["team"] == "Italy"


def test_wec_prologue_results_are_session_controls_not_another_race_summary():
    html = '''
    <a data-live-id-param="8123" class="btn"> Results </a>
    <a data-live-id-param="8124" class="btn"> Results </a>
    <a href="/en/race/summary/4948">Replay</a>
    '''
    assert wec_prologue_sessions(html) == {"morning": "8123", "afternoon": "8124"}
    assert parse_wec_summary_id(html, "official-prologue-imola-2026") == ""
    assert wec_prologue_sessions(html)["morning"] != wec_prologue_sessions(html)["afternoon"]
    assert parse_wec_session_results("<div>Results available soon</div>") == {}
    table = "<table><tr><td>1</td><td>50</td><td>FERRARI AF CORSE</td><td>1:31.177</td></tr></table>"
    assert parse_wec_session_results(table)["classification"][0]["time"] == "1:31.177"


ALTIUS_FIXTURE = """
<table>
<tr><td>02</td><td>9 Jul 2026 12:15</td><td><a href="/matches/21913">SCO v TUR</a></td><td>6 - 1</td></tr>
<tr><td>06</td><td>10 Jul 2026 18:30</td><td><a href="/matches/21917">POR v ITA (Semi-final)</a></td><td>2 - 5</td></tr>
</table>
"""


def test_eurohockey_order_insensitive_match_does_not_duplicate():
    matches = parse_altius_competition_matches(ALTIUS_FIXTURE)
    scotland = [row for row in matches if row["id"] == "21913"][0]
    italy = [row for row in matches if row["id"] == "21917"][0]
    assert scotland["home_score"] == 6 and scotland["away_score"] == 1
    assert italy["home_score"] == 2 and italy["away_score"] == 5
    assert align_hockey_score("Scotland", "Türkiye", scotland) == {"home": 6, "away": 1}
    assert align_hockey_score("Portugal", "Italy", italy) == {"home": 2, "away": 5}
    assert align_hockey_score("Italy", "Portugal", italy) == {"home": 5, "away": 2}
    standings = parse_altius_final_standings(
        "Team Code Final Standing Scotland SCO 1 Italy ITA 2 Croatia CRO 3 Portugal POR 4 "
        "Switzerland SUI 5 Czechia CZE 6 Türkiye TUR 7 Ukraine UKR 8"
    )
    assert [row["team"] for row in standings[:4]] == ["Scotland", "Italy", "Croatia", "Portugal"]
    assert "won" not in standings[0]


def test_ufc_official_article_creates_stable_bout_identities():
    from collector.adapters_final import ufc_bouts_from_article

    html = """
    <p>UFC Paris September 5, 2026</p>
    <p>Salahdine Parnasse defeats Dan Hooker by TKO, Round 1, 2:25</p>
    <p>Daniil Donchenko defeats Punahele Soriano by Unanimous Decision (30-27, 30-27, 29-28)</p>
    """
    first = ufc_bouts_from_article(html, "ufc-fight-night-september-05-2026")
    second = ufc_bouts_from_article(html, "ufc-fight-night-september-05-2026")
    assert len(first) == 2
    assert [row["source_event_id"] for row in first] == [row["source_event_id"] for row in second]
    assert first[0]["classification"][0]["status"] == "TKO"
    assert first[1]["classification"][0]["status"].startswith("Unanimous Decision")


def test_world_athletics_meet_keeps_official_event_identity():
    from collector.adapters_final import parse_wa_result_meet

    html = """
    <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"calendarEventsResults":{"competition":{"name":"World Athletics Ultimate Championship","startDate":"2026-09-11","venue":"Budapest"},"eventTitles":[{"events":[{"event":"Men's 100 Metres","eventId":10229630,"races":[]}]}]}}}}</script>
    """
    events = parse_wa_result_meet(html, "7212925")
    assert events[0]["source_event_id"] == "7212925:10229630"
    assert events[0]["home"]["name"] == "Men's 100 Metres"
    assert parse_wa_result_meet(html.replace("Ultimate Championship", "Diamond League"), "7212925") == []


def test_ibu_pursuit_uses_race_date_and_gender_not_the_city_label():
    races = [
        {
            "RaceId": "MEN",
            "Description": "Men's 12.5km Pursuit",
            "StartTime": "2026-01-18T14:00:00Z",
            "ResultStatus": "OFFICIAL",
        },
        {
            "RaceId": "WOMEN",
            "Description": "Women's 10km Pursuit",
            "ShortDescription": "Women's 10km Pursuit",
            "StartTime": "2026-01-18T11:30:00Z",
            "ResultStatus": "OFFICIAL",
            "Location": "Chiemgau Arena",
        },
    ]
    assert choose_ibu_race(races, "Lou Jeanmonnot Ruhpolding Women's Pursuit", "2026-01-18") == "WOMEN"
