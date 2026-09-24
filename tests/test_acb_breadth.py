from collector.acb_breadth import normalize_acb_event
from collector.adapters_official import parse_acb


def test_acb_calendar_first_round_is_date_only_without_fake_time():
    html = """
    <h3>26 de septiembre de 2026</h3>
    <div class="RoundMatch roundMatch">
      <span class="teamName--fullName">Surne Bilbao</span>
      <span class="teamName--fullName">Kids&Us Manresa</span>
    </div></div></div>
    <div class="RoundMatch roundMatch">
      <span class="teamName--fullName">MoraBanc Andorra</span>
      <span class="teamName--fullName">Monbus Obradoiro</span>
    </div></div></div>
    <h3>27 de septiembre de 2026</h3>
    <div class="RoundMatch roundMatch">
      <span class="teamName--fullName">Real Madrid</span>
      <span class="teamName--fullName">Unicaja</span>
    </div></div></div>
    """
    rows = parse_acb(html)
    assert len(rows) == 3
    event = normalize_acb_event(rows[0])
    assert event["sport"] == "basketball"
    assert event["competition_key"] == "spain-acb"
    assert event["start_date"] == "2026-09-26"
    assert event["start_precision"] == "DATE_ONLY"
    assert event["start_time"].startswith("2026-09-26T12:00:00")
    assert event["home"]["name"] == "Surne Bilbao"
    assert event["away"]["name"] == "Kids&Us Manresa"


def test_acb_date_only_identity_is_stable():
    raw = {
        "home": {"name": "Real Madrid"},
        "away": {"name": "Unicaja"},
        "status": "scheduled",
        "score": {"home": None, "away": None},
        "start_time": "2026-09-27T00:00:00Z",
        "extra": {"competition": "Liga Endesa"},
    }
    first = normalize_acb_event(raw)
    second = normalize_acb_event(raw)
    assert first["source_event_id"] == second["source_event_id"]
    assert first["start_precision"] == "DATE_ONLY"
