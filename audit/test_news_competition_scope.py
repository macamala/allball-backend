from datetime import date, datetime, timezone
from types import SimpleNamespace
import pytest
from bot import news_fact_guard as guard
from bot import news_football_sections as sections
from bot.classify import Classification

@pytest.mark.parametrize('label', [
    'AFC Champions League', 'AFC Champions League Elite', 'AFC Champions League Two',
    'CAF Champions League', 'African Champions League', 'CONCACAF Champions League',
    'OFC Champions League', 'Asian Champions League', "Women's Champions League",
    'UEFA Women’s Champions League', 'UEFA Youth Champions League', 'Champions League Elite',
])
def test_a_qualified_other_event_is_not_evidence_of_the_mens_uefa_event(label):
    assert not guard.competition_in_source('uefa-champions-league', label)
    assert sections._explicit(sections._norm(label)) != 'uefa-champions-league'

@pytest.mark.parametrize('text', ['UEFA Champions League match', 'Champions League match',
                                 'AFC Champions League and UEFA Champions League are separate.'])
def test_explicit_uefa_evidence_remains_available(text):
    assert guard.competition_in_source('uefa-champions-league',text)

@pytest.mark.parametrize('key,text',[
    ('afc-champions-league-elite','AFC Champions League Elite draw'),
    ('caf-champions-league','CAF Champions League draw'),
    ('uefa-womens-champions-league',"UEFA Women's Champions League draw")])
def test_the_correct_qualified_competition_still_matches(key,text):
    assert guard.competition_in_source(key,text)

@pytest.mark.parametrize('league,text',[
    ('uefa-nations-league','CONCACAF Nations League final'),
    ('fifa-world-cup','FIFA Club World Cup final'),
    ('fifa-world-cup',"FIFA Women's World Cup final"),
])
def test_other_bare_labels_cannot_discard_their_qualifiers(league,text):
    assert not guard.competition_in_source(league,text)

@pytest.mark.parametrize('classified,expected',[
    ('football-international',None),
    ('football-world',None),
    ('england-premier-league',None),
    ('spain-la-liga','draft_competition_mismatch:spain-la-liga'),
])
def test_unknown_competition_is_not_a_positive_contradiction(monkeypatch,classified,expected):
    from bot.taxonomy import BROAD_LEAGUE
    if classified=='football-world':classified=BROAD_LEAGUE['football']
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    monkeypatch.setattr('bot.classify.classify_article',lambda *args,**kwargs:Classification('football',classified,None,'high','test'))
    # This test isolates the classification contradiction predicate only; all
    # existing source facts and semantic validator gates still run in production.
    reason=guard.fact_lock_reason({'title':'Coach discusses preparations','body':'The football coach discussed preparations.'},
        'Coach discusses preparations','The football coach discussed preparations.',
        expected_sport='football',expected_league='england-premier-league')
    assert reason==expected


def test_a_writer_cannot_turn_an_afc_source_into_uefa(monkeypatch):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    reason=guard.fact_lock_reason({'body':'The team will play in the UEFA Champions League.'},
        'Continental competition','The team will play in the AFC Champions League.',expected_sport='football')
    assert reason=='unsupported_competition:uefa-champions-league'


def test_published_daejeon_story_uses_verified_club_menu_not_uefa(monkeypatch):
    membership={'south-korea-k-league-1':{'season':'2026','valid_from':'2026-01-01','valid_until':'2026-12-31','clubs':{'Daejeon Hana Citizen':('Daejeon Hana Citizen',)},'as_of':datetime(2026,10,2,8,tzinfo=timezone.utc)}}
    monkeypatch.setattr(sections,'memberships_for_news',lambda:membership)
    article=SimpleNamespace(ai_generated=True,
        title='Daejeon Hana Citizen players target AFC Champions League qualification following recent football results',
        summary='Daejeon Hana Citizen players are aiming to qualify for the AFC Champions League again.',
        content='The team has upcoming matches against Jeonbuk and Gwangju at home.',
        published_at='2026-10-02T07:18:00',league='uefa-champions-league',source_url='https://www.kleagueunited.com/example')
    tax=SimpleNamespace(public_ok=True,resolved_sport='football',resolved_competition=article.league)
    before={k:getattr(article,k) for k in ['title','summary','content','published_at','source_url']}
    assert sections.football_news_section(article,today=date(2026,10,2))=='south-korea-k-league-1'
    assert sections.assign_public_football_section(article,tax)
    assert article.league==tax.resolved_competition=='south-korea-k-league-1'
    assert before=={k:getattr(article,k) for k in before} and tax.public_ok
    assert not sections.assign_public_football_section(article,tax)
