from datetime import date
from types import SimpleNamespace
import pytest
from bot import news_football_sections as sections
from bot.news_football_source_context import source_menu_association

@pytest.fixture
def clubs(monkeypatch):
    monkeypatch.setattr(sections,'memberships_for_news',lambda:{'finland-ykkosliiga':{'clubs':['KäPa','JIPPO'],'valid_from':'2026-10-01','valid_until':'2026-10-05'}})
    monkeypatch.setattr(sections,'_CLUBS',{'valid_from':'2026-10-01','valid_until':'2026-12-31','leagues':{}})

@pytest.mark.parametrize('title',['Francuzima je bod puna kapa','Kapa je puna za Italijane','Full KAPA of football news'])
def test_ordinary_foreign_word_is_not_a_finnish_club(clubs,title):
    a=SimpleNamespace(title=title,summary='',published_at='2026-10-03')
    assert sections._club_section(sections._norm(title),'',a,False,date(2026,10,3)) is None

@pytest.mark.parametrize('title',['KäPa sign a new midfielder','Kapa FC confirms signing',"Kapa’s coach discusses training"])
def test_explicit_native_or_qualified_club_remains(clubs,title):
    a=SimpleNamespace(title=title,summary='',published_at='2026-10-03')
    assert sections._club_section(sections._norm(title),'',a,False,date(2026,10,3))=='finland-ykkosliiga'

ROM='https://liga2.prosport.ro/seria-1/scm-ramnicu-valcea-si-a-luat-revansa-in-fata-resitei-pentru-esecul-din-campionat-19402745'
def test_exact_editorial_category_only_associates_own_article():
    assert source_menu_association(ROM)=='romania-liga-2'
    for url in [ROM.replace('/seria-1/','/liga-3/'),ROM.replace('liga2.prosport.ro','evil.example'),ROM.rsplit('-',1)[0], 'https://liga2.prosport.ro/seria-1/']:
        assert source_menu_association(url) is None

@pytest.mark.parametrize('title,expected',[('Club confirms new coach','romania-liga-2'),('UEFA Champions League draw held','uefa-champions-league'),('Romania national team selects squad','football-national-teams'),('Club U12 team wins trophy','football-youth'),("Women's football players train",'football-women')])
def test_country_desk_never_overrides_primary_subject(title,expected):
    a=SimpleNamespace(title=title,summary='',content='',source_url=ROM,published_at='2026-10-03')
    assert sections.football_news_section(a,today=date(2026,10,3))==expected
