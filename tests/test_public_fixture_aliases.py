from collector.participant_alias import names_equivalent
from collector.provider import _dedupe_public_fixture_rows


def _event(event_id, competition_key, competition, home, away, start="2026-09-23T20:00:00Z", country=None):
    return {
        "id": event_id,
        "sport": "football",
        "competition_key": competition_key,
        "competition": competition,
        "competition_name": competition,
        "home": {"name": home},
        "away": {"name": away},
        "start_time": start,
        "country_id": country,
        "status": "scheduled",
        "score": {"home": None, "away": None},
    }


def test_verified_cross_provider_club_aliases():
    assert names_equivalent("ADT de Tarma", "Asociación Deportiva Tarma")
    assert names_equivalent("Rionegro Águilas", "Águilas Doradas")


def test_public_fixture_dedupe_collapses_peru_alias():
    rows = [
        _event("fifa-peru", "football-per-liga-1", "Liga 1", "ADT de Tarma", "Cienciano", country="PER"),
        _event("fotmob-peru", "football-per-liga-1", "Liga 1", "Asociación Deportiva Tarma", "Cienciano", country="PER"),
    ]
    assert len(_dedupe_public_fixture_rows(rows, set())) == 1


def test_public_fixture_dedupe_collapses_colombia_historical_alias():
    rows = [
        _event("core-col", "colombia-primera-a", "Categoría Primera A", "América de Cali", "Rionegro Águilas", start="2026-09-24T00:30:00Z", country="COL"),
        _event("fm-col", "football-col-primera-a", "Primera A", "América de Cali", "Águilas Doradas", start="2026-09-24T00:30:00Z", country="COL"),
    ]
    out = _dedupe_public_fixture_rows(rows, {"colombia-primera-a"})
    assert len(out) == 1
    assert out[0]["competition_key"] == "colombia-primera-a"


def test_public_fixture_dedupe_collapses_womens_u20_country_alias_only_in_context():
    rows = [
        _event(
            "fifa-u20",
            "football-fifa-u-20-women-s-world-cup",
            "FIFA U-20 Women's World Cup",
            "DPR Korea",
            "Colombia",
            start="2026-09-23T16:30:00Z",
        ),
        _event(
            "fm-u20",
            "football-women-s-world-cup-u20",
            "Women's World Cup U20",
            "North Korea U20 (W)",
            "Colombia U20 (W)",
            start="2026-09-23T16:30:00Z",
        ),
    ]
    assert len(_dedupe_public_fixture_rows(rows, set())) == 1
