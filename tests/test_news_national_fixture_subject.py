from datetime import date
from types import SimpleNamespace
import pytest
from bot.news_football_subjects import headline_national_fixture,literal_country_mentions
from bot import news_football_sections as sections

@pytest.mark.parametrize('title',[
    'Canada seek another step forward in Montréal against Peru | MLSSoccer.com',
    'Canada host Peru in friendly football match',
    'Peru face Canada in international football',
    'France and Italy draw in Nations League',
    'Northern Ireland beat Ukraine in Nations League',
    'Bosnia and Herzegovina host Sweden in football',
    "Canada women host Peru in football friendly",'Canada U17 face Peru',
])
def test_explicit_national_fixture_is_a_headline_subject(title):
    assert headline_national_fixture(title)

@pytest.mark.parametrize('title',[
    'Austria Vienna signs midfielder after Canada camp',
    'Canada Soccer appoints new coach from Peru',
    'Canada and Peru discuss national trade policy',
    'Club in Canada may host Peru next summer',
    'Samuel Piette returns to Montréal after Canada visit to Peru',
    'France, Italy and England prepare for matches',
    'Canada confirms squad for upcoming international matches',
    'Canada midfielder joins Peru club',
])
def test_country_presence_alone_is_not_a_national_fixture(title):
    assert not headline_national_fixture(title)


def test_embedded_country_is_not_counted_twice():
    assert {m[2] for m in literal_country_mentions('Northern Ireland host France')}=={'northern ireland','france'}
    assert {m[2] for m in literal_country_mentions('DR Congo face Senegal')}=={'dr congo','senegal'}


def story(title,body='CF Montréal captain Samuel Piette knows Stade Saputo better than anyone else.'):
    return SimpleNamespace(title=title,summary=body,content=body+'\n\nCanada meet Peru at the venue.',published_at='2026-10-03',source_url='https://www.mlssoccer.com/news/canada-seek-another-step-forward-in-montreal-against-peru')


def test_main_national_fixture_outranks_club_biography(monkeypatch):
    monkeypatch.setattr(sections,'_club_section',lambda *args,**kwargs:'usa-mls')
    article=story('Canada seek another step forward in Montréal against Peru | MLSSoccer.com')
    assert sections.football_news_section(article,today=date(2026,10,3))=='football-national-teams'

@pytest.mark.parametrize('title,expected',[
    ('Canada women face Peru in football friendly','football-women'),
    ('Canada U17 face Peru in football friendly','football-youth'),
    ('France and Italy draw in UEFA Nations League','uefa-nations-league'),
])
def test_gender_age_and_exact_tournament_identity_survive(monkeypatch,title,expected):
    monkeypatch.setattr(sections,'_club_section',lambda *args,**kwargs:'usa-mls')
    assert sections.football_news_section(story(title),today=date(2026,10,3))==expected


def test_menu_repair_does_not_admit_held_or_other_sport_articles(monkeypatch):
    monkeypatch.setattr(sections,'_club_section',lambda *args,**kwargs:'usa-mls')
    for public,sport,ai in [(False,'football',True),(True,'basketball',True),(True,'football',False)]:
        a=story('Canada host Peru in football friendly');a.ai_generated=ai;a.league='usa-mls'
        tax=SimpleNamespace(public_ok=public,resolved_sport=sport,resolved_competition='usa-mls')
        assert not sections.assign_public_football_section(a,tax)
        assert a.league=='usa-mls'
