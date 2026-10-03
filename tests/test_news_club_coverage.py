from collections import Counter
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from bot.news_club_coverage import ClubCoverage, load_club_coverage, normalize

NOW=datetime(2026,10,3,7,tzinfo=timezone.utc)
EPL='england-premier-league';ESP='spain-la-liga';SRB='serbia-superliga'

def roster(clubs):
    return {'clubs':clubs,'valid_from':'2026-10-02','valid_until':'2026-10-05','observed_at':NOW.isoformat()}

def coverage():
    return ClubCoverage({EPL:roster(['Manchester City','Everton','Arsenal','AFC Bournemouth','Fulham']),
        ESP:roster(['Real Madrid','Barcelona','Valencia','Getafe']),
        SRB:roster(['FK Crvena Zvezda','Partizan Beograd','Vojvodina','Čukarički']),
        'norway-eliteserien':roster(['Start','Brann','Molde','Viking'])},now=NOW)

def item(id,title,league=EPL,**extra):
    return {'id':id,'title':title,'summary':'','league':league,'tier':1,'sport':'football',
        'url':f'https://publisher.example/news/{id}','published_at':NOW-timedelta(hours=1),**extra}

def order(c,items):
    return c.balance(items,section=lambda r:r['league'],priority=lambda r:r['tier'])

@pytest.mark.parametrize('age,good',[(0,True),(71,True),(73,False),(-1,False)])
def test_roster_age_cannot_be_refreshed_by_constructing_coverage(age,good):
    data=roster(['Everton','Arsenal','Fulham','Chelsea']);data['observed_at']=(NOW-timedelta(hours=age)).isoformat()
    c=ClubCoverage({EPL:data},now=NOW)
    assert bool(c.clubs)==good

@pytest.mark.parametrize('field,value',[('valid_from','2026-11-01'),('valid_until','2026-10-02'),('observed_at','invalid'),('clubs',['Only One'])])
def test_wrong_period_missing_identity_or_malformed_roster_stays_unknown(field,value):
    data=roster(['Everton','Arsenal','Fulham','Chelsea']);data[field]=value
    assert not ClubCoverage({EPL:data},now=NOW).clubs

@pytest.mark.parametrize('title,expected',[
    ('Manchester City appoint coach',('manchester city',)),
    ('Everton defeat Arsenal',('everton','arsenal')),
    ('Bournemouth appoint coach',('afc bournemouth',)),
    ('FulhamExtra win training game',()),
    ('City confirms signing',()),
    ('Manchester City Women appoint manager',()),
    ('Arsenal U18 appoint manager',()),
    ('Everton academy changes',()),
    ('Former Arsenal player discusses retirement',()),
    ('Liverpool beat Real Madrid',()),
    ('Everton Arsenal Fulham Bournemouth roundup',()),
])
def test_primary_current_identity_is_exact_and_separated(title,expected):
    assert coverage().subjects(item(1,title),EPL)==expected


def test_history_recommendations_and_unused_source_hints_do_not_count_as_club_news():
    c=coverage();row=item(1,'Club confirms manager',content='Arsenal Everton Manchester City',feed={'club':'Arsenal'})
    assert c.subjects(row,EPL)==()
    row['summary']='The club confirmed the appointment.\n\nThe coach formerly worked at Arsenal.'
    assert c.subjects(row,EPL)==()
    row['summary']='Everton confirmed a new manager.'
    assert c.subjects(row,EPL)==('everton',)


def test_normalized_cyrillic_and_accents_keep_canonical_club_identity():
    c=coverage()
    assert c.subjects(item(1,'Црвена звезда потврдила појачање',SRB),SRB)==('fk crvena zvezda',)
    assert c.subjects(item(2,'Čukarički confirm a new coach',SRB),SRB)==('cukaricki',)
    assert c.subjects(item(3,'A fresh start for the players','norway-eliteserien'),'norway-eliteserien')==()


def test_unknown_or_duplicate_alias_cannot_become_a_second_team():
    data={EPL:roster(['Arsenal','ARSENAL','Everton','Fulham','AFC Bournemouth'])}
    c=ClubCoverage(data,now=NOW)
    assert len(c.clubs[EPL])==4
    assert c.subjects(item(1,'Bournemouth and AFC Bournemouth confirm schedule'),EPL)==('afc bournemouth',)


def test_current_roster_overrides_old_static_aliases_and_does_not_imagine_clubs():
    c=coverage()
    assert c.subjects(item(1,'Chelsea name their manager'),EPL)==()
    assert c.subjects(item(2,'Real Madrid appoint a coach'),ESP)==('real madrid',)
    assert c.subjects(item(3,'Real Madrid appoint a coach'),EPL)==()


def test_count_once_in_rolling_utc_and_rebuild_across_restarts():
    rows=[item(1,'Everton name manager'),item(1,'Everton name manager'),
          item(2,'Arsenal name manager',published_at=NOW-timedelta(days=2)),
          item(3,'Fulham name manager',published_at=NOW-timedelta(days=8)),
          item(4,'Bournemouth name manager',published_at=NOW+timedelta(minutes=1))]
    c=coverage();d=coverage()
    for row in rows:c.observe(row);d.observe(row)
    assert c.count24[(EPL,'everton')]==1 and c.count7[(EPL,'everton')]==1
    assert c.count24[(EPL,'arsenal')]==0 and c.count7[(EPL,'arsenal')]==1
    assert c.count7[(EPL,'fulham')]==0 and c.count7[(EPL,'afc bournemouth')]==0
    assert c.report()==d.report()


def test_uncovered_teams_beat_city_repetition_but_no_article_is_removed():
    c=coverage()
    for n in range(10):c.observe(item(n,'Manchester City name new signing'))
    rows=[item('c1','Manchester City squad update'),item('c2','Manchester City coach update'),
          item('e1','Everton name manager'),item('a1','Arsenal name manager'),
          item('e2','Everton training update'),item('b1','Bournemouth name manager')]
    original=deepcopy(rows);out=order(c,rows)
    assert {r['id'] for r in out[:3]}=={'e1','a1','b1'}
    assert [r['id'] for r in out].index('e2')<[r['id'] for r in out].index('c2')
    assert Counter(r['id'] for r in out)==Counter(r['id'] for r in rows)
    assert rows==original


def test_projected_slots_alternate_teams_and_unnamed_reporting_keeps_opportunity():
    c=coverage();rows=[item('c1','Manchester City squad update'),item('c2','Manchester City coach update'),
        item('c3','Manchester City training update'),item('e1','Everton name manager'),
        item('e2','Everton coach update'),item('topic','Football federation announces rules')]
    out=order(c,rows)
    assert out[0]['id']=='c1' and out[1]['id']=='e1'
    assert out[3]['id']=='topic'
    assert Counter(r['id'] for r in out)==Counter(r['id'] for r in rows)


def test_league_slots_zvezda_priority_other_sports_and_single_club_are_preserved():
    c=coverage();rows=[item('z','Crvena Zvezda update',SRB,tier=2),
        item('a','Manchester City update'),item('v','Valencia update',ESP,tier=0),
        item('e','Everton update'),item('x','Basketball update','nba',sport='basketball',tier=0)]
    out=order(c,rows)
    assert [(r['league'],r['tier']) for r in rows]==[(r['league'],r['tier']) for r in out]
    assert out[0] is rows[0] and out[-1] is rows[-1]
    assert order(c,[])==[]
    assert order(c,rows[:1])==rows[:1]


def test_report_never_confuses_candidate_or_mention_with_a_published_story():
    c=coverage();c.observe(item(1,'Manchester City update'))
    report=c.report([item('e','Everton update'),item('a','Arsenal update')])
    rows={r['club_key']:r for r in report['rows'] if r['league']==EPL}
    assert rows['everton']['status']=='candidate_waiting' and rows['everton']['articles_7d']==0
    assert rows['fulham']['status']=='no_current_candidate'
    assert rows['manchester city']['status']=='published_24h'
    assert report['clubs_with_24h_news']==1 and report['clubs_with_candidates']==2
    assert report['complete'] is False


def test_real_public_database_filter_excludes_held_wrong_sport_missing_image_and_future(monkeypatch):
    from sqlalchemy import create_engine,event
    from sqlalchemy.orm import Session
    from models import Base,Article,ArticleTaxonomyResolution as Tax
    from taxonomy_resolver import RESOLVER_VERSION
    from bot import news_football_memberships as members
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    monkeypatch.setattr(members,'memberships_for_news',lambda now:{EPL:roster(['Arsenal','Everton','Fulham','Chelsea'])})
    with Session(engine) as db:
        variations=[{}, {'public_ok':False},{'resolved_sport':'basketball'}, {'hero_media_kind':'LOGO'},
            {'image_url':''},{'resolver_version':'stale'},{'ai_generated':False},{'age':-1},{'age':200}]
        for n,opts in enumerate(variations,1):
            db.add(Article(id=n,title='Everton appoint manager',summary='',sport='football',league=EPL,
                image_url=opts.get('image_url','https://photos.example/news.jpg'),ai_generated=opts.get('ai_generated',True),
                published_at=(NOW-timedelta(hours=opts.get('age',1))).replace(tzinfo=None)))
            db.add(Tax(article_id=n,public_ok=opts.get('public_ok',True),resolved_sport=opts.get('resolved_sport','football'),
                resolved_competition=EPL,resolver_version=opts.get('resolver_version',RESOLVER_VERSION),hero_media_kind=opts.get('hero_media_kind','EDITORIAL_PHOTO')))
        db.commit();writes=[]
        @event.listens_for(engine,'before_cursor_execute')
        def record(conn,cursor,statement,parameters,context,executemany):
            if not statement.lstrip().lower().startswith('select'):writes.append(statement)
        c=load_club_coverage(db,now=NOW)
        assert c.count24[(EPL,'everton')]==1 and c.scanned==1
        assert not writes


def test_fair_queue_calls_team_balancer_only_after_normal_source_admission():
    from bot.news_policy import fair_news_queue
    c=coverage();c.observe(item(1,'Manchester City update'))
    rows=[item('c','Manchester City Premier League update'),item('e','Everton Premier League update'),
        item('old','Fulham Premier League update',published_at=NOW-timedelta(days=2)),
        item('wrong','Arsenal Premier League basketball update',sport='basketball')]
    tags=lambda i:SimpleNamespace(sport=i['sport'],league=i['league'])
    out,rejected=fair_news_queue(rows,tags,now=NOW,football_inventory={EPL:4},football_club_coverage=c,allowed_sports={'football'},max_age_hours=24)
    assert [r['id'] for r in out]==['e','c']
    assert rejected['stale_publication']==1 and rejected['outside_editorial_focus']==1


@pytest.mark.parametrize('title',['A strong start confirmed by the coach','Players start training today','A new start for the striker','Good start announced by the board'])
def test_generic_start_does_not_gain_a_club_identity_from_a_following_verb(title):
    assert coverage().subjects(item(1,title,'norway-eliteserien'),'norway-eliteserien')==()


@pytest.mark.parametrize('seed',range(12))
def test_reordering_is_stable_lossless_and_keeps_league_tier_schedule(seed):
    import random
    rng=random.Random(seed);c=coverage()
    names={EPL:['Arsenal','Everton','Manchester City','Bournemouth'],ESP:['Real Madrid','Barcelona','Valencia','Getafe']}
    rows=[]
    for n in range(60):
        league=rng.choice([EPL,ESP]);club=rng.choice(names[league]);rows.append(item(n,club+' confirm preparations',league,tier=rng.choice([0,1])))
    original=deepcopy(rows);out=order(c,rows)
    assert Counter(r['id'] for r in out)==Counter(r['id'] for r in rows)
    assert [(r['league'],r['tier']) for r in out]==[(r['league'],r['tier']) for r in rows]
    assert out==order(c,rows) and rows==original


def test_first_priority_is_preserved_but_followups_cannot_reserve_every_opening_slot():
    c=coverage()
    rows=[item('z1','Crvena Zvezda update',SRB,tier=2),item('z2','Crvena Zvezda other update',SRB,tier=2),
          item('a','Arsenal update'),item('z3','Crvena Zvezda Champions League update','uefa-champions-league',tier=2)]
    before=deepcopy(rows);priorities={r['url']:r['tier'] for r in rows}
    result=c.bounded_priorities(rows,priorities,identity=lambda r:r['url'],section=lambda r:r['league'])
    assert result[rows[0]['url']]==2 and result[rows[1]['url']]==0 and result[rows[3]['url']]==1
    assert rows==before and priorities=={r['url']:r['tier'] for r in rows}


def test_each_waiting_club_gets_a_first_chance_before_repeats():
    c=coverage()
    c.observe(item(1,'Arsenal update'));c.observe(item(2,'Everton update'))
    rows=[item('m1','Manchester City update'),item('m2','Manchester City update two'),
          item('b1','Bournemouth update'),item('b2','Bournemouth update two'),
          item('a','Arsenal update'),item('e','Everton update')]
    out=order(c,rows)
    assert len({club for row in out[:4] for club in c.subjects(row,EPL)})==4


def test_portuguese_sub23_is_not_first_team_coverage():
    assert coverage().subjects(item(1,'Arsenal sub-23 confirma preparacao'),EPL)==()
