"""Mapped family parsers: ESPN FITT, Liquipedia, Sackmann CSV, Nuxt."""

from collector.adapters import FetchRequest, FetchResult
from collector.adapters_csv import SackmannTennisAdapter, parse_sackmann_csv
from collector.adapters_espn import EspnScoreboardAdapter, parse_espn_scoreboard
from collector.adapters_wiki import LiquipediaAdapter
from collector.html_parse import parse_espnfitt, parse_liquipedia_html, parse_nuxt_data
from collector.http import CHALLENGE_MARKERS, _is_challenge


ESPN_FITT = """
<html><body>
<script>window['__espnfitt__'] = {"page":{"content":{"scoreboard":{"evts":[
  {"id":"401","date":"2026-09-18T00:20:00Z","completed":true,
   "competitors":[
     {"homeAway":"home","score":"24","displayName":"Baltimore Ravens"},
     {"homeAway":"away","score":"21","displayName":"Kansas City Chiefs"}
   ],"status":{"state":"post"}}
]}}}};</script>
</body></html>
"""

LIQ_HTML = """
<div class="match-info">
  <div class="match-info-header-opponent match-info-header-opponent-left">
    <span class="name"><a href="/counterstrike/NRG">NRG</a></span>
  </div>
  <div class="match-info-header-scoreholder-score">2</div>
  <div class="match-info-header-scoreholder-score">1</div>
  <div class="match-info-header-opponent">
    <span class="name"><a href="/counterstrike/G2">G2 Esports</a></span>
  </div>
</div>
"""

SACKMANN_CSV = """tourney_name,tourney_date,winner_name,loser_name,round,match_num
Australian Open,20240115,Jannik Sinner,Novak Djokovic,F,1
"""

NUXT_HTML = """
<html><body>
<script type="application/json" id="__NUXT_DATA__">
[{"games":[{"homeTeam":{"name":"Kiel"},"awayTeam":{"name":"Flensburg"},"startDate":"2026-09-18T18:00:00Z"}]}]
</script>
</body></html>
"""


def test_espn_fitt_scoreboard_events():
    events = parse_espnfitt(ESPN_FITT)
    assert events
    assert events[0]["home"]["name"] == "Baltimore Ravens"
    assert events[0]["away"]["name"] == "Kansas City Chiefs"
    adapter = EspnScoreboardAdapter(
        getter=lambda url: FetchResult(ok=True, http_status=200, payload=ESPN_FITT)
    )
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="nfl"))
    assert result.ok
    assert result.events[0]["home"]["name"] == "Baltimore Ravens"


def test_espn_site_payload_still_parses():
    payload = {
        "leagues": [{"name": "NFL"}],
        "events": [
            {
                "id": "401",
                "date": "2026-09-18T00:20:00Z",
                "competitions": [
                    {
                        "id": "401-1",
                        "competitors": [
                            {"homeAway": "home", "score": "24", "team": {"displayName": "Baltimore Ravens"}},
                            {"homeAway": "away", "score": "21", "team": {"displayName": "Kansas City Chiefs"}},
                        ],
                        "status": {"type": {"state": "post"}},
                    }
                ],
            }
        ],
    }
    events = parse_espn_scoreboard(payload)
    assert events[0]["home"]["name"] == "Baltimore Ravens"


def test_liquipedia_match_cards():
    events = parse_liquipedia_html(LIQ_HTML)
    assert events[0]["home"]["name"] == "NRG"
    adapter = LiquipediaAdapter(
        getter=lambda url: FetchResult(
            ok=True,
            http_status=200,
            payload={"parse": {"text": {"*": LIQ_HTML}}},
        )
    )
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="tier1"))
    assert result.events[0]["away"]["name"] == "G2 Esports"


def test_sackmann_csv_matches():
    events = parse_sackmann_csv(SACKMANN_CSV, "atp-tour")
    assert events[0]["home"]["name"] == "Jannik Sinner"
    adapter = SackmannTennisAdapter(
        text_getter=lambda url, **k: FetchResult(ok=True, http_status=200, payload=SACKMANN_CSV)
    )
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="atp-tour"))
    assert result.ok
    assert result.events


def test_nuxt_data_events():
    events = parse_nuxt_data(NUXT_HTML)
    assert events
    assert events[0]["home"]["name"] == "Kiel"


def test_recaptcha_script_is_not_a_challenge():
    body = b"<html><script src='https://www.google.com/recaptcha/api.js'></script><h1>Fixtures</h1></html>"
    assert not _is_challenge(200, body)
    assert b"captcha" not in CHALLENGE_MARKERS
    assert _is_challenge(200, b"Just a moment... cf-browser-verification")
