from collector.family_catalog import adapter_key_for


def test_fivb_web_uses_dedicated_volleyballworld_adapter():
    assert adapter_key_for("fivb-web", "volleyball") == "volleyballworld"
