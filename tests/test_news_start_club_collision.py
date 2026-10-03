from datetime import date
from types import SimpleNamespace
import pytest
from bot import news_football_sections as sections
from bot.news_football_priority import candidate_football_section

@pytest.fixture
def catalogue(monkeypatch):
    period={'valid_from':'2026-10-01','valid_until':'2026-10-05'}
    rows={'norway-eliteserien':{**period,'clubs':['Start','Brann','Viking','Molde']},
          'england-premier-league':{**period,'clubs':['Chelsea','Arsenal','Liverpool','Everton']}}
    monkeypatch.setattr(sections,'memberships_for_news',lambda:rows)
    monkeypatch.setattr(sections,'_CLUBS',{'valid_from':'2026-10-01','valid_until':'2026-12-31','leagues':{}})

def club(title,summary=''):
    a=SimpleNamespace(published_at='2026-10-03T01:00:00')
    return sections._club_section(sections._norm(title),sections._norm(summary),a,False,date(2026,10,3))

@pytest.mark.parametrize('title',[
    'Blackburn Rovers star has excellent start to the season',
    'Doncaster Rovers winger looks for improvement after tough start',
    'Club confirms start of training programme',
    'The club start preparations for the new season',
    'A fresh start for the midfielder',
    'Players start football club training today',
])
def test_common_start_does_not_select_a_norwegian_team(catalogue,title):
    assert club(title) is None

@pytest.mark.parametrize('title',[
    'IK Start confirm signing',
    'Start FC confirms training programme',
    "Start's manager confirms preparations",
    'Start’s goalkeeper returns to training',
])
def test_explicit_club_identity_still_uses_verified_membership(catalogue,title):
    assert club(title)=='norway-eliteserien'

def test_a_real_other_club_wins_instead_of_a_passing_start(catalogue):
    assert club('A new start for Chelsea midfielder')=='england-premier-league'
    assert club('Brann confirms preparations')=='norway-eliteserien'

def test_historical_body_and_ambiguous_start_cannot_create_queue_debt(catalogue):
    item={'title':'Blackburn Rovers player makes an excellent start','summary':'The winger discusses his current form.','_extracted':'He previously played in the 2. Bundesliga.','published_at':'2026-10-03'}
    before=dict(item)
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='germany-2-bundesliga'),today=date(2026,10,3)) is None
    assert item==before
