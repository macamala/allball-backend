from collector.adapters import FetchRequest, FetchResult
from collector.adapters_feeds import FIFA_RESULT_TYPE, FifaFootballAdapter, PULSELIVE_COMP_TOKENS, WorldRugbyAdapter
from collector.verification_ledger import recompute_ledger
from collector.zero_event_closeout import (
    dedupe_atp_matches,
    parse_atp_results,
    parse_caf_matches,
    parse_cdl_matches,
    parse_ehf_matches,
    parse_nascar_results,
    parse_nz_iframe,
    parse_pll_schedule,
    parse_pll_standings,
    parse_vnl_match,
    zero_event_collectors,
    tennis_identity,
)


CDL_HTML = """
{"status":"COMPLETED","statusText":"Watch Match VOD","link":"https://callofdutyleague.com/en-us/match/12905","date":{"startTime":1784228400,"startDate":1784228400},"competitors":[{"longName":"Paris Gentle Mates","shortName":"PAR","score":3},{"longName":"Toronto KOI","shortName":"TOR","score":0}]}
{"status":"COMPLETED","link":"https://valorantesports.com/match/9","date":{"startTime":1784228400},"competitors":[{"longName":"Sentinels","score":2},{"longName":"LOUD","score":1}]}
"""

PLL_HTML = """
<table><thead><tr><th aria-label="eastern">eastern</th></tr></thead><tbody>
<tr><td><a aria-label="Philadelphia Waterdogs" href="/teams/philadelphia-waterdogs"><span>Philadelphia Waterdogs</span></a></td><td>9</td><td>3</td><td>151</td><td>137</td><td>14</td></tr>
</tbody></table>
<table><thead><tr><th aria-label="western">western</th></tr></thead><tbody>
<tr><td><a aria-label="Utah Archers" href="/teams/utah-archers"><span>Utah Archers</span></a></td><td>7</td><td>5</td><td>142</td><td>130</td><td>12</td></tr>
</tbody></table>
"""


def test_cdl_keeps_call_of_duty_and_drops_other_games():
    events = parse_cdl_matches(CDL_HTML)
    assert len(events) == 1
    assert events[0]["game_id"] == "call-of-duty"
    assert events[0]["source_event_id"] == "cdl:12905"
    assert events[0]["round"] == "series"
    assert events[0]["score"] == {"home": 3, "away": 0}
    assert events[0]["home"]["name"] == "Paris Gentle Mates"


def test_atp_dedupes_same_players_and_day():
    incoming = parse_atp_results(
        {
            "matches": [
                {
                    "matchId": "m1",
                    "winner": {"name": "Jannik Sinner"},
                    "loser": {"name": "Carlos Alcaraz"},
                    "date": "2026-08-29T18:00:00Z",
                    "round": "Final",
                    "sets": ["6-4", "6-3"],
                    "winnerSets": 2,
                    "loserSets": 0,
                }
            ]
        }
    )
    existing = [{"home": {"name": "Carlos Alcaraz"}, "away": {"name": "Jannik Sinner"}, "start_time": "2026-08-29T20:00:00Z"}]
    assert tennis_identity(incoming[0]) == tennis_identity(existing[0])
    assert dedupe_atp_matches(incoming, existing) == []
    assert incoming[0]["source_event_id"].startswith("atp:6242:")
    assert incoming[0]["score"]["sets"] == ["6-4", "6-3"]


def test_fifa_calendar_keeps_identity_and_aet():
    row = {
        "IdMatch": "400021543",
        "MatchNumber": 104,
        "MatchStatus": 0,
        "ResultType": 3,
        "Date": "2026-07-19T00:00:00Z",
        "CompetitionName": [{"Description": "FIFA World Cup"}],
        "HomeTeamScore": 1,
        "AwayTeamScore": 0,
        "HomeTeamPenaltyScore": None,
        "AwayTeamPenaltyScore": None,
        "Home": {"IdTeam": "1", "TeamName": [{"Description": "Spain"}]},
        "Away": {"IdTeam": "2", "TeamName": [{"Description": "Argentina"}]},
    }
    adapter = FifaFootballAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload={"Results": []}))
    event = adapter._event(row)
    assert event["source_event_id"] == "400021543"
    assert event["score"]["home"] == 1
    assert event["score"]["away"] == 0
    assert event["result_type"] == "AET"
    assert FIFA_RESULT_TYPE[3] == "AET"
    pens = dict(row)
    pens["HomeTeamPenaltyScore"] = 4
    pens["AwayTeamPenaltyScore"] = 2
    pens["ResultType"] = 1
    decided = adapter._event(pens)
    assert decided["result_type"] == "PSO"
    assert decided["score"]["home_penalties"] == 4
    assert decided["score"]["home"] == 1


def test_fivb_keeps_set_scores():
    event = parse_vnl_match(
        {
            "matchId": "vnl-1",
            "homeTeam": {"name": "Poland"},
            "awayTeam": {"name": "Italy"},
            "homeSets": 3,
            "awaySets": 1,
            "sets": [{"home": 25, "away": 21}, {"home": 22, "away": 25}, {"home": 25, "away": 18}, {"home": 25, "away": 20}],
            "date": "2026-07-26T00:00:00Z",
            "competition": "Volleyball Nations League 2026",
        }
    )
    assert event["score"] == {"home": 3, "away": 1}
    assert event["sets"][0] == {"set": 1, "home": 25, "away": 21}
    assert event["source_event_id"] == "fivb:vnl-1"
    assert "Nations League" in event["competition"]


def test_rugby_final_uses_pacific_nations_cup_identity():
    assert "pacific nations cup" in PULSELIVE_COMP_TOKENS["internationals-rwc"]
    payload = {
        "content": [
            {
                "matchId": "1ab861c4-0bad-4711-aeba-b40e702ad048",
                "status": "C",
                "scores": [15, 20],
                "eventPhase": "Final",
                "teams": [{"id": "fij", "name": "Fiji"}, {"id": "jpn", "name": "Japan"}],
                "competition": "Pacific Nations Cup 2026",
                "time": {"millis": 1789812300000, "label": "2026-09-19"},
            },
            {
                "matchId": "club",
                "status": "C",
                "scores": [19, 47],
                "teams": [{"id": "reds", "name": "Queensland Reds"}, {"id": "tahs", "name": "NSW Waratahs"}],
                "competition": "Super Rugby Pacific",
                "time": {"label": "2026-09-19"},
            },
        ]
    }
    adapter = WorldRugbyAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    events = adapter.fetch(FetchRequest(capability="results", competition_id="internationals-rwc")).events
    assert len(events) == 1
    assert events[0]["home"]["name"] == "Fiji"
    assert events[0]["score"] == {"home": 15, "away": 20}
    assert events[0]["competition"] == "Pacific Nations Cup 2026"
    assert events[0]["round"] == "Final"
    assert "world cup" not in events[0]["competition"].lower()


def test_nascar_race_identity_is_one_event():
    events = parse_nascar_results(
        {
            "race": {"id": "bristol-2026-09-17", "name": "Bristol", "track": "Bristol", "date": "2026-09-17T23:00:00Z"},
            "results": [
                {"finish": 1, "driver": "Jake Garcia", "start": 4, "laps": 250, "laps_led": 104, "status": "Running", "points": 40},
                {"finish": 2, "driver": "Corey Heim", "laps": 250, "status": "Running"},
            ],
        },
        series="NASCAR Craftsman Truck Series",
        competition_id="nascar-truck",
    )
    assert len(events) == 1
    assert events[0]["source_event_id"] == "nascar:nascar-truck:bristol-2026-09-17"
    assert events[0]["winner"] == "Jake Garcia"
    assert len(events[0]["classification"]) == 2


def test_pga_shape_is_not_one_row_per_player():
    from collector.adapters_final18 import PgaGraphqlAdapter

    def poster(body):
        query = str(body.get("query") or "")
        if "leaderboardV3" in query:
            return FetchResult(
                ok=True,
                http_status=200,
                payload={
                    "data": {
                        "leaderboardV3": {
                            "players": [
                                {"player": {"id": "1", "displayName": "Jacob Bridgeman", "country": "USA"}, "scoringData": {"position": "1", "total": "-26", "thru": "F", "roundScores": [{"roundNumber": 1, "strokes": 66}, {"roundNumber": 4, "strokes": 61}]}},
                                {"player": {"id": "2", "displayName": "Other"}, "scoringData": {"position": "2", "total": "-20", "thru": "F"}},
                            ]
                        }
                    }
                },
            )
        return FetchResult(
            ok=True,
            http_status=200,
            payload={"data": {"completeSchedule": {"tournaments": [{"id": "R2026506", "tournamentName": "Biltmore Championship Asheville", "tournamentStatus": "COMPLETED", "startDate": "2026-09-17", "endDate": "2026-09-20"}]}}},
        )

    events = PgaGraphqlAdapter(poster=poster).fetch(FetchRequest(capability="snapshot", competition_id="pga-tour")).events
    assert len(events) == 1
    assert events[0]["home"]["name"] == "Biltmore Championship Asheville"
    assert len(events[0]["classification"]) == 2
    assert events[0]["classification"][0]["strokes"] == [66, 61]
    assert events[0]["start_time"] == "2026-09-17T00:00:00Z"
    from collector.adapters_final18 import _pga_start

    assert _pga_start(1789603200000) == "2026-09-17T00:00:00Z"


def test_pll_standings_and_caf_scores_and_nz_origin():
    match_html = r'{\"externalEventId\":\"317540992\",\"visitorScore\":9,\"homeScore\":5,\"eventStatus\":3,\"startTime\":1778284800,\"homeTeam\":{\"fullName\":\"Archers\",\"location\":\"Utah\"},\"awayTeam\":{\"fullName\":\"Waterdogs\",\"location\":\"Philadelphia\"}}'
    matches = parse_pll_schedule(match_html)
    assert matches[0]["source_event_id"] == "pll:317540992"
    assert matches[0]["home"]["name"] == "Utah Archers"
    assert matches[0]["score"]["away"] == 9
    rows = parse_pll_standings(PLL_HTML)
    assert rows[0]["team"] == "Philadelphia Waterdogs"
    assert rows[0]["won"] == 9 and rows[0]["lost"] == 3
    assert rows[1]["team"] == "Utah Archers"
    caf = parse_caf_matches(
        {
            "matches": [
                {
                    "date": "2026-01-18",
                    "stage": "Final",
                    "home": "Senegal",
                    "away": "Morocco",
                    "ftHome": 1,
                    "ftAway": 0,
                    "aetHome": 1,
                    "aetAway": 0,
                },
                {
                    "date": "2026-01-17",
                    "stage": "Third place",
                    "home": "Nigeria",
                    "away": "Egypt",
                    "ftHome": 0,
                    "ftAway": 0,
                    "penHome": 4,
                    "penAway": 2,
                },
            ]
        }
    )
    assert caf[0]["result_type"] == "AET"
    assert caf[0]["score"]["ft_home"] == 1
    assert caf[0]["source_event_id"].startswith("caf:afcon2025:2026-01-18:")
    assert caf[1]["result_type"] == "PSO"
    assert caf[1]["score"]["home_penalties"] == 4
    assert caf[1]["score"]["home"] == 0
    origin = parse_nz_iframe('<iframe src="https://comp.sportlomo.com/nz/national-league"></iframe><iframe src="https://www.googletagmanager.com/ns.html"></iframe>')
    assert origin["upstream_origin"] == "comp.sportlomo.com"
    ehf = parse_ehf_matches(
        [{"id": "f4", "homeTeam": {"name": "Barça"}, "awayTeam": {"name": "Füchse Berlin"}, "homeScore": 37, "awayScore": 34, "date": "2026-06-14T00:00:00Z", "phase": "Final", "halftime": {"home": 20, "away": 16}}]
    )
    assert ehf[0]["periods"][0] == {"label": "HT", "home": 20, "away": 16}
    assert ehf[0]["source_event_id"] == "ehf:f4"


def test_title_fights_migration_is_in_the_ledger():
    ledger = recompute_ledger({})
    row = next(item for item in ledger["rows"] if item["competition_key"] == "title-fights")
    assert row["blocker_code"] == "MODEL_SCOPE"


EHF_CLUB = """
<div class="caption-text">Finals</div>
<a class="table-row table-row--elimination" href="/men/2025-26/matches/details/202611020107004/Barca-FuchseBerlin/">
<span class="name">Bar&#xE7;a</span><span class="name">F&#xFC;chse Berlin</span>
<span class="date">Sun Jun 14, 2026</span><span class="time-and-location">18:00 Cologne</span>
<div class="match-results"><span>37</span><span>34</span></div>
</a>
<div class="caption-text">Semi-finals</div>
<a class="table-row table-row--elimination" href="/men/2025-26/matches/details/202611020107002/SCMagdeburg-FuchseBerlin/">
<span class="name">SC Magdeburg</span><span class="name">F&#xFC;chse Berlin</span>
<span class="date">Sat Jun 13, 2026</span><span class="time-and-location">15:00 Cologne</span>
<div class="match-results"><span>35</span><span>40</span></div>
</a>
"""

EHF_OTHER_CLUB = """
<div class="caption-text">Finals</div>
<a class="table-row table-row--elimination" href="/men/2025-26/matches/details/202611020107004/Barca-FuchseBerlin/">
<span class="name">Bar&#xE7;a</span><span class="name">F&#xFC;chse Berlin</span>
<span class="date">Sun Jun 14, 2026</span>
<div class="match-results"><span>37</span><span>34</span></div>
</a>
"""

NASCAR_HTML = """
<script>const weekendRaceData = {"race_name":"UNOH 250","race_date":"2026-09-17","race_season":2026,"track_name":"Bristol Motor Speedway","margin_of_victory":"1.305"};</script>
<div class="race-result" role="row"><div class="position" role="cell">1</div><div class="driver-name">Jake Garcia</div><div class="starting-pos" role="cell">12</div><div class="final-status" role="cell">Running</div><div class="laps-completed" role="cell">250</div><div class="laps-led" role="cell">104</div><div class="best-lap" role="cell">15.84</div><div class="points" role="cell">69</div></div>
<div class="race-result" role="row"><div class="position" role="cell">2</div><div class="driver-name">Bayley Currey</div><div class="starting-pos" role="cell">16</div><div class="final-status" role="cell">Running</div><div class="laps-completed" role="cell">250</div><div class="laps-led" role="cell">0</div><div class="best-lap" role="cell">15.98</div><div class="points" role="cell">37</div></div>
<div class="race-result" role="row"><div class="position" role="cell">3</div><div class="driver-name">Corey Heim</div><div class="starting-pos" role="cell">4</div><div class="final-status" role="cell">Running</div><div class="laps-completed" role="cell">250</div><div class="laps-led" role="cell">10</div><div class="best-lap" role="cell">15.90</div><div class="points" role="cell">34</div></div>
"""

ARCA_HTML = """
<h1 class="entry-title">Race results: Bush's Best 200 at Bristol Motor Speedway</h1>
<div class="article-date">September 17, 2026</div>
<table><tr><th>Pos.</th><th>No.</th><th>Name</th><th>Sponsor</th><th>Laps</th><th>Diff</th></tr>
<tr><td>1</td><td>28</td><td>Carson Brown*</td><td>DWC</td><td>200</td><td>—</td></tr>
<tr><td>2</td><td>77</td><td>Tristan McKee*</td><td>Freeway</td><td>200</td><td>2.056</td></tr>
<tr><td>3</td><td>17</td><td>Kaden Honeycutt</td><td>MMI</td><td>200</td><td>2.096</td></tr>
</table>
"""


def test_ehf_club_pages_dedupe_and_keep_half_time():
    from collector.zero_event_closeout import attach_ehf_halves, dedupe_ehf_matches, parse_ehf_club_html

    first = parse_ehf_club_html(EHF_CLUB)
    second = parse_ehf_club_html(EHF_OTHER_CLUB)
    merged = dedupe_ehf_matches(first + second)
    assert len(first) == 2
    assert len(merged) == 2
    final = next(row for row in merged if row["source_event_id"] == "ehf:202611020107004")
    attach_ehf_halves([final], "Barça 37:34 (20:16) Füchse Berlin")
    assert final["score"] == {"home": 37, "away": 34}
    assert final["periods"][0] == {"label": "HT", "home": 20, "away": 16}
    assert final["start_time"].startswith("2026-06-14")


def test_nascar_truck_finish_order_and_arca_table():
    from collector.zero_event_closeout import parse_arca_results_html, parse_nascar_live_html

    truck = parse_nascar_live_html(
        NASCAR_HTML,
        page_url="https://www.nascar.com/live-results/nascar-craftsman-truck-series/2026-unoh-250/",
        competition_id="nascar-truck",
        series="NASCAR Craftsman Truck Series",
    )
    assert len(truck) == 1
    assert truck[0]["season"] == "2026"
    assert [row["name"] for row in truck[0]["classification"]] == ["Jake Garcia", "Bayley Currey", "Corey Heim"]
    assert truck[0]["classification"][0]["best_lap"] == "15.84"
    assert truck[0]["classification"][0]["laps_led"] == "104"
    assert truck[0]["margin"] == "1.305"
    arca = parse_arca_results_html(
        ARCA_HTML,
        page_url="https://www.arcaracing.com/2026/09/17/race-results-bushs-best-200-bristol-motor-speedway/",
    )
    assert arca[0]["winner"] == "Carson Brown"
    assert arca[0]["classification"][1]["name"] == "Tristan McKee"
    assert arca[0]["classification"][1]["gap"] == "2.056"
    assert arca[0]["classification"][2]["car"] == "17"
    assert arca[0]["coverage"] == "full"


def test_vnl_sets_and_caf_penalties_and_nz_2025_final():
    from collector.zero_event_closeout import (
        nz_championship_has_completed_matches,
        parse_caf_semifinal_article,
        parse_nz_final_article,
        parse_nz_iframe,
        parse_vnl_article,
        parse_vnl_standings,
    )

    event = parse_vnl_article(
        "Iran and Japan /schedule/26487/ Japan celebrate a 3-2 (25-19, 25-19, 20-25, 23-25, 15-12) victory",
        page_url="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/schedule/26487/",
    )[0]
    assert event["source_event_id"] == "vnl:2026:men:26487"
    assert event["score"] == {"home": 3, "away": 2}
    assert [item["home"] for item in event["sets"]] == [25, 25, 20, 23, 15]
    assert event["coverage_kind"] == "official_summary"
    standings = parse_vnl_standings(
        '<td headers=rank>1<td class="vbw-o-table__cell team"><a alt=JPN>Japan</a>'
        '<td class="vbw-o-table__cell matchestotal advanced" headers="matches total2">12'
        '<td class="vbw-o-table__cell matcheswon basic">12'
        '<td class="vbw-o-table__cell matcheslost advanced">0'
        '<td class="vbw-o-table__cell set30result advanced">3'
        '<td class="vbw-o-table__cell set31result advanced">3'
        '<td class="vbw-o-table__cell set32result advanced">6'
        '<td class="vbw-o-table__cell set23result advanced">0'
        '<td class="vbw-o-table__cell set13result advanced">0'
        '<td class="vbw-o-table__cell set03result advanced">0'
        '<td class="vbw-o-table__cell matchpoints basic">30'
    )
    assert standings[0]["team"] == "Japan"
    assert standings[0]["points"] == 30
    caf = parse_caf_semifinal_article(
        "Morocco 0-0 Nigeria after extra time. Morocco win 4-2 on penalties. FULL-TIME – Senegal 1-0 Egypt",
        page_url="https://www.cafonline.com/afcon2025/news/semifinals/",
    )
    assert [row["source_event_id"] for row in caf] == [
        "caf:afcon2025:2026-01-14:morocco:nigeria:semifinal",
        "caf:afcon2025:2026-01-14:senegal:egypt:semifinal",
    ]
    assert caf[0]["result_type"] == "PSO"
    assert caf[0]["score"]["home_penalties"] == 4
    assert caf[0]["score"]["aet_home"] == 0
    assert caf[1]["score"]["ft_home"] == 1
    assert "2506823" not in caf[0]["source_event_id"]
    final = parse_nz_final_article(
        "In 2025, Auckland City FC pipped Wellington Olympic AFC on penalties 7-6 after a 2-2 draw after extra-time.",
        page_url="https://www.nzfootball.co.nz/newsarticle/163883",
    )[0]
    assert final["result_type"] == "PSO"
    assert final["score"]["aet_home"] == 2
    assert final["score"]["away_penalties"] == 7
    assert final["coverage_kind"] == "official_summary"
    assert nz_championship_has_completed_matches("2026-09-23") is False
    assert nz_championship_has_completed_matches("2026-09-26") is True
    iframe = parse_nz_iframe(
        '<iframe src="https://www.googletagmanager.com/ns.html"></iframe>'
        '<iframe src="https://apps.nzfootball.co.nz/all-national-league-results"></iframe>'
    )
    assert iframe["upstream_origin"] == "apps.nzfootball.co.nz"


def test_atp_is_permission_required_and_richer_event_wins():
    from collector.zero_event_closeout import choose_richer_event, collect_atp

    assert collect_atp(lambda url: "should-not-fetch")["events"] == []
    ledger = recompute_ledger({})
    row = next(item for item in ledger["rows"] if item["competition_key"] == "atp-tour")
    assert row["terms_status"] == "PERMISSION_REQUIRED"
    assert row["blocker_code"] == "PERMISSION"
    assert row["production_event_status"] != "PROVEN"
    assert "SportScore" in row["blocker_detail"]
    richer = choose_richer_event(
        {"id": "thin", "score": {"home": 19, "away": 17}},
        {"id": "rich", "score": {"home": 19, "away": 17}, "periods": {"home": [6, 2, 4, 7], "away": [4, 6, 3, 4]}},
    )
    assert richer["id"] == "rich"


def test_fifa_detail_keeps_registry_key_and_world_cup_name():
    from collector.competition_identity import correct_public_competition_id

    assert (
        correct_public_competition_id(
            stored_competition_id="fifa-connected-competitions",
            source_competition_name="FIFA World Cup",
            sport_id="football",
            source_family="fifa-digital",
        )
        == "fifa-connected-competitions"
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="fivb-competitions",
            source_competition_name="Volleyball Nations League 2026",
            sport_id="volleyball",
            source_family="fivb-web",
        )
        == "fivb-competitions"
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="africa-cup-of-nations",
            source_competition_name="TotalEnergies CAF AFCON Morocco 2025",
            sport_id="football",
            source_family="caf-web",
        )
        == "africa-cup-of-nations"
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="england-premier-league",
            source_competition_name="Nigerian Premier League",
            sport_id="football",
        )
        is None
    )




def test_zero_event_collectors_heartbeats_between_families(monkeypatch):
    import collector.zero_event_closeout as closeout

    calls = []

    def heartbeat():
        calls.append("pulse")

    empty = lambda *_args, **_kwargs: {"events": [], "standings": [], "note": "empty"}
    for name in (
        "collect_cdl",
        "collect_pll",
        "collect_atp",
        "collect_ehf",
        "collect_vnl",
        "collect_nascar",
        "collect_nz",
        "collect_caf",
    ):
        monkeypatch.setattr(closeout, name, empty)

    rows = zero_event_collectors(lambda _url: "", heartbeat=heartbeat)

    assert len(rows) == 9
    assert len(calls) == 18
