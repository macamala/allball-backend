from types import SimpleNamespace

import pytest

from bot import news_fact_guard as guard
from bot import fetch_sources as ingest
from public_index import _correct_confirmed_mccabe_copy
from taxonomy_resolver import TaxonomyResolution


def test_shared_football_club_names_cannot_create_a_league_fact(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    source = "Source article category: Women's Team. Chelsea defeated Arsenal."
    assert guard.fact_lock_reason({'body': 'Chelsea won in the Premier League.'},
        'Club news', source, expected_sport='football') == 'unsupported_competition:england-premier-league'
    assert guard.competition_in_source('england-premier-league', source) is False
    assert guard.competition_in_source('england-premier-league', 'The English Premier League confirmed the decision.')


@pytest.mark.parametrize('source,retained', [('Chelsea met Arsenal.', False), ('Chelsea played in the Premier League.', True)])
def test_public_competition_requires_source_evidence(source, retained):
    resolution = TaxonomyResolution('football', 'england-premier-league', .98, .97, ['club-name'])
    result = ingest._source_grounded_resolution(resolution, 'Team news', source)
    assert result.sport == 'football' and result.sport_confidence == .98
    assert result.public_competition == ('england-premier-league' if retained else None)
    assert resolution.public_competition == 'england-premier-league'


def test_writer_never_receives_inferred_league_as_verified_fact(monkeypatch):
    captured = []
    monkeypatch.setattr(ingest, 'write_ninkosports_story', lambda **kwargs: captured.append(kwargs) or '')
    ingest._ai_story('Chelsea women news', 'Chelsea defeated Arsenal in London.', 'football',
                     'england-premier-league', 6000)
    assert captured[0]['league'] == ''


def test_audited_womens_copy_repair_preserves_identity_and_is_idempotent():
    row = SimpleNamespace(id=22166, ai_generated=True,
        source_url='https://www.chelseafc.com/en/news/article/katie-mccabe-on-playing-smart-and-riding-the-storms-against-former-club',
        title='Katie McCabe helps Chelsea defeat former club Arsenal in Premier League match',
        content='The win mattered most.', ai_content='The win mattered most.',
        league='england-premier-league', country='england', slug='stable-original-url')
    tax = SimpleNamespace(resolved_competition='england-premier-league', competition_confidence=.98, public_ok=True)
    assert _correct_confirmed_mccabe_copy(row, tax)
    assert "Chelsea Women's" in row.title and 'Premier League' not in row.title
    assert row.league is None and tax.resolved_competition is None
    assert row.slug == 'stable-original-url' and tax.public_ok is True
    assert _correct_confirmed_mccabe_copy(row, tax) == {}
    row.id = 999
    assert _correct_confirmed_mccabe_copy(row, tax) == {}


@pytest.mark.parametrize('photo_ok,confirmed_hold,expected_public', [(True, False, True), (False, False, False), (True, True, False)])
def test_full_repair_restores_only_after_all_public_gates(monkeypatch, photo_ok, confirmed_hold, expected_public):
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from public_index import repair_recent_gossip_news
    from taxonomy_resolver import RESOLVER_VERSION
    monkeypatch.setattr('bot.news_image_http.news_image_is_reachable', lambda url: photo_ok)
    old = "McCabe reflects on Chelsea Women's victory over former club Arsenal"
    body = ("McCabe said Chelsea had prepared for Arsenal's ability in possession before the football match. "
        "The team had to withstand pressure before taking control of the ball. Alyssa Thompson scored the goal.\n\n"
        "Arsenal added attackers in the second half, and McCabe said Chelsea needed to remain organised. "
        "Keeping possession near the corner helped them protect their advantage and take the points. "
        "She said she respected Arsenal's supporters after spending a decade with the club.\n\n"
        "McCabe praised Keira Walsh for her work in midfield. She described Walsh as a passing option under pressure "
        "and said her composure helped Chelsea retain possession in tight areas. McCabe was pleased with the victory.")
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        article = Article(id=22166, title=old, slug='stable-url', sport='football',
            source_url='https://www.chelseafc.com/en/news/article/katie-mccabe-on-playing-smart-and-riding-the-storms-against-former-club',
            summary='McCabe praised Walsh after the win against Arsenal.', content=body, ai_content=body,
            ai_generated=True, published_at=datetime.utcnow(), image_url='https://example.test/player.jpg')
        tax = ArticleTaxonomyResolution(article_id=22166, resolved_sport='football', sport_confidence='0.98',
            competition_confidence='0', resolver_version=RESOLVER_VERSION, public_ok=False)
        incident = NewsIncident(article_id=22166, reason_code='non_news_retrospective_commentary',
            phase='postpublish', writer_provider='news-audit', writer_model='deterministic',
            status='open', confirmed=confirmed_hold, draft_excerpt=old)
        db.add_all([article, tax, incident]); db.commit()
        assert repair_recent_gossip_news(db) == 1
        assert article.title == "McCabe praises Walsh after Chelsea Women's victory over Arsenal"
        assert tax.public_ok is expected_public
        # The current verified club catalogue may tag an admitted women's
        # story, but a held article must not acquire a public league.
        assert tax.resolved_competition == ('england-womens-super-league' if expected_public else None)
        assert article.slug == 'stable-url'
        assert incident.status == ('open' if confirmed_hold else 'auto_corrected')
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()
