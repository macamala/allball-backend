from collector.canonical_detail import attach_canonical_detail, canonicalize_statistics, canonicalize_timeline
from collector.detail_capabilities import capability_inventory
from collector.rich_capability import build_rows


def test_capability_inventory_is_static():
    rows = capability_inventory()
    assert any(row["provider_family"] == "openligadb" and row["timeline"] for row in rows)


def test_rich_capability_covers_frozen_180():
    rows = build_rows()
    assert len(rows) == 180
    assert len({row["competition"] for row in rows}) == 180



def test_timeline_and_stats_omit_unknown_zeros():
    timeline = canonicalize_timeline(
        [{"type": "goal", "minute": 12, "player": "Saka", "score_after": {"home": 1, "away": 0}}]
    )
    assert timeline[0]["family"] == "goal"
    assert timeline[0]["score_after"]["home"] == 1
    stats = canonicalize_statistics([{"label": "Possession", "home": 58, "away": 42}, {"label": "xG"}])
    labels = [row["label"] for row in stats]
    assert "Possession" in labels
    assert "xG" not in labels


def test_attach_canonical_detail_drops_empty_sections():
    event = attach_canonical_detail(
        {
            "incidents": [],
            "statistics": [],
            "lineups": [],
            "periods": [],
            "score": {"home": 0, "away": 0},
        }
    )
    assert "incidents" not in event
    assert "statistics" not in event
    assert "lineups" not in event
    assert event["score"]["home"] == 0


def test_volleyball_set_pairs_and_match_score():
    from collector.canonical_detail import volleyball_match_score, volleyball_sets_from_scalars

    sets = volleyball_sets_from_scalars([25, 25, 25, 19, 21, 14])
    assert [(row["home"], row["away"]) for row in sets] == [(25, 19), (25, 21), (25, 14)]
    assert volleyball_match_score(sets) == {"home": 3, "away": 0}
    event = attach_canonical_detail(
        {
            "sport": "volleyball",
            "score": {"home": 2, "away": 0},
            "periods": [25, 25, 25, 19, 21, 14],
        }
    )
    assert event["score"]["home"] == 3
    assert event["score"]["away"] == 0
    assert event["periods"][0]["home"] == 25
    assert event["periods"][0]["away"] == 19
