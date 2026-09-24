from collector.adapters_sites import events_for_host, parse_eurohandball


def test_parse_eurohandball_group_phase_results_and_fixtures():
    html = """
    <div class="matches">
      <span>09.09.2026</span> <span>18:45</span>
      <span>One Veszprém HC</span> VS <span>FC Porto</span>
      <strong>28 : 36</strong>

      <span>09.09.2026</span> <span>18:45</span>
      VS <span>One Veszprém HC</span> <span>FC Porto</span>
      <strong>28 : 36</strong>

      <span>16.09.2026</span> <span>20:45</span>
      <span>Füchse Berlin</span> VS <span>One Veszprém HC</span>
      <strong>:</strong>
    </div>
    """
    rows = parse_eurohandball(html)
    assert len(rows) == 2

    result = rows[0]
    assert result["home"]["name"] == "One Veszprém HC"
    assert result["away"]["name"] == "FC Porto"
    assert result["status"] == "finished"
    assert result["score"] == {"home": 28, "away": 36}
    assert result["start_time"] == "2026-09-09T18:45:00+02:00"

    fixture = rows[1]
    assert fixture["home"]["name"] == "Füchse Berlin"
    assert fixture["away"]["name"] == "One Veszprém HC"
    assert fixture["status"] == "scheduled"
    assert fixture["score"] == {"home": None, "away": None}
    assert fixture["start_time"] == "2026-09-16T20:45:00+02:00"


def test_eurohandball_host_routes_to_official_parser():
    html = """
    <div>10.09.2026 18:45 RK Partizan AdmiralBet VS Füchse Berlin 44 : 33</div>
    """
    rows = events_for_host(
        html,
        "https://old.eurohandball.com/ec/00-01/cl/men/2026-27/round/1/Group%2BPhase",
    )
    assert len(rows) == 1
    assert rows[0]["home"]["name"] == "RK Partizan AdmiralBet"
    assert rows[0]["away"]["name"] == "Füchse Berlin"
    assert rows[0]["score"] == {"home": 44, "away": 33}
