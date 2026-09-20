from collector.canonical_detail import attach_canonical_detail, canonicalize_statistics, canonicalize_timeline


def test_capability_inventory_is_static():
    from collector.detail_capabilities import capability_inventory

    rows = capability_inventory()
    assert any(row["provider_family"] == "openligadb" and row["timeline"] for row in rows)


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
