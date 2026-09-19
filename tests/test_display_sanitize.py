from collector.display import sanitize_participant_name


def test_placeholder_codes_become_human_or_tbd():
    assert sanitize_participant_name("Wsf1") == "Winner of SF1"
    assert sanitize_participant_name("Wqf2") == "Winner of QF2"
    assert sanitize_participant_name("Lsf1") == "Loser of SF1"
    assert sanitize_participant_name("TBD") == "TBD"
    assert sanitize_participant_name("Team TBD") == "TBD"
    assert sanitize_participant_name("Ilia Simakin") == "Ilia Simakin"
