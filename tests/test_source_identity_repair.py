from collector.source_identity_repair import incoming_source_identity_reject


def test_ufc_source_can_never_enter_dota_taxonomy():
    event = {
        "sport": "dota-2",
        "competition_key": "unknown",
        "source_family": "ufc-web",
        "home": {"name": "Jean Silva"},
        "away": {"name": "Trevor Peek"},
    }
    assert incoming_source_identity_reject(event) == "ufc_source_wrong_sport"


def test_source_scoped_page_text_is_rejected():
    cases = [
        (
            "golmates-web",
            "En vivo COQUIMBO Criciúma - Operário PR",
            "Liga 1 GARCILASO",
        ),
        (
            "ultimate-rugby",
            "Sep 24 Colomiers Auckland",
            "Manawatu at Eden Park 25th Sep 2026",
        ),
        (
            "lnh-web",
            "ProLigue - J03 ven. 18 sept. 20h30 Massy",
            "Dijon Suspense",
        ),
        (
            "concacaf-web",
            "Group Stage Caribbean Cup Violette AC",
            "Club Sando FC",
        ),
        (
            "dfb-web",
            "Zum Gewinnspiel U 21",
            "GEORGIEN",
        ),
    ]
    for family, home, away in cases:
        assert incoming_source_identity_reject(
            {
                "sport": "football",
                "source_family": family,
                "home": {"name": home},
                "away": {"name": away},
            }
        )


def test_legitimate_source_rows_are_not_rejected():
    assert incoming_source_identity_reject(
        {
            "sport": "rugby",
            "source_family": "ultimate-rugby",
            "home": {"name": "Tasman Mako"},
            "away": {"name": "Bay of Plenty"},
        }
    ) == ""
    assert incoming_source_identity_reject(
        {
            "sport": "handball",
            "source_family": "lnh-web",
            "home": {"name": "Cesson Rennes MHB"},
            "away": {"name": "PAUC Handball"},
        }
    ) == ""
