from collector.asobal_breadth import current_round, parse_asobal_round


def test_asobal_current_round_parser_hides_scheduled_zero_score():
    html = """
    <h1>Partidos Jornada 3</h1>
    <ul>
      <li>
        <span>25/09/2026 - 19:00 ASOBAL TV + RTVEPlay + Eurosport</span>
        <a>ADE</a> 0 - 0 <a>CNG</a>
        <div>Palacio Municipal de los Deportes Urbano González</div>
        <div>Jordi Ausás Busquets | Miquel Florenza Virgili</div>
        <div>No ha comenzado |</div>
      </li>
      <li>
        <span>26/09/2026 - 16:00 ASOBAL TV</span>
        <a>CQN</a> 0 - 0 <a>SEV</a>
        <div>Pabellón Municipal El Sargal</div>
        <div>No ha comenzado |</div>
      </li>
    </ul>
    """
    assert current_round(html) == 3
    rows = parse_asobal_round(html)
    assert len(rows) == 2
    first = rows[0]
    assert first["competition_key"] == "spain-asobal"
    assert first["home"]["name"] == "ABANCA Ademar León"
    assert first["away"]["name"] == "Frigoríficos del Morrazo"
    assert first["start_time"] == "2026-09-25T17:00:00Z"
    assert first["status"] == "scheduled"
    assert first["score"] == {"home": None, "away": None}
    assert first["venue"] == "Palacio Municipal de los Deportes Urbano González"
    assert first["round"] == "Jornada 3"


def test_asobal_finished_match_keeps_official_score():
    html = """
    <h1>Partidos Jornada 1</h1>
    <li>
      11/09/2026 - 19:00 ASOBAL TV
      <a>LOG</a> 32 - 48 <a>BAR</a>
      <div>Palacio de los Deportes de la Rioja</div>
      <div>Partido finalizado |</div>
    </li>
    """
    row = parse_asobal_round(html)[0]
    assert row["status"] == "finished"
    assert row["score"] == {"home": 32, "away": 48}
    assert row["home"]["name"] == "Dicorpebal Logroño La Rioja"
    assert row["away"]["name"] == "Barça"
