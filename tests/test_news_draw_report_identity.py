from datetime import datetime,timedelta,timezone
import pytest
from bot.news_report_similarity import draw_report_signature,same_draw_report
from bot.dedupe import existing_near_duplicate
from database import SessionLocal
from models import Article,ArticleTaxonomyResolution,NewsIncident
from taxonomy_resolver import RESOLVER_VERSION
from public_index import repair_recent_duplicate_news

T1="France and Italy draw as Olise's goal is cancelled out in Nations League"
T2='France and Italy share points after a second-half equaliser'
B1='France were held by Italy in a Nations League football match. Olise put the hosts ahead and Bastoni restored parity.\n\nBoth teams finished with a point after their goals.'
B2='France and Italy shared points in their football meeting. Olise scored after the interval.\n\nA defensive error allowed Bastoni to level and the match ended as a draw.'
NOW=datetime(2026,10,3,5,tzinfo=timezone.utc)


def signature(title=T1,body=B1):return draw_report_signature(title,body)


def test_participants_scorers_and_source_window_identify_the_same_report():
    left=signature();right=signature(T2,B2)
    assert left and right
    assert left.participants==('france','italy') and left.scorers=={'olise','bastoni'}
    assert same_draw_report(left,right,NOW,NOW-timedelta(minutes=12))
    assert same_draw_report(left,right,NOW.replace(tzinfo=None),NOW)

@pytest.mark.parametrize('delta',[-49,-25,25,49])
def test_different_dates_cannot_merge_a_rematch(delta):
    assert not same_draw_report(signature(),signature(),NOW,NOW+timedelta(hours=delta))

@pytest.mark.parametrize('title,body',[
    ('Zidane records first France draw against Italy',B1),
    ('France and Italy draw as manager praises midfield',B1),
    ('France and Italy draw: player ratings',B1),
    ('France and Italy draw reaction',B1),
    ('France and Italy could draw in Nations League',B1),
    ('France and Italy share points: injury update',B1),
    ('France and Italy draw: fans react to ticket policy',B1),
    (T1,'Donnarumma said Italy played with the right attitude. '+B1),
    (T1,''),(T1,'\n\n  '),
    (T1,'Olise scored the goal. The teams shared points.'),
    (T1,B1.replace('Bastoni restored parity','Bastoni made a clearance')),
    ('France and Italy draw in futsal',B1),
    ('France and Italy draw in beach soccer',B1),
])
def test_reactions_previews_other_formats_and_missing_facts_have_no_report_key(title,body):
    assert draw_report_signature(title,body) is None

@pytest.mark.parametrize('title,body',[
    ('France women and Italy women draw',B1),
    ('France U21 and Italy U21 draw',B1),
    (T1.replace('Italy','England'),B1),
    (T1,B1.replace('Bastoni','Kean')),
    ('France and Italy draw 2-2',B1),
    ('France and Italy draw in FIFA World Cup',B1.replace('Nations League','World Cup')),
])
def test_shared_headline_does_not_override_gender_age_participants_scorers_score_or_tournament(title,body):
    assert not same_draw_report(signature('France and Italy draw 1-1',B1),signature(title,body),NOW,NOW)


def test_secondary_game_scorers_do_not_identify_the_leading_match():
    body='France and Italy shared points.\n\nTheir match ended level.\n\nOlise scored elsewhere and Bastoni restored parity in another match.'
    assert signature(T1,body) is None


def test_unknown_or_mixed_score_window_fails_closed():
    assert signature(T1,B1.replace('France were held','After a 3-0 result France were held')) is None
    assert signature(T1,B1+'\n\nIn another match Belgium won 3-0.')
    assert not same_draw_report(signature(),signature(),None,NOW)


def test_ingest_and_existing_public_repair_retain_rows_and_permanent_incident():
    db=SessionLocal();ids=[]
    try:
        now=datetime.utcnow()
        for idx,(title,body) in enumerate([(T1,B1),(T2,B2)]):
            a=Article(title=title,content=body,ai_generated=True,
                external_id=f'https://fixture.example/draw-identity-{idx}',slug=f'draw-identity-{idx}',
                created_at=now+timedelta(seconds=idx),published_at=now-timedelta(minutes=idx),
                sport='football',image_url='https://fixture.example/photo.jpg')
            db.add(a);db.flush();ids.append(a.id)
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,resolved_sport='football',public_ok=True))
            if idx==0:
                assert existing_near_duplicate(db,T2,now,body=B2,sport='football').id==a.id
                assert existing_near_duplicate(db,T2,now,body=B2,sport='basketball') is None
        db.commit()
        assert repair_recent_duplicate_news(db)>=1
        assert db.query(Article).filter(Article.id.in_(ids)).count()==2
        visible=db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids),ArticleTaxonomyResolution.public_ok.is_(True)).all()
        assert len(visible)==1 and visible[0].article_id==ids[0]
        incident=db.query(NewsIncident).filter_by(article_id=ids[1],reason_code='duplicate_story',status='open').one()
        assert incident
        original=[(db.get(Article,i).title,db.get(Article,i).content,db.get(Article,i).published_at) for i in ids]
        repair_recent_duplicate_news(db)
        assert [(db.get(Article,i).title,db.get(Article,i).content,db.get(Article,i).published_at) for i in ids]==original
        assert db.query(NewsIncident).filter_by(article_id=ids[1],reason_code='duplicate_story',status='open').count()==1
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close()
