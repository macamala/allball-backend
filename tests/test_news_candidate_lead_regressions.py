from types import SimpleNamespace
from datetime import date
import pytest
from bot.news_football_priority import candidate_football_section
from bot.news_policy import non_article_news_reason
from bot import news_football_sections as sections

@pytest.mark.parametrize('title',[
    'Watford missed a midfield addition: Opinion',
    'Opinion: Watford missed a midfield addition',
    'Watford missed a midfield addition | OPINION',
    'Watford missed a midfield addition — Opinion',
    'Watford missed a midfield addition - Opinion',
])
def test_labelled_opinion_is_not_original_news_input(title):
    assert non_article_news_reason({'title':title})=='non_article_analysis'

@pytest.mark.parametrize('title',[
    'Doctor gives second opinion after winger injury',
    'Club confirms its position after public opinion survey',
    'Coach says players are entitled to an opinion',
])
def test_ordinary_reporting_can_mention_an_opinion(title):
    assert non_article_news_reason({'title':title}) is None

def test_full_rss_body_is_not_promoted_to_a_source_lead(monkeypatch):
    seen=[]
    monkeypatch.setattr(sections,'football_news_section',lambda article,**kwargs:seen.append(article) or 'england-championship')
    lead='The club confirmed its new signing following the completed agreement.'
    body=lead+'\n\n'+'He previously played in the 2. Bundesliga. '*15
    item={'title':'Blackburn Rovers confirm signing','summary':body,'_extracted':body,'_source_body_origin':'verified-full-rss','published_at':'2026-10-03','url':'https://the72.co.uk/2026/10/03/example/'}
    before=dict(item)
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='germany-2-bundesliga'))=='england-championship'
    assert seen[0].summary==lead and seen[0].content==body
    assert item==before

def test_old_club_league_in_rss_tail_does_not_steal_headline_club_queue(monkeypatch):
    monkeypatch.setattr(sections,'_club_section',lambda title,*args:'england-championship' if 'blackburn rovers' in title else None)
    body='The winger completed his move and will train with the current squad.\n\nHe previously played in the 2. Bundesliga.'
    item={'title':'Blackburn Rovers confirm signing','summary':body,'_extracted':body,'published_at':'2026-10-03'}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='germany-2-bundesliga'),today=date(2026,10,3))=='england-championship'

def test_unsupported_classifier_hint_does_not_invent_competition_debt(monkeypatch):
    monkeypatch.setattr(sections,'football_news_section',lambda *args,**kwargs:None)
    item={'title':'Club confirms preparations','summary':'The current squad will train together.\n\nHistorical reference to the 2. Bundesliga.'}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='germany-2-bundesliga')) is None

def test_explicit_current_lead_competition_survives(monkeypatch):
    monkeypatch.setattr(sections,'football_news_section',lambda *args,**kwargs:None)
    item={'title':'Club confirms preparations','summary':'The team prepares for its UEFA Champions League match.'}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league='uefa-champions-league'))=='uefa-champions-league'

@pytest.mark.parametrize('body',[
    'This is a complete first sentence. '+'More available source detail '*50,
    'A very long source statement '*60,
])
def test_overlong_unseparated_summary_does_not_cut_a_competition_qualifier(monkeypatch,body):
    seen=[];monkeypatch.setattr(sections,'football_news_section',lambda a,**kwargs:seen.append(a) or 'football-international')
    candidate_football_section({'title':'Club update','summary':body,'_extracted':body},SimpleNamespace(sport='football',league=None))
    assert seen[0].summary in {'','This is a complete first sentence.'}
    assert seen[0].content==body

def test_nonfootball_candidates_never_enter_football_queue():
    assert candidate_football_section({'title':'UEFA Champions League'},SimpleNamespace(sport='basketball',league='uefa-champions-league')) is None
