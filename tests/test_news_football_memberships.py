from datetime import datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace
import pytest
from bot import news_football_memberships as m
from bot.news_football_sections import football_news_section
NOW = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)

def board(key='poland-ekstraklasa'):
    return {'competition': {'id':key, 'sport':'football'}, 'stale':False, 'available':True,
            'season':'2026/2027','updated_at':NOW.isoformat(),
            'rows':[{'team':name,'team_id':str(i)} for i,name in enumerate(['Górnik Zabrze','Legia Warszawa','Lech Poznań','Raków Częstochowa'])]}

@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(m, '_ENTRIES', {})
    monkeypatch.setattr(m, '_LAST_REFRESH',float('-inf'))

@pytest.mark.parametrize('field,value', [('stale',True),('available',False),('season','2025/2026'),('season','2027/2028'),('updated_at','2026-10-02T08:00:00'),('updated_at',(NOW-timedelta(days=4)).isoformat()),('updated_at',(NOW+timedelta(hours=1)).isoformat())])
def test_rejects_unverified_or_wrong_time(field,value):
    data=board();data[field]=value
    assert m.parse_membership('poland-ekstraklasa',data,now=NOW) is None

def test_rejects_wrong_sport_and_cross_country_serieb():
    data=board('football-bra-s-rie-b')
    assert m.parse_membership('italy-serie-b',data,now=NOW) is None
    data=board();data['competition']['sport']='basketball'
    assert m.parse_membership('poland-ekstraklasa',data,now=NOW) is None
    assert m.parse_membership('uefa-champions-league',board('uefa-champions-league'),now=NOW) is None

def test_duplicates_groups_do_not_duplicate_memberships():
    data=board();data['rows']*=2
    entry=m.parse_membership('poland-ekstraklasa',data,now=NOW)
    assert len(entry['clubs'])==4
    assert entry['data_key']=='poland-ekstraklasa'

def test_refresh_is_read_only_bounded_and_six_hour_cached(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{'poland-ekstraklasa':{}})
    calls=[]
    def get(league,key): calls.append((league,key));return board(key)
    result=m.refresh_football_news_memberships(now=NOW,get=get)
    assert result['leagues']==1
    assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='cached'
    assert calls==[('poland-ekstraklasa','poland-ekstraklasa')]
    assert not m.memberships_for_news(NOW+timedelta(days=4))
    copy=m.memberships_for_news(NOW);copy['poland-ekstraklasa']['clubs'].clear()
    assert len(m.memberships_for_news(NOW)['poland-ekstraklasa']['clubs'])==4

def test_short_outage_does_not_erase_good_memberships(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{'poland-ekstraklasa':{}})
    m.refresh_football_news_memberships(now=NOW,get=lambda a,b:board())
    def failure(*args):raise RuntimeError('offline')
    assert m.refresh_football_news_memberships(now=NOW,get=failure,force=True)['leagues']==1
    assert m.refresh_football_news_memberships(now=NOW+timedelta(days=4),get=failure,force=True)['leagues']==0

def test_new_club_headline_routes_to_verified_league_without_changing_text(monkeypatch):
    entry=m.parse_membership('poland-ekstraklasa',board(),now=NOW)
    monkeypatch.setattr(m,'_ENTRIES',{'poland-ekstraklasa':entry})
    article=SimpleNamespace(title='Górnik Zabrze appoint a new head coach',summary='The club announced the coaching change.',content='The football club confirmed the appointment.',published_at=NOW)
    from bot import news_football_sections as sections
    monkeypatch.setattr(sections, 'memberships_for_news', lambda: m.memberships_for_news(NOW))
    before=vars(article).copy()
    assert football_news_section(article,today=NOW.date())=='poland-ekstraklasa'
    assert vars(article)==before
    article.title='Górnik Zabrze women appoint a new head coach'
    assert football_news_section(article,today=NOW.date())=='football-women'
    article.title='Górnik Zabrze under-19 team appoint a new head coach'
    assert football_news_section(article,today=NOW.date())=='football-youth'

def test_new_module_has_no_database_or_write_endpoint():
    import inspect
    source=inspect.getsource(m)
    for bad in ('SessionLocal','execute(','.post(','.put(','.delete(','.commit(', 'collector.run'):
        assert bad not in source
