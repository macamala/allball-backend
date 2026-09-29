from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot import news_fact_guard as guard
from bot.news_policy import original_draft_reason
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_ufc_copy, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://www.ufc.com/news/octagon-returns-down-under-ufc-fight-night-sydney-sunday-february-7'
BODY = ('The venue previously hosted Volkovski vs. Lopes. '
        'Travel packages for fans are available through Sportsnet Holidays, and exclusive corporate suites can be booked directly via Afterpay Arena. '
        'General public and UFC VIP ticket details will be announced later, with pre‑sale access available through UFC.com/Sydney.')


@pytest.mark.parametrize('source,draft,blocked', [
    ('VOLKANOVSKI vs. LOPES', 'Volkovski vs. Lopes', True),
    ('VOLKANOVSKI vs. LOPES', 'Volkanovski vs. Lopes', False),
    ('DJOKOVIC vs. SINNER', 'Djokvic vs. Sinner', True),
    ('ARSENAL vs CHELSEA', 'Arsenal vs Chelsea', False),
    ('VOLKANOVSKI vs. LOPES', 'The event returns to Sydney.', False),
    ('VOLKANOVSKI vs. LOPES and Volkovski vs. Jones', 'Volkovski vs. Jones', False),
])
def test_explicit_participant_spelling_is_locked_without_guessing_identity(monkeypatch, source, draft, blocked):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    monkeypatch.setattr(guard, '_acronyms', lambda text: set())
    reason = guard.fact_lock_reason({'body': draft}, 'Event announcement', source)
    assert bool(reason and reason.startswith('unsupported_event_participant:')) is blocked


@pytest.mark.parametrize('address', ['UFC.com/Sydney', 'tickets.example.org', 'tickets.example.net/register'])
def test_bare_addresses_cannot_evade_the_no_links_gate(address):
    draft = {'title': 'Event returns to city', 'summary': 'The event has been announced.',
             'body': 'Registration is available through ' + address}
    assert original_draft_reason(draft, 'Event announcement', 'Source facts') == 'external_link_in_copy'


@pytest.mark.parametrize('field,value', [('id', 22166), ('ai_generated', False),
    ('source_url', 'https://example.test/unrelated')])
def test_ufc_repair_is_strictly_scoped(field, value):
    row = SimpleNamespace(id=22165, ai_generated=True, source_url=URL, content=BODY, ai_content=None)
    setattr(row, field, value)
    before = vars(row).copy()
    assert _correct_confirmed_ufc_copy(row) == {}
    assert vars(row) == before


@pytest.mark.parametrize('public', [True, False])
def test_confirmed_repair_is_audited_idempotent_and_never_resurrects_a_hold(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):
        model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        article = Article(id=22165, title='UFC Fight Night returns to Sydney', slug='ufc-original-link',
            sport='mma', source_url=URL, published_at=stamp, content=BODY, ai_content=BODY,
            ai_generated=True, image_url='https://example.test/city.jpg')
        tax = ArticleTaxonomyResolution(article_id=22165, resolved_sport='mma',
            resolver_version=RESOLVER_VERSION, public_ok=public)
        db.add_all([article, tax]); db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        if public:
            assert article.content == 'The venue previously hosted Volkanovski vs. Lopes.'
            assert article.ai_content == article.content
        else:
            assert article.content == BODY
        assert article.published_at == stamp and article.slug == 'ufc-original-link'
        assert article.image_url == 'https://example.test/city.jpg' and tax.public_ok is public
        assert db.query(NewsIncident).filter_by(
            reason_code='confirmed_participant_spelling_and_commercial_copy', status='auto_corrected'
        ).count() == int(public)
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()
