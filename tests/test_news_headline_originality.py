from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot.news_policy import original_draft_reason
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_lead_headline, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://www.rugbypass.com/news/scott-barrett-among-notable-inclusions-in-34-man-all-blacks-bledisloe-cup-squad/'
SOURCE_TITLE = 'Scott Barrett among notable inclusions in 34-man All Blacks Bledisloe Cup squad'
SOURCE_LEAD = ('All Blacks head coach Dave Rennie has named his 34-man squad to take on the '
               'Wallabies in the Bledisloe Cup starting next weekend at Eden Park in Auckland.')
BAD_TITLE = ('All Blacks head coach Dave Rennie has named a 34-man squad for the '
             'Bledisloe Cup series starting next weekend at Eden Park in Auckland.')
GOOD_TITLE = 'Barrett and Frizell return as Taylor takes All Blacks captaincy'
BODY = ('Codie Taylor will captain the All Blacks, with Ardie Savea and Luke Jacobson absent. '
        'Scott Barrett and Shannon Frizell are returning to the national side for the Bledisloe Cup.')


@pytest.mark.parametrize('title,reason', [
    (SOURCE_LEAD, 'copied_source_headline'),
    (SOURCE_LEAD.replace('has named', 'HAS NAMED').rstrip('.'), 'copied_source_headline'),
    (BAD_TITLE, 'headline_too_similar_to_source'),
    (GOOD_TITLE, None),
    ('Codie Taylor will captain the All Blacks', None),
])
def test_body_sentence_cannot_be_reused_as_a_headline(title, reason):
    draft = {'title': title, 'summary': 'Taylor leads the side.', 'body': BODY}
    assert original_draft_reason(draft, SOURCE_TITLE, SOURCE_LEAD + ' ' +
        'Shannon Frizell and Scott Barrett return, with Codie Taylor named captain.') == reason


@pytest.mark.parametrize('field,value', [('id', 22164), ('ai_generated', False),
    ('source_url', 'https://example.test/other'), ('title', GOOD_TITLE)])
def test_audited_headline_repair_requires_exact_row_and_source(field, value):
    row = SimpleNamespace(id=22163, ai_generated=True, source_url=URL, title=BAD_TITLE)
    setattr(row, field, value)
    before = vars(row).copy()
    assert _correct_confirmed_lead_headline(row) == {}
    assert vars(row) == before


@pytest.mark.parametrize('public', [True, False])
def test_headline_repair_preserves_archive_identity_and_records_incident(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):
        model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        article = Article(id=22163, title=BAD_TITLE, slug='original-stable-url', sport='rugby',
            source_url=URL, published_at=stamp, content=BODY, ai_content=BODY, ai_generated=True,
            image_url='https://example.test/editorial-photo.jpg')
        tax = ArticleTaxonomyResolution(article_id=22163, resolved_sport='rugby',
            resolver_version=RESOLVER_VERSION, public_ok=public)
        db.add_all([article, tax]); db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert article.title == (GOOD_TITLE if public else BAD_TITLE)
        assert article.slug == 'original-stable-url' and article.published_at == stamp
        assert article.content == BODY and article.ai_content == BODY
        assert article.image_url == 'https://example.test/editorial-photo.jpg'
        assert tax.public_ok is public
        assert db.query(NewsIncident).filter_by(reason_code='headline_too_similar_to_source',
            status='auto_corrected').count() == int(public)
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()
