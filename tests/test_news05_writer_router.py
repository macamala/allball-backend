import socket
import httpx

from bot import news_writer_router as router
from bot.news_budget import AiRequestBudget, ai_budget_scope


def _clear(monkeypatch):
    for key in (
        "GROQ_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
        "OPENAI_API_KEY", "NEWS_WRITER_ORDER", "NEWS_GROQ_MODEL",
        "NEWS_CLOUDFLARE_MODEL", "OPENAI_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    router.reset_writer_state()


def test_free_first_router_uses_groq_and_tracks_identity(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-groq")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fixture-cf")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a" * 32)
    monkeypatch.setattr(router, "_groq", lambda cfg, prompt: "Groq draft")
    monkeypatch.setattr(router, "_cloudflare", lambda *a: (_ for _ in ()).throw(AssertionError("unexpected fallback")))
    assert router.write_ninkosports_story("Title", "Football facts") == "Groq draft"
    assert router.last_writer_identity()[0] == "groq"


def test_policy_skips_circuit_broken_writer(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-groq")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fixture-cf")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "b" * 32)
    monkeypatch.setattr(router, "_groq", lambda *a: (_ for _ in ()).throw(AssertionError("blocked writer called")))
    monkeypatch.setattr(router, "_cloudflare", lambda cfg, prompt: "Cloudflare draft")
    with router.writer_policy_scope(lambda provider, model: provider != "groq"):
        assert router.write_ninkosports_story("Title", "Football facts") == "Cloudflare draft"
    assert router.last_writer_identity()[0] == "cloudflare"


def test_correction_prefers_different_writer_but_keeps_original_as_last_fallback(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-groq")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fixture-cf")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "c" * 32)
    calls = []
    monkeypatch.setattr(router, "_groq", lambda cfg, prompt: calls.append("groq") or "First")
    monkeypatch.setattr(router, "_cloudflare", lambda cfg, prompt: calls.append("cloudflare") or "Second")

    assert router.write_ninkosports_story("Title", "Football facts") == "First"
    first_identity = router.last_writer_identity()
    assert first_identity[0] == "groq"

    assert router.write_ninkosports_story(
        "Title", "Football facts", correction_reason="unsupported_number",
        deprioritize_writers={first_identity},
    ) == "Second"
    assert calls == ["groq", "cloudflare"]
    assert router.last_writer_identity()[0] == "cloudflare"


def test_unusable_provider_fails_over_and_is_held_for_cycle(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-groq")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fixture-cf")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "d" * 32)
    calls = []
    monkeypatch.setattr(router, "_groq", lambda cfg, prompt: calls.append("groq") or None)
    monkeypatch.setattr(router, "_cloudflare", lambda cfg, prompt: calls.append("cloudflare") or "Good")
    assert router.write_ninkosports_story("Title", "Football facts") == "Good"
    assert router.write_ninkosports_story("Title 2", "More football facts") == "Good"
    assert calls == ["groq", "cloudflare", "cloudflare"]


def test_explicit_invalid_writer_order_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NEWS_WRITER_ORDER", "groq,unknown")
    monkeypatch.setenv("GROQ_API_KEY", "fixture")
    assert router.configuration_reason() == "invalid_news_writer_order"


def test_no_configured_writer_fails_closed(monkeypatch):
    _clear(monkeypatch)
    assert router.configuration_reason() == "news_ai_key_missing"
    assert router.writer_rate_limited()


def test_cloudflare_credentials_are_a_valid_writer_configuration(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NEWS_WRITER_ORDER", "cloudflare")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fixture")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "e" * 32)
    assert router.configuration_reason() is None
    assert router.configured_writer_identities()[0][0] == "cloudflare"


def test_each_real_provider_http_attempt_consumes_shared_budget(monkeypatch, tmp_path):
    _clear(monkeypatch)
    responses = iter([
        httpx.Response(500, request=httpx.Request("POST", "https://example.test")),
        httpx.Response(200, request=httpx.Request("POST", "https://example.test"), json={"ok": True}),
    ])
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return next(responses)
    monkeypatch.setattr(router.httpx, "Client", Client)

    budget = AiRequestBudget(2, str(tmp_path / "ledger.db"), daily_limit=2)
    with ai_budget_scope(budget):
        assert router._post("groq", "https://example.test", {}, {}) is None
        assert router._post("cloudflare", "https://example.test", {}, {}) == {"ok": True}
    assert budget.attempts == 2
    assert not AiRequestBudget(1, str(tmp_path / "ledger.db"), daily_limit=2).can_start()


def test_three_deterministic_rejects_hold_writer_only_for_current_cycle(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-groq")
    identity = router.configured_writer_identities()[0]
    assert identity[0] == "groq"
    assert router.note_writer_rejection(*identity) == 1
    assert router.note_writer_rejection(*identity) == 2
    assert not router.writer_rate_limited()
    assert router.note_writer_rejection(*identity) == 3
    assert router.writer_rate_limited()
    router.reset_writer_state()
    assert not router.writer_rate_limited()
