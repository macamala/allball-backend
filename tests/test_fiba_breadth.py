import json

from collector.fiba_breadth import (
    game_to_event,
    parse_event_index,
    parse_game_dicts,
)


def flight_html(payload):
    body = "a:" + json.dumps(payload, separators=(",", ":"))
    outer = json.dumps([1, body])
    return f"<script>self.__next_f.push({outer})</script>"


def test_fiba_event_index_discovers_public_events():
    html = flight_html({
        "events": [{
            "slug": "fiba-u18-afrobasket-2026",
            "fibaOfficialName": "FIBA U18 AfroBasket 2026",
            "eventDateStart": "2026-09-20T00:00:00Z",
            "eventDateEnd": "2026-09-30T00:00:00Z",
            "gender": "M",
            "fibaHostJson": [{"countryName": "Rwanda", "cities": [{"name": "Kigali"}]}],
        }]
    })
    rows = parse_event_index(html)
    assert len(rows) == 1
    assert rows[0]["slug"] == "fiba-u18-afrobasket-2026"
    assert rows[0]["name"] == "FIBA U18 AfroBasket 2026"
    assert rows[0]["country"] == "Rwanda"
    assert rows[0]["city"] == "Kigali"


def test_fiba_game_parser_and_event_shape_keep_provider_identity():
    game = {
        "gameId": 136817,
        "gameDateTime": "2026-09-25T18:30:00Z",
        "teamA": {"organisationId": 10, "code": "SRB", "officialName": "Serbia"},
        "teamB": {"organisationId": 20, "code": "ESP", "officialName": "Spain"},
        "teamAScore": 88,
        "teamBScore": 82,
        "gameStatisticStatusCode": "FINAL",
        "round": {"roundName": "Quarter-Finals"},
        "competition": {"officialName": "FIBA World Cup 2026", "fibaZone": "WORLD"},
    }
    html = flight_html({"games": [game]})
    parsed = parse_game_dicts(html)
    assert [str(row["gameId"]) for row in parsed] == ["136817"]

    event = game_to_event(
        parsed[0],
        {
            "slug": "fiba-basketball-world-cup-2026",
            "name": "FIBA World Cup 2026",
            "country": "",
            "city": "Doha",
            "gender": "M",
        },
    )
    assert event["id"] == "fiba:136817"
    assert event["sport"] == "basketball"
    assert event["event_family"] == "team_match"
    assert event["competition_key"] == "basketball-fiba-fiba-basketball-world-cup-2026"
    assert event["home"]["name"] == "Serbia"
    assert event["away"]["name"] == "Spain"
    assert event["status"] == "finished"
    assert event["score"] == {"home": 88, "away": 82}
    assert event["round"] == "Quarter-Finals"
    assert event["extra"]["source_event_ids"] == {"fiba-web": "136817"}


def test_fiba_scheduled_game_does_not_publish_zero_placeholders_as_score():
    event = game_to_event({
        "gameId": "200",
        "gameDateTime": "2026-09-26T10:00:00Z",
        "teamA": {"officialName": "Australia"},
        "teamB": {"officialName": "Brazil"},
        "teamAScore": 0,
        "teamBScore": 0,
        "competition": {"officialName": "FIBA Qualifiers"},
    })
    assert event["status"] == "scheduled"
    assert event["score"] == {"home": None, "away": None}



def test_fiba_game_parser_preserves_identity_artwork():
    event = game_to_event(
        {
            "gameId": "asset-1",
            "gameDateTime": "2026-09-25T10:00:00Z",
            "teamA": {
                "organisationId": "10",
                "officialName": "Serbia",
                "logoUrl": "https://cdn.example/serbia.svg",
                "countryCode": "SRB",
            },
            "teamB": {
                "organisationId": "20",
                "officialName": "Spain",
                "image": {"url": "https://cdn.example/spain.svg"},
                "countryCode": "ESP",
            },
            "competition": {
                "officialName": "FIBA Test Cup",
                "logo": "https://cdn.example/fiba.svg",
            },
        },
        {"slug": "fiba-test-cup", "name": "FIBA Test Cup"},
    )
    assert event["home"]["logo"] == "https://cdn.example/serbia.svg"
    assert event["home"]["country_id"] == "SRB"
    assert event["away"]["logo"] == "https://cdn.example/spain.svg"
    assert event["away"]["country_id"] == "ESP"
    assert event["competition_logo"] == "https://cdn.example/fiba.svg"
