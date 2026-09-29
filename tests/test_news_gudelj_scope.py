from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot import news_fact_guard as guard
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_gudelj_copy, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://www.crvenazvezdafk.com/vesti/gudelj-medju-najboljim-mladim-stoperima-sveta'
TITLE = 'Stefan Gudelj ranked eighth among world’s best football defenders under 22'
SUMMARY = 'Stefan Gudelj of Red Star Belgrade has been ranked eighth among the world’s best defenders under 22, according to the latest CIES football observer study.'
BODY = ('The study covers more than 70 leagues worldwide and gives Gudelj an index of 79.4, placing him among the top young defenders globally.\n\n'
        'He is listed alongside European stars such as Barcelona’s Cubarsí, Liverpool’s Jeremy Jacquet, and Real Madrid’s Dean Huijsen.\n\n'
        'Red Star’s consistent progress and the player’s maturity have earned him international recognition and another strong endorsement of the club’s youth academy.')


@pytest.mark.parametrize('public', [True, False])
def test_exact_published_copy_repair_preserves_archive_and_records_correction(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
        article = Article(id=22201,title=TITLE,summary=SUMMARY,slug='unchanged-gudelj-url',sport='football',
            source_url=URL,content=BODY,ai_content=BODY,ai_generated=True,published_at=stamp,
            image_url='https://photo.test/gudelj.jpg')
        tax = ArticleTaxonomyResolution(article_id=22201,resolved_sport='football',resolver_version=RESOLVER_VERSION,public_ok=public)
        db.add_all([article,tax]); db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert tax.public_ok is public and article.published_at == stamp
        assert article.slug == 'unchanged-gudelj-url' and article.image_url == 'https://photo.test/gudelj.jpg'
        if public:
            assert 'centre-back study' in article.title and 'centre-backs under 22' in article.summary
            assert 'Red Star’s consistent progress' not in article.content
            assert 'The club credited Gudelj’s performances' in article.content
            assert article.content == article.ai_content
            assert db.query(NewsIncident).filter_by(reason_code='expanded_player_position_scope',status='auto_corrected').count() == 1
        else:
            assert article.content == BODY and db.query(NewsIncident).count() == 0
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


@pytest.mark.parametrize('field,value', [('id',22202),('ai_generated',False),('source_url','https://other.test/story')])
def test_repair_never_touches_other_sources_or_originals(field,value):
    row=SimpleNamespace(id=22201,ai_generated=True,source_url=URL,title=TITLE,summary=SUMMARY,content=BODY,ai_content=BODY)
    setattr(row,field,value); before=vars(row).copy()
    assert _correct_confirmed_gudelj_copy(row) == {} and vars(row)==before


def test_source_position_and_actor_scope_remain_locked(monkeypatch):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *a:None)
    source_title='Гудељ међу најбољим младим штоперима света'
    source='Стефан Гудељ се нашао међу најбоље оцењеним штоперима.'
    assert guard.fact_lock_reason({'title':TITLE},source_title,source) == 'expanded_player_position_scope'
    assert guard.fact_lock_reason({'body':BODY.split('\n\n')[-1]},source_title,source) == 'player_progress_assigned_to_club'
    assert guard.fact_lock_reason({'title':'Gudelj features among highly rated young centre-backs'},source_title,source) is None
