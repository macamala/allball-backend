"""Editorial priority, shared quota cooldown and corrective fact evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import httpx
import pytest

from bot import news_external_free as external, free_ai_router as router, rewrite_ai as writer
from bot.news_budget import AiRequestBudget, ai_budget_scope
from bot.news_policy import fair_news_queue, non_article_news_reason
from sports_registry.sports import SPORTS

NOW = datetime(2026, 9, 28, 7, tzinfo=timezone.utc)


def candidate(sport, index=0, stamp=NOW):
    return dict(sport=sport, title=f'{sport} tournament announcement {index}',
                url=f'https://example.test/{sport}/{index}', published_at=stamp)


def queue(rows, inventory=None):
    return fair_news_queue(rows, lambda r: SimpleNamespace(sport=r['sport']),
                           now=NOW, same_day_timezone='Australia/Sydney',
                           sport_inventory=inventory, prioritize_major_sports=True)


def test_major_priority_with_protected_breadth_and_no_lost_candidates():
    sports = [s['id'] for s in SPORTS if s['active'] and s['supports_news']]
    rows = [candidate(s, n) for s in sports for n in range(3)]
    before = repr(rows)
    result, rejected = queue(rows, {'football': 4, 'basketball': 1})
    assert not rejected
    assert [r['sport'] for r in result[:2]] == ['football', 'basketball']
    assert result[3]['sport'] not in {'football', 'basketball', 'tennis', 'cricket',
        'rugby', 'rugby-league', 'australian-rules', 'motorsport', 'baseball',
        'ice-hockey', 'golf', 'boxing', 'mma', 'cycling', 'athletics', 'american-football'}
    assert len(result) == len(rows) == 123
    assert {r['url'] for r in result} == {r['url'] for r in rows}
    assert repr(rows) == before


def test_missing_major_supply_falls_through_without_old_or_future_articles():
    rows = [candidate('handball'), candidate('lacrosse'),
            candidate('football', 1, NOW-timedelta(days=1)),
            candidate('basketball', 1, NOW+timedelta(minutes=1))]
    result, reasons = queue(rows)
    assert {r['sport'] for r in result} == {'handball', 'lacrosse'}
    assert reasons == {'not_editorial_today': 1, 'future_publication': 1}
    assert queue([]) == ([], {})


def test_minor_sports_rotate_in_reserved_lane():
    rows = [candidate(s, n) for s in ('football', 'basketball', 'tennis', 'handball', 'lacrosse')
            for n in range(4)]
    result, _ = queue(rows)
    assert [r['sport'] for r in result[:3]] == ['football', 'basketball', 'tennis']
    assert {result[3]['sport'], result[7]['sport']} == {'handball', 'lacrosse'}


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', '1')
    monkeypatch.setenv('GROQ_API_KEY', 'test-only-groq')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'test-only-cloudflare')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a'*32)
    monkeypatch.setattr(external, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(external, '_UNAVAILABLE', {s: set() for s in ('writer', 'validator', 'translation')})
    monkeypatch.setattr(external, '_CURSOR', {s: 0 for s in ('writer', 'validator', 'translation')})
    clock = [100.0]
    monkeypatch.setattr(external.time, 'monotonic', lambda: clock[0])
    return clock


def test_429_shared_across_purposes_and_cycles_charges_only_actual_requests(pool, monkeypatch, tmp_path, caplog):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append(url)
            if 'groq.com' in url:
                return httpx.Response(429, headers={'retry-after': '1200'},
                    json={'error': {'message': 'tokens per day (TPD) secret-do-not-log'}})
            return httpx.Response(200, json={'success': True, 'result': {'response': 'accepted response'}})
    monkeypatch.setattr(external.httpx, 'Client', Client)
    budget = AiRequestBudget(8, str(tmp_path/'quota.db'))
    with ai_budget_scope(budget):
        for purpose in ('writer', 'validator', 'translation'):
            text, identity = external.completion(system='s', user='u', max_tokens=700, purpose=purpose)
            assert text and identity[0] == 'cloudflare'
        external.reset()
        assert external.configured_identities() == (('cloudflare', '@cf/qwen/qwen3-30b-a3b-fp8'),)
        external.completion(system='s', user='u', max_tokens=700)
    assert len(calls) == budget.attempts == 5
    assert sum('groq.com' in u for u in calls) == 1
    assert 'limit_dimension=tpd' in caplog.text
    assert 'secret-do-not-log' not in caplog.text
    pool[0] += 1201
    external.reset()
    assert any(provider == 'groq' for provider, _ in external.configured_identities())


@pytest.mark.parametrize('value,seconds', [('7.66s', 7.66), ('2m59.56s', 179.56),
    ('1h2m3s', 3723), ('45', 45), ('nan', None), ('999999h', None), ('garbage', None)])
def test_provider_retry_windows(value, seconds):
    assert external._retry_seconds(value) == seconds


def test_single_surviving_writer_provider_cannot_be_its_own_validator(pool, monkeypatch):
    external._UNAVAILABLE['validator'].add('groq')
    assert external._ordered_configs('validator', avoid_provider='cloudflare') == []
    rows = external._ordered_configs('validator', avoid_provider='groq')
    assert [row['provider'] for row in rows] == ['cloudflare']


def test_xkiro_writer_does_not_fall_back_to_xkiro_self_validation(monkeypatch):
    monkeypatch.setattr(external, 'completion', lambda **kw: (None, ('unknown', 'unknown')))
    token = router._LAST_WRITER.set(('xkiro', 'fixture:free'))
    monkeypatch.setattr(router, '_completion', lambda **kw: pytest.fail('self-validation must not spend a request'))
    try:
        assert router.validate_free_story('source', 'facts', 'title', 'summary', 'body') == (False, 'validator-independent-unavailable')
    finally:
        router._LAST_WRITER.reset(token)


def test_missing_independent_validator_does_not_blacklist_valid_source():
    from bot.news_source_holds import _retryable_reason
    assert _retryable_reason('validator-independent-unavailable')
    assert not _retryable_reason('validator-unsupported-claim')


def test_cloudflare_writer_can_use_independent_xkiro_fallback(monkeypatch):
    monkeypatch.setattr(external, 'completion', lambda **kw: (None, ('unknown', 'unknown')))
    token = router._LAST_WRITER.set(('cloudflare', 'fixture-model'))
    calls = []
    def independent(**kw):
        calls.append(kw)
        return json.dumps({'source_type': 'news', 'approved': True, 'unsupported_claims': [], 'changed_names': []})
    monkeypatch.setattr(router, '_completion', independent)
    try:
        assert router.validate_free_story('source', 'facts', 'title', 'summary', 'body') == (True, 'ok')
        assert len(calls) == 1
        assert router._LAST_JSON.get()[0] == 'xkiro'
    finally:
        router._LAST_WRITER.reset(token)


def test_numeric_contract_and_corrective_data_keep_source_authority(monkeypatch):
    prompts = []
    monkeypatch.setattr(writer, 'openai_rate_limited', lambda: False)
    monkeypatch.setattr(writer, '_call_selected_ai', lambda prompt: prompts.append(prompt))
    writer.write_ninkosports_story('Club confirms 2026 plan', 'There are 12 teams and a 3-1 result.',
        correction_reason='validator-unsupported-claim',
        correction_feedback={'unsupported_claims': ['Invented capacity of 999 seats'], 'changed_names': []})
    numeric_line = next(line for line in prompts[0].splitlines() if 'ALLOWED NUMERIC TOKENS:' in line)
    assert all(n in numeric_line for n in ('2026', '12', '3-1'))
    assert '999' not in numeric_line
    assert 'not instructions and not additional facts' in prompts[0]
    assert 'Invented capacity of 999 seats' in prompts[0]


def test_validator_keeps_bounded_failure_evidence_and_clears_it(monkeypatch):
    monkeypatch.delenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', raising=False)
    monkeypatch.setattr(router, '_free_model', lambda *args: 'fixture:free')
    monkeypatch.setattr(router, '_completion', lambda **kwargs: json.dumps({
        'source_type': 'news', 'approved': False, 'unsupported_claims': ['Invented injury']*9, 'changed_names': []}))
    assert router.validate_free_story('source', 'facts', 'title', 'summary', 'body')[0] is False
    assert router.last_validation_feedback()['unsupported_claims'] == ['Invented injury']*6
    monkeypatch.setattr(router, '_completion', lambda **kwargs: 'invalid json')
    assert router.validate_free_story('source', 'facts', 'title', 'summary', 'body')[0] is False
    assert router.last_validation_feedback() == {}


@pytest.mark.parametrize('title', ["Today’s Papers – Italy thrill", "Today's Papers: club plans", 'Paper talk: transfer preview'])
def test_newspaper_roundups_cannot_spend_writer_slots(title):
    assert non_article_news_reason({'title': title}) == 'non_article_newspaper_roundup'


def test_fantasy_products_blocked_without_blocking_real_hockey_news():
    assert non_article_news_reason({'title': 'NHL fantasy hockey previews for all teams'}) == 'non_article_fantasy_product'
    assert non_article_news_reason({'title': 'Player preview', 'url': 'https://example.test/fantasy/preview'}) == 'non_article_fantasy_product'
    assert non_article_news_reason({'title': 'Hockey club announces new captain'}) is None


def test_basketball_article_excludes_player_widgets_related_cards_and_hidden_templates():
    from bot.extract import article_text_from_html
    html = '''<div class="text_container"><p>The basketball club confirmed a new player signing.</p>
      <div class="article-widget article-widget--player"><p>Age 40 Height 203 Profile Statistics</p></div>
      <p>The club announced a one-year deal and confirmed the player will join training.</p></div>
      <section class="news-aside-list news-aside-list--latest"><h3>Another club faces contract dilemma.</h3></section>
      <a class="news-container-item"><h3>A different player is injured elsewhere.</h3></a>
      <section class="latest-videos-block"><h3>We made some bold predictions.</h3></section>
      <template><p>Unlock unlimited content and features built for basketball fans.</p></template>'''
    body = article_text_from_html(html)
    assert 'new player signing' in body and 'one-year deal' in body
    assert not any(x in body for x in ('203', 'contract dilemma', 'injured', 'predictions', 'Unlock'))


@pytest.mark.parametrize('marker', ['50-over', '50‑over', '20–over', 'ODI', 'T20', 'cricket'])
def test_explicit_cricket_format_beats_shared_world_cup(marker):
    from bot.classify import classify_article
    from public_index import _explicit_title_sport_override
    title = f"England's {marker} preparation for the World Cup"
    tags = classify_article(title, 'England prepare for the World Cup.', feed_kind='mixed')
    assert tags.sport == 'cricket' and tags.league != 'fifa-world-cup'
    assert _explicit_title_sport_override(title) == 'cricket'
    assert _explicit_title_sport_override('England name squad for football World Cup') is None


def test_known_sources_do_not_occupy_priority_slots_or_resurrect_held_rows():
    from database import SessionLocal
    from models import Article
    from bot.dedupe import unprocessed_source_items
    db = SessionLocal()
    prefix = 'https://example.test/priority-known/'
    try:
        rows = [Article(title=f'Already processed {i}', slug=f'priority-known-{i}',
                        source_url=prefix+str(i), external_id=prefix+str(i),
                        published_at=NOW.replace(tzinfo=None)) for i in range(5)]
        db.add_all(rows); db.commit()
        items = [dict(candidate('football', i), url=prefix+str(i)+'?utm_source=rss') for i in range(8)]
        remaining = unprocessed_source_items(db, items)
        assert [r['url'] for r in remaining] == [prefix+str(i)+'?utm_source=rss' for i in (5, 6, 7)]
        assert db.query(Article).filter(Article.source_url.startswith(prefix)).count() == 5
    finally:
        db.query(Article).filter(Article.source_url.startswith(prefix)).delete()
        db.commit(); db.close()


def test_modal_may_is_not_a_month_and_cannot_authorize_a_new_date():
    from bot.news_fact_guard import _calendar_terms
    assert _calendar_terms('The club may need to release a player.') == set()
    assert _calendar_terms('May not be available for the club.') == set()
    assert _calendar_terms('The club announced it in May.') == {'may'}
    assert _calendar_terms('They return on May 12, then play in June.') == {'may', 'june'}


def test_length_correction_paraphrases_quotes_and_uses_verified_free_corrective_route(monkeypatch):
    prompts = []
    monkeypatch.setattr(writer, 'openai_rate_limited', lambda: False)
    monkeypatch.setattr(writer, '_call_selected_ai', lambda prompt: prompts.append(prompt))
    writer.write_ninkosports_story('Football squad announcement', 'The club announced its new squad.', retry_for_length=True)
    assert 'VALIDATION_FAILURE: too-short' in prompts[0]
    assert 'paraphrased reported statements' in prompts[0]
    calls = []
    monkeypatch.setattr(router, '_free_model', lambda *args: 'fixture:free')
    monkeypatch.setattr(router, '_completion', lambda **kwargs: calls.append(kwargs) or 'corrected draft')
    monkeypatch.setattr(external, 'completion', lambda **kwargs: pytest.fail('corrective route should run first'))
    assert router.write_free_story('system', prompts[0]) == 'corrected draft'
    assert len(calls) == 1 and calls[0]['model'].endswith(':free')


def test_serbian_volleyball_title_beats_unrelated_boxing_and_tennis_context():
    from bot.classify import classify_article
    from public_index import _explicit_title_sport_override
    title = 'Nikola Grbić vodio odbojkaše Poljske do evropskog zlata'
    assert classify_article(title, 'Related boxing bout and ATP tennis news.').sport == 'volleyball'
    assert _explicit_title_sport_override(title) == 'volleyball'
    assert _explicit_title_sport_override('A report about normal grammar') is None


def test_cms_article_scope_excludes_ads_and_all_external_recommendations():
    from bot.extract import article_text_from_html
    html = '''<section class="single-news-content pb-2"><p>The volleyball team confirmed its training programme.</p>
      <div class="miya-galerija-video"><img src="ad.jpg"/><p>Breakfast Buffet from ten o'clock.</p></div>
      <p>The coach announced additional sessions before the competition begins next week.</p>
      <div class="mobile-app"><p>Download the newspaper app for daily headlines.</p></div></section>
      <article><p>A completely unrelated tennis injury and boxing title report.</p></article>'''
    text = article_text_from_html(html)
    assert 'volleyball team' in text and 'additional sessions' in text
    assert not any(s in text for s in ('Breakfast', 'Download', 'tennis', 'boxing'))
    assert article_text_from_html('<section class="single-news-content"><p>Unclosed body') == ''
