from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_photo_sweep_reaches_old_rows_and_wraps_without_chasing_new_arrivals(monkeypatch):
    from database import SessionLocal
    from models import Article,ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    from public_index import repair_recent_news_images,_SOURCE_IMAGE_CHECKED
    from bot.news_image_rotation import _CURSORS
    from bot import news_image_http
    import public_index
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY','1')
    _CURSORS.clear();_SOURCE_IMAGE_CHECKED.clear()
    db=SessionLocal();ids=[];football=[];probes=[]
    stamp=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(hours=1)
    def create(index,sport='football',public=True,old=False):
        a=Article(title='Club confirms preparations',slug='photo-rotation-'+str(index),sport=sport,
                  ai_generated=True,content='Original text stays intact.',summary='Original summary.',
                  image_url='https://fixture.example/photo-'+str(index)+'.jpg',source_url='https://fixture.example/report-'+str(index),
                  published_at=stamp-timedelta(days=9) if old else stamp)
        db.add(a);db.flush();ids.append(a.id)
        db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,
               public_ok=public,quality_ok=True,resolved_sport=sport,hero_media_kind='EDITORIAL_PHOTO'))
        return a.id
    def probe(urls,**kwargs):
        urls=list(urls);assert len(urls)<=160 and kwargs['max_workers']==6
        probes.append(urls)
        return {url:(True,'ok') for url in urls}
    monkeypatch.setattr(news_image_http,'probe_news_images',probe)
    monkeypatch.setattr(public_index,'_reachable_source_image',lambda *args,**kwargs:None)
    try:
        for i in range(330):football.append(create(i))
        create(500,'basketball');create(501,public=False);create(502,old=True)
        db.commit()
        assert repair_recent_news_images(db,limit=999,rotate=True)==0
        assert len(probes[-1])==160
        new_id=create(999);db.commit()
        assert repair_recent_news_images(db,limit=160,rotate=True)==0
        assert repair_recent_news_images(db,limit=160,rotate=True)==0
        visited=[url for batch in probes for url in batch]
        assert len(visited)==330 and len(set(visited))==330
        assert set(visited)=={'https://fixture.example/photo-'+str(i)+'.jpg' for i in range(330)}
        assert 'https://fixture.example/photo-999.jpg' not in visited
        assert repair_recent_news_images(db,limit=160,rotate=True)==0
        assert 'https://fixture.example/photo-999.jpg' in probes[-1]
        assert all(a.content=='Original text stays intact.' for a in db.query(Article).filter(Article.id.in_(ids)))
        assert all(a.published_at==stamp for a in db.query(Article).filter(Article.id.in_(football)))
        assert db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(football),ArticleTaxonomyResolution.public_ok.is_(True)).count()==330
    finally:
        db.rollback()
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close();_CURSORS.clear();_SOURCE_IMAGE_CHECKED.clear()


def test_transient_photo_source_recheck_precedes_other_alignments_with_same_budget(monkeypatch):
    import public_index
    from bot import news_image_http
    public_index._SOURCE_IMAGE_CHECKED.clear()
    articles=[SimpleNamespace(id=100+i,image_url='https://photos.example/'+str(i)+'.jpg',source_url='https://source.example/'+str(i)) for i in range(10)]
    taxes=[SimpleNamespace(public_ok=True,hero_media_kind='EDITORIAL_PHOTO') for _ in articles]
    db=Mock();q=db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value
    q.all.side_effect=[list(zip(articles,taxes)),[]]
    bad=articles[-1].image_url
    monkeypatch.setattr(news_image_http,'probe_news_images',lambda urls,**kw:{u:(u!=bad,'ok' if u!=bad else 'http_429') for u in urls})
    calls=[]
    monkeypatch.setattr(public_index,'_reachable_source_image',lambda url,**kwargs:calls.append(url) or None)
    assert public_index.repair_recent_news_images(db,recover_limit=16)==0
    assert len(calls)==6 and calls[0]==articles[-1].source_url
    assert articles[-1].image_url==bad and taxes[-1].public_ok
    db.commit.assert_not_called()
    public_index._SOURCE_IMAGE_CHECKED.clear()


def test_failed_photo_probe_cannot_advance_rotation(monkeypatch):
    import public_index
    from bot import news_image_http,news_image_rotation
    news_image_rotation._CURSORS.clear()
    item=SimpleNamespace(id=44,image_url='https://photos.example/44.jpg')
    monkeypatch.setattr(news_image_rotation,'next_image_health_rows',lambda *args,**kwargs:([(item,SimpleNamespace(public_ok=True))],'football',44))
    monkeypatch.setattr(news_image_http,'probe_news_images',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('transport failed')))
    with pytest.raises(RuntimeError):public_index.repair_recent_news_images(Mock(),rotate=True)
    assert news_image_rotation._CURSORS=={}


def test_rotation_is_only_selection_state_and_rejects_unknown_scopes():
    from bot.news_image_rotation import _CURSORS,finish_image_health_rows
    _CURSORS.clear()
    finish_image_health_rows('football',123)
    finish_image_health_rows('all',456)
    assert _CURSORS=={'football':123,'all':456}
    with pytest.raises(ValueError):finish_image_health_rows('untrusted',1)
    _CURSORS.clear()
