from datetime import datetime

import pytest

from bot.dedupe import confirmed_interview_key, existing_near_duplicate, titles_are_near_duplicate
from database import SessionLocal
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import repair_recent_duplicate_news, persist_public_article
from taxonomy_resolver import RESOLVER_VERSION


BODY = (
    'Boaći recalled his time at Red Star and said unity is the source of victory. '
    'He watched from the bench due to a minor injury after Milunović was sent off, '
    'and he trusted the players taking penalties. He suggested that Bukari or Ivanić '
    'could score in the upcoming match.'
)
OTHER = BODY.replace('Boaći', 'Richmond Boakye').replace('source of victory', 'way to victory')
TITLE = 'Red Star Belgrade prepares for its first match at home in this European competition'
OTHER_TITLE = 'Richmond Boakye expects a star atmosphere as Red Star host Copenhagen in Conference League'


def test_audited_interview_matches_across_different_headlines_and_transliterated_name():
    assert not titles_are_near_duplicate(TITLE, OTHER_TITLE)
    assert confirmed_interview_key(BODY) == confirmed_interview_key(OTHER)
    assert confirmed_interview_key(BODY)


@pytest.mark.parametrize('detail', ['Boaći', 'Red Star', 'Milunović', 'Bukari', 'Ivanić',
    'penalties', 'bench', 'minor injury', 'unity', 'victory'])
def test_same_club_player_or_partial_background_cannot_collapse_distinct_news(detail):
    assert confirmed_interview_key(BODY.replace(detail, 'other')) is None


def test_ingest_and_public_repair_share_content_key_and_retain_both_rows(monkeypatch):
    db = SessionLocal()
    ids = []
    try:
        for index, title, body in ((0, TITLE, BODY), (1, OTHER_TITLE, OTHER)):
            article = Article(title=title, content=body, ai_generated=True,
                external_id=f'https://fixture.example/boakye-interview-{index}',
                slug=f'boakye-interview-fixture-{index}', created_at=datetime.utcnow(),
                published_at=datetime.utcnow(), sport='football', image_url='https://fixture.example/photo.jpg')
            db.add(article); db.flush(); ids.append(article.id)
            db.add(ArticleTaxonomyResolution(article_id=article.id,
                resolver_version=RESOLVER_VERSION, resolved_sport='football', public_ok=True))
            if index == 0:
                assert existing_near_duplicate(db, OTHER_TITLE, datetime.utcnow(), body=OTHER).id == article.id
        db.commit()
        assert repair_recent_duplicate_news(db, limit=600) >= 1
        assert db.query(Article).filter(Article.id.in_(ids)).count() == 2
        visible = db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id.in_(ids),
            ArticleTaxonomyResolution.public_ok.is_(True)).all()
        assert len(visible) == 1 and visible[0].article_id == ids[-1]
        from bot.news_learning import article_has_open_incident
        from taxonomy_resolver import TaxonomyResolution
        import public_index
        assert article_has_open_incident(db, ids[0])
        monkeypatch.setattr(public_index, 'evaluate_quality', lambda **kwargs: {'ok': True, 'word_count': 100})
        monkeypatch.setattr(public_index, 'isolation_ok', lambda *args, **kwargs: True)
        monkeypatch.setattr(public_index, 'news_image_is_publishable', lambda *args: True)
        held = db.get(Article, ids[0])
        resolution = TaxonomyResolution(sport='football', competition=None,
            sport_confidence=0.99, competition_confidence=0.0)
        persist_public_article(db, held, resolution, commit=True)
        tax = db.query(ArticleTaxonomyResolution).filter_by(article_id=held.id).one()
        assert tax.public_ok is False
        # Establish the incident, rather than an unrelated quality failure,
        # is what prevents a reindex/repair from making the row public again.
        db.query(NewsIncident).filter_by(article_id=held.id).update({'status': 'dismissed'})
        db.commit()
        persist_public_article(db, held, resolution, commit=True)
        assert tax.public_ok is True
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit(); db.close()
