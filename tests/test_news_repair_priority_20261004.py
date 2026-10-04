from datetime import datetime,timedelta,timezone
import logging
import pytest


@pytest.mark.parametrize('focus,expected', [('1',1),('0',0)])
def test_old_football_incident_is_not_starved_by_newer_other_sports(monkeypatch,caplog,focus,expected):
    from database import SessionLocal
    from models import Article,ArticleTaxonomyResolution,NewsIncident
    from taxonomy_resolver import RESOLVER_VERSION
    from public_index import repair_recent_gossip_news
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY',focus)
    db=SessionLocal();ids=[]
    stamp=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(hours=1)
    try:
        bad=Article(title='Battlefield Studios Unveils Season 5 Updates for Battlefield 6 and REDSEC',
            slug='older-football-incident-'+focus,sport='football',ai_generated=True,
            summary='Preserve the original report.',content='Original retained copy, never rewritten by the selector.',
            published_at=stamp-timedelta(hours=24),source_url='https://example.test/old/'+focus,
            image_url='https://example.test/retained.jpg')
        db.add(bad);db.flush();ids.append(bad.id)
        bad_id=bad.id
        db.add(ArticleTaxonomyResolution(article_id=bad.id,resolver_version=RESOLVER_VERSION,
            resolved_sport='football',public_ok=True,quality_ok=True))
        for i in range(601):
            a=Article(title='Basketball club confirms training preparations',
                slug='newer-other-sport-'+focus+'-'+str(i),sport='basketball',ai_generated=True,
                content='The basketball club has confirmed its preparations.',summary='Basketball preparation update.',
                published_at=stamp,source_url='https://example.test/other/'+focus+'/'+str(i),
                image_url='https://example.test/basketball.jpg')
            db.add(a);db.flush();ids.append(a.id)
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,
                resolved_sport='basketball',public_ok=True,quality_ok=True))
        db.commit()
        with caplog.at_level(logging.INFO,logger='ninkosports.public_index'):
            assert repair_recent_gossip_news(db,limit=600)==expected
        assert 'News editorial repair scanned=600' in caplog.text
        tax=db.query(ArticleTaxonomyResolution).filter_by(article_id=bad_id).one()
        assert tax.public_ok is (not bool(expected))
        assert db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id.in_(ids[1:]),ArticleTaxonomyResolution.public_ok.is_(True)).count()==601
        assert db.get(Article,bad_id).content=='Original retained copy, never rewritten by the selector.'
        assert db.get(Article,bad_id).published_at==stamp-timedelta(hours=24)
        assert db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).count()==expected
        if expected:assert repair_recent_gossip_news(db,limit=600)==0
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close()
