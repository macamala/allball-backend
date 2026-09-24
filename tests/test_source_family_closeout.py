"""Frozen-fixture coverage for the source-family closeout. Does not weaken other tests."""

from collector.match import same_canonical_event
from collector.normalize import fingerprint
from collector.source_family_closeout import (
    TERMS_BLOCKED,
    bwf_tournament_links,
    cricket_series_event,
    empty_shell_has_no_results,
    ettu_competition_links,
    futsalplanet_event,
    collect_gri,
    gri_meeting_links,
    hrnsw_meeting_links,
    ibu_race_event,
    ingestion_allowed,
    kpga_position_is_numeric,
    nwpl_iframe_targets,
    parse_clicktt_schedule,
    parse_clicktt_standings,
    parse_futsalplanet_row,
    parse_gri_race_card,
    parse_ibu_cup_standings,
    parse_ibu_race_results,
    parse_kpga_leaderboard,
    parse_tournamentsoftware_matches,
    parse_wec_fastest_article,
    parse_wst_sitemap,
    collect_wst_tournament,
    wst_events_from_tournament,
    wst_match_centre_id,
    blast_cs_series,
    riot_match_event,
    rlcs_blast_mapping,
    same_upstream_not_independent,
    wa_discipline_events,
    attach_wa_classification,
    parse_wa_result_page,
    world_aquatics_shell_results,
)


IBU_RESULT = {
    "Results": [
        {
            "Rank": "1",
            "Leg": 0,
            "Name": "JEANMONNOT Lou",
            "Nat": "FRA",
            "TotalTime": "20:12.4",
            "Behind": "0.0",
            "Shootings": "0+0",
            "ShootingTotal": "0",
            "IBUId": "BTFRA22810199801",
        },
        {"Rank": "2", "Leg": 1, "Name": "LEG ROW", "Nat": "FRA", "TotalTime": "10:00.0"},
    ]
}


def test_ibu_race_identity_and_classification():
    comp = {
        "RaceId": "BT2526SWRLCP01SWSP",
        "Description": "Women's 7.5km Sprint",
        "StartTime": "2025-11-29T13:30:00Z",
        "Location": "Ostersund",
        "ResultStatus": "OFFICIAL",
    }
    event = ibu_race_event(comp, IBU_RESULT, event_meta={"EventId": "BT2526SWRLCP01", "SeasonId": "2526", "Description": "BMW IBU World Cup"})
    assert event["source_event_id"] == "BT2526SWRLCP01SWSP"
    assert event["classification"][0]["name"] == "JEANMONNOT Lou"
    assert event["classification"][0]["penalties"] == "0"
    assert all(row["name"] != "LEG ROW" for row in event["classification"])
    again = ibu_race_event(comp, IBU_RESULT, event_meta={"EventId": "BT2526SWRLCP01"})
    assert again["source_event_id"] == event["source_event_id"]
    rows = parse_ibu_race_results(IBU_RESULT)
    assert rows[0]["shootings"] == "0+0"
    standings = parse_ibu_cup_standings(
        {"CupId": "BT2526SWRLCP__SWTS", "CupName": "Women's World Cup Total Score", "Rows": [{"Rank": "1", "Name": "JEANMONNOT Lou", "Nat": "FRA", "Score": "1135"}]}
    )
    assert standings[0]["points"] == "1135"


def test_gri_href_orders_and_six_runner_identity():
    index = """
    <a href="/results/view-results/?date=22-Sep-2026&amp;track=TRL">Tralee</a>
    <a href="/results/view-results/?track=CML&amp;date=20-Sep-2026">Clonmel</a>
    <a href="/results/view-results/?date=16-Sep-2026&track=OLD">outside</a>
    """
    links = gri_meeting_links(index)
    assert [item["track"] for item in links] == ["TRL", "CML", "OLD"]
    assert "date=22-Sep-2026" in links[0]["url"] and "track=TRL" in links[0]["url"]
    assert "track=CML" in links[1]["url"]
    runners = [
        (1, 4, "KILLDUFF JOEY", "29.62", "7/2", "EvAw"),
        (2, 1, "SECOND DOG", "29.70", "4/1", "Rls"),
        (3, 2, "THIRD DOG", "29.80", "5/1", "Crd"),
        (4, 6, "FOURTH DOG", "29.90", "6/1", "Bmp"),
        (5, 3, "FIFTH DOG", "30.01", "8/1", "Wide"),
        (6, 5, "SIXTH DOG", "30.10", "10/1", "Fin"),
    ]
    rows = "".join(
        f"<tr><td>{pos}.</td><td><img alt=\"Trap {trap}\"></td>"
        f"<td><a href=\"/results/greyhound-search/greyhound-details/?gid={name.replace(' ', '%20')}\">{name}</a></td>"
        f"<td>{time}</td><td></td><td>Sand</td><td>{time}</td><td>{sp}</td><td>{comment}</td></tr>"
        for pos, trap, name, time, sp, comment in runners
    )
    card = (
        "<h4>Race 1 - Kingdom Greyhound Stadium 525 (Grade : A5) Flat 525</h4>"
        + rows
        + "<h4>Race 2 - The Barking Buzz App 525 (Grade : A4) Flat 525</h4>"
        + rows.replace("KILLDUFF JOEY", "LADY CASE").replace(">4<", ">5<", 1)
    )
    races = parse_gri_race_card(card, track="TRL", date_token="22-Sep-2026")
    again = parse_gri_race_card(card, track="TRL", date_token="22-Sep-2026")
    assert [race["source_event_id"] for race in races] == [
        "gri:TRL:2026-09-22:1",
        "gri:TRL:2026-09-22:2",
    ]
    assert [race["source_event_id"] for race in again] == [race["source_event_id"] for race in races]
    assert len({race["source_event_id"] for race in races + again}) == 2
    race_one = races[0]["classification"]
    assert len(race_one) == 6
    assert race_one[0]["name"] == "KILLDUFF JOEY"
    assert race_one[0]["trap"] == 4
    assert race_one[0]["time"] == "29.62"
    assert races[0]["grade"] == "A5"
    assert all(row.get("race") == 1 for row in race_one)
    assert races[1]["classification"][0]["name"] == "LADY CASE"

    fetched = []

    class _Page:
        ok = True
        payload = card

    def getter(url):
        fetched.append(url)
        return _Page()

    events = collect_gri(getter, index)
    assert all("16-Sep-2026" not in url for url in fetched)
    assert any("track=TRL" in url for url in fetched)
    assert {event["source_event_id"] for event in events} >= {"gri:TRL:2026-09-22:1", "gri:TRL:2026-09-22:2"}


def test_gri_two_races_stay_separate():
    html = """
    <a href="/results/view-results/?track=CML&amp;date=20-Sep-2026">card</a>
    <h4>Race 1 - The Talking Dogs A6 525 (Grade : A6) Flat 525</h4>
    <tr><td>1.</td><td><img alt="Trap 1"></td><td><a href="/results/greyhound-search/greyhound-details/?gid=CIRCUS%20BOY">CIRCUS BOY</a></td><td>29.72</td><td>Sand</td><td>29.72</td><td>2/1F</td><td>SlAw</td></tr>
    <h4>Race 2 - The Bet On The Tote A4 525</h4>
    <tr><td>1.</td><td><img alt="Trap 3"></td><td><a href="/results/greyhound-search/greyhound-details/?gid=OTHER%20DOG">OTHER DOG</a></td><td>29.10</td><td>Sand</td><td>29.10</td><td>5/2</td><td>Led</td></tr>
    """
    links = gri_meeting_links(html)
    assert links[0]["track"] == "CML"
    races = parse_gri_race_card(html, track="CML", date_token="20-Sep-2026")
    assert len(races) == 2
    assert races[0]["source_event_id"] != races[1]["source_event_id"]
    assert races[0]["race_number"] == 1
    assert races[1]["classification"][0]["name"] == "OTHER DOG"
    assert fingerprint({**races[0], "sport": "greyhound-racing", "competition_key": "ireland-gri-meetings"}) != fingerprint(
        {**races[1], "sport": "greyhound-racing", "competition_key": "ireland-gri-meetings"}
    )


def test_hrnsw_meeting_discovery_is_one_upstream():
    html = '<a href="http://www.harness.org.au/meeting-results.cfm?mc=PC220926&amp;ms=NSW">Penrith</a>'
    meetings = hrnsw_meeting_links(html)
    assert meetings[0]["meeting_code"] == "PC220926"
    assert meetings[0]["date"] == "2026-09-22"
    assert same_upstream_not_independent("hrnsw-web", "harness.org.au", derived_from="hrnsw-web")


def test_kpga_wd_rtd_dq_are_not_numeric_ranks():
    html = """
    <tr><td>1</td><td>Kim</td><td>KOR</td><td>-12</td><td>65</td></tr>
    <tr><td>WD</td><td>Park</td><td>KOR</td><td></td><td></td></tr>
    <tr><td>RTD</td><td>Lee</td><td>KOR</td><td></td><td></td></tr>
    <tr><td>DQ</td><td>Choi</td><td>KOR</td><td></td><td></td></tr>
    """
    rows = parse_kpga_leaderboard(html, game_id="202611000015M", year="2026")
    assert rows[0]["player"] == "Kim"
    assert kpga_position_is_numeric(rows[0])
    assert [row["position"] for row in rows[1:]] == ["WD", "RTD", "DQ"]
    assert not any(kpga_position_is_numeric(row) for row in rows[1:])


def test_tournamentsoftware_matches_do_not_collapse_across_tournaments():
    html = """
    <div data-match-id="m1" data-draw="MS" data-round="F" data-discipline="MS" data-time="2026-09-20T10:00:00Z" data-match-score="2-0">
      <span data-side="Player A"></span><span data-side="Player B"></span>
      <span data-game="21-15"></span>
    </div>
    """
    one = parse_tournamentsoftware_matches(html, tournament_id="5214", federation="bwf")
    two = parse_tournamentsoftware_matches(html, tournament_id="9999", federation="bwf")
    assert one[0]["source_event_id"] != two[0]["source_event_id"]
    assert one[0]["games"] == ["21-15"]
    page = '<a href="/tournament/5214/sands-china-ltd-macau-open-2026/results/">Results</a>'
    assert bwf_tournament_links(page)[0]["tournament_id"] == "5214"


def test_futsalplanet_keeps_et_and_penalties_apart():
    parsed = parse_futsalplanet_row(["01/02/2026", "Home FC", "Away FC", "FT 2-2", "ET 3-2", "PEN 4-3"])
    event = futsalplanet_event("Home FC", "Away FC", "2026-02-01T00:00:00Z", parsed, competition="Liga", season="2026", round_name="Final", source_id="fp:1")
    assert event["score"]["home"] == 2
    assert event["et_score"] == [3, 2]
    assert event["penalty_score"] == [4, 3]


def test_riot_games_do_not_share_canonical_identity():
    valorant = riot_match_event(game="valorant", league="vct", match_id="1", home="T1", away="GEN", home_score=2, away_score=1, when="2026-03-14T00:00:00Z", best_of=3)
    league = riot_match_event(game="league-of-legends", league="lck", match_id="1", home="T1", away="GEN", home_score=2, away_score=1, when="2026-03-14T00:00:00Z", best_of=3)
    assert valorant["game_id"] != league["game_id"]
    assert valorant["source_event_id"] != league["source_event_id"]
    assert not same_canonical_event(
        {**valorant, "sport": "valorant", "competition_key": "vct"},
        {**league, "sport": "league-of-legends", "competition_key": "lck"},
    )
    assert not ingestion_allowed("valorantesports-web")
    assert not ingestion_allowed("lolesports-web")


def test_rlcs_discovery_and_blast_are_one_chain():
    schedule = '<div data-rl-event="worlds-2026" data-blast="https://blast.tv/rl/worlds" data-name="World Championship"></div>'
    blast = '<div data-blast-event="worlds-2026" data-home="G2" data-away="BDS" data-score="4-2"></div>'
    events = rlcs_blast_mapping(schedule, blast)
    assert events[0]["score"]["home"] == 4
    assert events[0]["provenance"]["independent_providers"] == 1
    assert same_upstream_not_independent("rocketleague", "blast-rl", derived_from="rocketleague")


def test_blast_cs_series_and_map_scores():
    html = '<div data-series="s1" data-home="NAVI" data-away="FaZe" data-score="2-1" data-bo="3" data-maps="13-11,8-13,13-9"></div>'
    event = blast_cs_series(html)[0]
    assert event["best_of"] == 3
    assert len(event["maps"]) == 3


def test_wec_sessions_do_not_cross_attach_and_do_not_invent_times():
    am = """
    <h3>Fastest Times (AM Session)</h3>
    <p><u>Hypercar</u></p>
    <p>1. <strong>Antonio Giovinazzi</strong> Ferrari AF Corse<strong> 1m31.586s</strong><br>
    2. <strong>Robert Kubica</strong> AF Corse +<strong>0.097s</strong></p>
    <p><u>LMGT3</u></p>
    <p>1. <strong>Alessio Rovera</strong> VISTA AF Corse <strong>1m42.875s</strong></p>
    """
    pm = """
    <h3>Fastest Times (PM Session)</h3>
    <p><u>Hypercar</u></p>
    <p>1. <strong>Antonio Fuoco</strong> Ferrari AF Corse<strong> 1m31.177s</strong><br>
    2. <strong>Robert Kubica</strong> AF Corse <strong>+0.126s</strong></p>
    <p><u>LMGT3</u></p>
    <p>1. <strong>Mattia Drudi</strong> Heart of Racing Team <strong>1m42.698s</strong></p>
    """
    am_rows = parse_wec_fastest_article(am, session="morning", article_id="13197")
    pm_rows = parse_wec_fastest_article(pm, session="afternoon", article_id="13198")
    hyper = [row for row in am_rows["classification"] if row["class"] == "Hypercar"]
    assert hyper[0]["time"] == "1m31.586s" and hyper[0]["time_kind"] == "absolute"
    assert hyper[1]["time"] == "+0.097s" and hyper[1]["time_kind"] == "gap"
    assert [row["class"] for row in am_rows["classification"]].count("LMGT3") == 1
    assert parse_wec_fastest_article(am, session="afternoon", article_id="13197") == {}
    assert parse_wec_fastest_article(pm, session="morning", article_id="13198") == {}
    assert pm_rows["classification"][0]["name"] == "Antonio Fuoco"
    assert pm_rows["classification"][0]["time"] == "1m31.177s"
    assert am_rows["coverage"] == "official_top_10_summary"
    assert "1:31.586" not in hyper[0]["time"]


def test_world_athletics_persists_each_discipline_including_mens_100():
    html = """
    <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"calendarEventsResults":{"competition":{"name":"World Athletics Ultimate Championship","startDate":"2026-09-11","venue":"Budapest"},"eventTitles":[]}}}}</script>
    <option value="10229630">Men&#x27;s 100 Metres</option>
    <option value="10229631">Men&#x27;s 200 Metres</option>
    """
    events = wa_discipline_events(html, "7212925")
    ids = {event["source_event_id"] for event in events}
    assert "7212925:10229630" in ids
    assert "7212925:10229631" in ids
    assert len(ids) == 2
    again = wa_discipline_events(html, "7212925")
    assert {event["source_event_id"] for event in again} == ids


def _wa_page(event_id, discipline, per_result_wind, races):
    import json

    payload = {
        "props": {
            "pageProps": {
                "calendarEventsResults": {
                    "competition": {"name": "World Athletics Ultimate Championship"},
                    "eventTitles": [
                        {
                            "events": [
                                {
                                    "event": discipline,
                                    "eventId": event_id,
                                    "gender": "M",
                                    "perResultWind": per_result_wind,
                                    "races": races,
                                }
                            ]
                        }
                    ],
                }
            }
        }
    }
    return '<script id="__NEXT_DATA__">' + json.dumps(payload) + "</script>"


def test_world_athletics_rounds_wind_and_field_attempts():
    sprint = _wa_page(
        10229630,
        "Men's 100 Metres",
        False,
        [
            {
                "race": "Final",
                "raceNumber": 0,
                "wind": "-0.6",
                "results": [
                    {"competitor": {"name": "Kenneth BEDNAREK"}, "mark": "9.85", "nationality": "USA", "place": "1.", "wind": None, "remark": None},
                    {"competitor": {"name": "Oblique SEVILLE"}, "mark": "9.90", "nationality": "JAM", "place": "2.", "remark": None},
                ],
            },
            {
                "race": "Semifinal - Heat",
                "raceNumber": 1,
                "wind": "-0.2",
                "results": [
                    {"competitor": {"name": "Oblique SEVILLE"}, "mark": "9.90", "nationality": "JAM", "place": "1."},
                    {"competitor": {"name": "Gone DNS"}, "mark": "", "nationality": "USA", "place": "", "remark": "DNS"},
                ],
            },
            {
                "race": "Semifinal - Heat",
                "raceNumber": 2,
                "wind": "-0.7",
                "results": [
                    {"competitor": {"name": "Kenneth BEDNAREK"}, "mark": "9.94", "nationality": "USA", "place": "1."},
                ],
            },
        ],
    )
    parsed = parse_wa_result_page(sprint)
    again = parse_wa_result_page(sprint)
    assert parsed["event_id"] == "10229630"
    assert [item["round"] for item in parsed["rounds"]] == ["Final", "Semifinal", "Semifinal"]
    assert [item["heat"] for item in parsed["rounds"]] == [None, 1, 2]
    assert [item["wind"] for item in parsed["rounds"]] == ["-0.6", "-0.2", "-0.7"]
    final = [row for row in parsed["classification"] if row["round"] == "Final"]
    assert len(final) == 2
    assert final[0]["athlete"] == "Kenneth BEDNAREK"
    assert final[0]["wind"] == "-0.6"
    assert final[0]["wind_scope"] == "round"
    dns = [row for row in parsed["classification"] if row.get("status") == "DNS"]
    assert dns and dns[0]["position"] == "DNS"
    assert again["classification"] == parsed["classification"]
    event = {"source_event_id": "7212925:10229630", "discipline": "Men's 100 Metres"}
    attach_wa_classification(event, sprint)
    assert len(event["classification"]) == 5
    other = {"source_event_id": "7212925:999"}
    attach_wa_classification(other, sprint)
    assert "classification" not in other

    field = _wa_page(
        10229617,
        "Men's Long Jump",
        True,
        [
            {
                "race": "Final",
                "raceNumber": 0,
                "wind": None,
                "results": [
                    {"competitor": {"name": "Miltiadis TENTOGLOU"}, "mark": "8.35", "nationality": "GRE", "place": "1.", "wind": "0.0"},
                    {"competitor": {"name": "Second JUMPER"}, "mark": "8.10", "nationality": "USA", "place": "2.", "wind": "+0.4"},
                ],
            }
        ],
    )
    jumped = parse_wa_result_page(field)
    assert jumped["rounds"][0]["wind"] is None
    assert jumped["classification"][0]["wind"] == "0.0"
    assert jumped["classification"][0]["wind_scope"] == "result"
    assert jumped["classification"][1]["wind"] == "+0.4"


def test_wst_tournament_uuid_is_not_a_guessed_match_uuid():
    tournament_id = "9c9377a1-bcf0-46af-85cf-6f0d4b111f1c"
    match_id = "0186172e-007b-43f7-bdd2-f2725760e1d5"
    payload = {
        "data": {
            "id": tournament_id,
            "attributes": {
                "tournamentID": tournament_id,
                "name": "Q School 2026 - Event 1",
                "venue": "Sheffield",
                "matches": [
                    {
                        "matchID": match_id,
                        "tournamentID": tournament_id,
                        "homePlayerScore": 0,
                        "awayPlayerScore": 4,
                        "round": "Round 1",
                        "fixtureNumber": 5,
                        "status": "Completed",
                        "startDateTime": "2026-05-20 09:00:00",
                        "homePlayer": {"id": "p1", "firstName": "Robert", "surname": "Pope", "countryCode": "ENG"},
                        "awayPlayer": {"id": "p2", "firstName": "Mark", "surname": "Vincent", "nationality": {"code": "WAL"}},
                    },
                    {
                        "matchID": "not-a-uuid",
                        "tournamentID": tournament_id,
                        "homePlayer": {"firstName": "Guessed", "surname": "Player"},
                        "awayPlayer": {"firstName": "Other", "surname": "Player"},
                    },
                ],
            },
        }
    }
    frames = {
        match_id: {
            "data": {
                "attributes": {
                    "history": {
                        "matchData": {
                            "matchHistory": {
                                "frames": [
                                    {"frameNumber": 1, "homePlayerPoints": 16, "awayPlayerPoints": 81},
                                    {"frameNumber": 2, "homePlayerPoints": 0, "awayPlayerPoints": 70},
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
    assert wst_match_centre_id({"matchID": "911bebbd-650f-47bc-943c-ef40f13a26e6", "tournamentID": "other"}, tournament_id) == ""
    events = wst_events_from_tournament(payload, frame_payloads=frames)
    again = wst_events_from_tournament(payload, frame_payloads=frames)
    assert len(events) == 1
    assert events[0]["match_uuid"] == match_id
    assert events[0]["tournament_uuid"] == tournament_id
    assert events[0]["match_uuid"] != events[0]["tournament_uuid"]
    assert events[0]["score"]["home"] == 0 and events[0]["score"]["away"] == 4
    assert len(events[0]["classification"]) == 2
    assert events[0]["home"]["id"] == "p1"
    assert events[0]["home"]["country_id"] == "ENG"
    assert events[0]["away"]["country_id"] == "WAL"
    assert events[0]["source_event_id"] == again[0]["source_event_id"]
    assert collect_wst_tournament(lambda url: None, tournament_id="not-a-real-uuid") == []


def test_wst_sitemap_without_match_centre_is_not_discovery():
    xml = "<urlset><url><loc>https://www.wst.tv/matches</loc></url></urlset>"
    assert parse_wst_sitemap(xml)["discovery_proven"] is False


def test_world_aquatics_empty_shell_creates_nothing():
    assert world_aquatics_shell_results("<div>No Information yet to show</div>") == []
    assert empty_shell_has_no_results("<div>No Information yet to show</div>")


def test_usta_and_clicktt_stay_disabled():
    assert ingestion_allowed("usta-web") is False
    assert ingestion_allowed("usa-usta-meetings") is False
    assert "non-commercial" in TERMS_BLOCKED["usta-web"]
    assert ingestion_allowed("click-tt") is False
    standings = parse_clicktt_standings("<tr><td>1</td><td>Saarbrucken</td><td>10</td><td>8</td><td>1</td><td>1</td><td>17</td></tr>")
    assert standings[0]["team"] == "Saarbrucken"
    assert standings[0]["points"] == "17"
    matches = parse_clicktt_schedule("<tr><td>2026-09-20 18:00</td><td>Saarbrucken</td><td>Dusseldorf</td><td>3:1</td></tr>")
    assert matches[0]["score"]["home"] == 3


def test_cricket_series_identity_and_nwpl_iframe_provenance():
    first = cricket_series_event(series_id="ipl-2026", match_id="1", name="Match 1", when="2026-03-22T14:00:00Z", home="CSK", away="MI", venue="Chennai")
    second = cricket_series_event(series_id="ipl-2026", match_id="2", name="Match 2", when="2026-03-23T14:00:00Z", home="CSK", away="MI", venue="Chennai")
    assert first["source_event_id"] != second["source_event_id"]
    html = '<iframe src="https://total-waterpolo.com/nordic-league-men-2024-25/"></iframe>'
    assert nwpl_iframe_targets(html) == ["https://total-waterpolo.com/nordic-league-men-2024-25/"]
    assert same_upstream_not_independent("nordic-wpl-web", "total-waterpolo", derived_from="nordic-wpl-web")


def test_ettu_discovery_reads_official_results_links():
    html = """
    <h2>2026 European Youth Championships</h2>
    <a href="https://www.ettu.tv/events/133/14/1/5/5"><span>Results</span></a>
    <h2>2026 European U21 Championships</h2>
    <a href="https://www.ettu.tv/events/122/9/1/5/5"><span>Results</span></a>
    """
    links = ettu_competition_links(html)
    assert len(links) == 2
    assert links[0]["results_url"].startswith("https://www.ettu.tv/")
