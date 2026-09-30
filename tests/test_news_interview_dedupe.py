from datetime import datetime

import pytest

from bot.dedupe import confirmed_interview_key, existing_near_duplicate, titles_are_near_duplicate
from database import SessionLocal
from models import Article, ArticleTaxonomyResolution
from public_index import repair_recent_duplicate_news
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


def test_ingest_and_public_repair_share_content_key_and_retain_both_rows():
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
    finally:
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit(); db.close()
