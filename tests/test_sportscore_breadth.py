from collector.competition_identity import correct_public_competition_id
from collector.sportscore_crosswalk import source_native_identity


def test_sportscore_source_native_tennis_identity_is_stable():
    row = {
        "competition": "ATP Hangzhou, China Men Singles",
        "competition_logo": "https://example.test/tournament/123.png",
    }
    first = source_native_identity("tennis", row)
    second = source_native_identity("tennis", dict(row))
    assert first == second
    competition_id, name, _source_identity = first
    assert competition_id.startswith("tennis-ss-")
    assert name == "ATP Hangzhou, China Men Singles"
    assert (
        correct_public_competition_id(
            stored_competition_id=competition_id,
            source_competition_name=name,
            sport_id="tennis",
            source_family="sportscore",
        )
        == competition_id
    )


def test_sportscore_rejects_ambiguous_generic_without_logo():
    competition_id, name, source_identity = source_native_identity(
        "basketball", {"competition": "Club Friendship"}
    )
    assert competition_id is None
    assert name == "Club Friendship"
    assert source_identity == ""


def test_sportscore_same_label_different_logo_stays_separate():
    left = source_native_identity(
        "basketball",
        {"competition": "Club Friendship", "competition_logo": "https://x.test/a.png"},
    )[0]
    right = source_native_identity(
        "basketball",
        {"competition": "Club Friendship", "competition_logo": "https://x.test/b.png"},
    )[0]
    assert left
    assert right
    assert left != right
