import news_xkiro_quality_probe as probe


def _fixture_text():
    base = probe.SOURCE_FACTS.replace("\n", " ")
    filler = (
        " The synthetic report stays limited to the supplied match record and repeats no extra claims."
        " It adds no venue, date, crowd detail, tactical judgment, injury update, quotation or outside context."
    )
    return base + filler * 2


def test_quality_fixture_accepts_all_source_numbers_names_and_latin_serbian():
    text = _fixture_text()
    payload = {language: text for language in probe.LANGUAGES}
    assert probe.validate_translations(payload) == []


def test_quality_fixture_rejects_missing_number_and_serbian_cyrillic():
    text = _fixture_text()
    payload = {language: text for language in probe.LANGUAGES}
    payload["de"] = payload["de"].replace("2-0", "two goals")
    payload["sr"] += " тест"
    errors = probe.validate_translations(payload)
    assert "de:missing_required_number" in errors
    assert "sr:cyrillic_not_allowed" in errors


def test_free_entitlement_requires_free_model_and_remaining_tokens(monkeypatch):
    calls = []
    def request(method, url, key, payload=None):
        calls.append(url)
        if url.endswith("/models"):
            return {"http_status": 200}, {
                "data": [{"id": probe.MODEL, "access_tier": "free"}]
            }
        return {"http_status": 200}, {
            "free_tokens": {"remaining": 123, "limit_per_day": 500000}
        }
    monkeypatch.setattr(probe, "request_json", request)
    ok, report = probe.verify_free_entitlement("fixture")
    assert ok
    assert report["model_catalog_verified"]
    assert report["free_usage_verified"]
    assert report["free_tokens_remaining"] == 123
    assert len(calls) == 2


def test_free_entitlement_rejects_paid_model_before_generation(monkeypatch):
    calls = []
    def request(method, url, key, payload=None):
        calls.append(url)
        return {"http_status": 200}, {
            "data": [{"id": probe.MODEL, "access_tier": "paid"}]
        }
    monkeypatch.setattr(probe, "request_json", request)
    ok, report = probe.verify_free_entitlement("fixture")
    assert not ok
    assert not report["model_catalog_verified"]
    assert len(calls) == 1


def test_free_entitlement_rejects_zero_remaining_tokens(monkeypatch):
    def request(method, url, key, payload=None):
        if url.endswith("/models"):
            return {"http_status": 200}, {
                "data": [{"id": probe.MODEL, "access_tier": "free"}]
            }
        return {"http_status": 200}, {"free_tokens": {"remaining": 0}}
    monkeypatch.setattr(probe, "request_json", request)
    ok, report = probe.verify_free_entitlement("fixture")
    assert not ok
    assert report["free_tokens_remaining"] == 0
