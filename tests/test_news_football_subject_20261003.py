from datetime import date
from types import SimpleNamespace
import pytest
from bot.news_football_sections import football_news_section, assign_public_football_section

def story(title,summary='',content=''):
    return SimpleNamespace(title=title,summary=summary,content=content,
        published_at='2026-10-02T13:00:00',ai_generated=True,league='germany-bundesliga')

@pytest.mark.parametrize('marker',['Frauen','Damen','Feminine','Féminines','Femenina','Femenino','Femminile','Ženska'])
def test_womens_marker_cannot_populate_a_mens_domestic_menu(marker):
    a=story(f'Eintracht Frankfurt {marker} host Bayern in Bundesliga football')
    assert football_news_section(a,today=date(2026,10,3))=='football-women'

@pytest.mark.parametrize('event',['Asian Games','Asiad','Olympic Games','AFC Asian Cup','Copa America','Africa Cup of Nations','CONCACAF Gold Cup'])
def test_womens_current_event_beats_incidental_body_world_cup(event):
    a=story(f'South Korea women defeat China to win bronze at {event}',
        'The team won their bronze-medal football match.',
        "The coach remembered the FIFA Women's World Cup. Players also discussed the Women's Champions League.")
    assert football_news_section(a,today=date(2026,10,3))=='football-women'

@pytest.mark.parametrize('age',['U16','U17','U19','U20','U21','U23','Under-23'])
def test_youth_regional_events_do_not_inherit_senior_world_cup(age):
    a=story(f'South Korea {age} win at Asian Games',content='The squad discussed the FIFA World Cup.')
    assert football_news_section(a,today=date(2026,10,3))=='football-youth'

def test_senior_regional_event_uses_national_topic_not_world_cup():
    a=story('Japan wins Asian Cup match',content='The manager previously coached in the World Cup.')
    assert football_news_section(a,today=date(2026,10,3))=='football-national-teams'

@pytest.mark.parametrize('title,expected',[
    ('Bayern win Bundesliga football match','germany-bundesliga'),
    ('AFC Champions League Elite draw confirmed','afc-champions-league-elite'),
    ("Chelsea win UEFA Women's Champions League match",'uefa-womens-champions-league'),
    ('England women select World Cup playoff squad','fifa-womens-world-cup'),
    ('England wins UEFA Nations League match','uefa-nations-league'),
])
def test_known_competition_routes_are_retained(title,expected):
    assert football_news_section(story(title),today=date(2026,10,3))==expected

def test_published_frauen_incident_is_repaired_without_copy_or_date_mutation():
    a=story('Eintracht Frankfurt Frauen host unbeaten FC Bayern in Bundesliga football',content='Original football reporting.')
    before=dict(vars(a));tax=SimpleNamespace(public_ok=True,resolved_sport='football',resolved_competition='germany-bundesliga')
    assert assign_public_football_section(a,tax)
    assert a.league==tax.resolved_competition=='football-women'
    for key in ('title','summary','content','published_at'):assert getattr(a,key)==before[key]
    assert tax.public_ok and not assign_public_football_section(a,tax)

@pytest.mark.parametrize('public,sport,ai',[(False,'football',True),(True,'basketball',True),(True,'football',False)])
def test_menu_repair_cannot_admit_held_or_nonfootball_content(public,sport,ai):
    a=story('Eintracht Frankfurt Frauen host Bayern in Bundesliga football');a.ai_generated=ai
    tax=SimpleNamespace(public_ok=public,resolved_sport=sport,resolved_competition=a.league)
    assert not assign_public_football_section(a,tax)
    assert a.league=='germany-bundesliga'
