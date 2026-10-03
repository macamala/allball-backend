from types import SimpleNamespace
from datetime import date
import pytest
from bot import news_football_sections as sections
from bot.news_football_priority import candidate_football_section

@pytest.fixture
def clubs(monkeypatch):
    monkeypatch.setattr(sections,'_club_section',lambda title,*a:'england-championship' if 'burnley' in title else None)

@pytest.mark.parametrize('title',[
    'Burnley move to poach key figure from Serie A side',
    'Burnley appoint coach from a Serie A club',
    'Burnley sign forward from the Bundesliga team',
])
def test_other_clubs_league_does_not_steal_transfer_subject(clubs,title):
    a=SimpleNamespace(title=title,summary='',content='',published_at='2026-10-03')
    assert sections.football_news_section(a,today=date(2026,10,3))=='england-championship'

@pytest.mark.parametrize('title',[
    'Former Premier League mainstay is still without a club',
    'Former Serie A midfielder confirms retirement',
])
def test_primary_subject_rejection_is_not_undone_by_queue_fallback(monkeypatch,title):
    monkeypatch.setattr(sections,'_club_section',lambda *a:None)
    tag='england-premier-league' if 'Premier League' in title else 'italy-serie-a'
    item={'title':title,'summary':'','_extracted':'','published_at':'2026-10-03'}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league=tag)) is None

@pytest.mark.parametrize('title,league',[
    ('Serie A clubs confirm new rule','italy-serie-a'),
    ('Premier League transfers confirmed','england-premier-league'),
    ('Champions League club appoints new coach','uefa-champions-league'),
])
def test_real_current_competition_remains_explicit(title,league):
    assert sections._explicit(sections._norm(title))==league
