from types import SimpleNamespace
from datetime import date
import pytest
from bot.news_policy import non_article_news_reason
from bot.news_football_sections import football_news_section

@pytest.mark.parametrize('prefix',['Ticket news:','Ticket information:','Ticketing information —','Buy tickets:'])
def test_sales_bulletin_cannot_consume_original_news_slot(prefix):
    assert non_article_news_reason({'title':prefix+' Chelsea Legends vs Tottenham Legends'})=='non_article_ticket_promotion'

@pytest.mark.parametrize('title',['Chelsea ticket price rise challenged by supporters','Refunds confirmed after match cancellation','Police investigate fake tickets at final','Chelsea Legends beat Tottenham Legends in charity match'])
def test_actual_sporting_and_consumer_reporting_is_not_a_sales_bulletin(title):
    assert non_article_news_reason({'title':title}) is None

@pytest.mark.parametrize('age',[6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23])
@pytest.mark.parametrize('form',['U{}','Under-{}'])
def test_explicit_junior_team_does_not_enter_mens_domestic_menu(age,form):
    a=SimpleNamespace(title='Red Star Belgrade '+form.format(age)+' win youth tournament',summary='The squad won its final match.',content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))=='football-youth'

@pytest.mark.parametrize('title',['Red Star Belgrade sign 18-year-old forward','Chelsea won the title in 2018','Liverpool host Premier League game'])
def test_individual_age_or_calendar_year_is_not_a_youth_competition(title):
    a=SimpleNamespace(title=title,summary='',content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))!='football-youth'

@pytest.mark.parametrize('title',['Gudelj ranked in under-22 study','Under-18 rankings examine Liverpool player','Chelsea midfielder leads under-20 research'])
def test_age_limited_research_is_not_a_junior_team(title):
    a=SimpleNamespace(title=title,summary='',content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))!='football-youth'

@pytest.mark.parametrize('title,summary',[
    ('Crvena zvezda’s 2018 football team wins Ilija Pantelić Trophy','Crvena zvezda’s team born in 2018 won the tournament in Novi Sad.'),
    ('Club wins trophy','The squad of players born in 2014 won the event.'),
])
def test_birth_year_cohort_is_youth_without_changing_text_or_date(title,summary):
    a=SimpleNamespace(title=title,summary=summary,content='Original text.',published_at='2026-10-01',ai_generated=True,league='serbia-superliga')
    before=dict(vars(a))
    tax=SimpleNamespace(public_ok=True,resolved_sport='football',resolved_competition=a.league)
    from bot.news_football_sections import assign_public_football_section
    assert assign_public_football_section(a,tax)
    assert a.league==tax.resolved_competition=='football-youth'
    assert all(getattr(a,k)==before[k] for k in ['title','summary','content','published_at'])
    assert not assign_public_football_section(a,tax)

@pytest.mark.parametrize('summary',['Chelsea won the league in 2018.','The forward born in 2008 joined Chelsea.','The team born in 1990 played a reunion match.','The team born in 2030 won the tournament.'])
def test_individual_birth_year_and_legacy_reunions_are_not_youth(summary):
    a=SimpleNamespace(title='Chelsea football update',summary=summary,content='',published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))!='football-youth'

@pytest.mark.parametrize('host',['chelseafc.com','www.chelseafc.com'])
def test_ticket_source_retains_its_product_identity_after_rewrite(host):
    assert non_article_news_reason({'title':'Chelsea Legends will host Tottenham Legends','url':'https://'+host+'/en/news/article/ticket-news-chelsea-fc-legends-vs-tottenham-hotspur-legends'})=='non_article_ticket_promotion'

@pytest.mark.parametrize('url',['https://fakechelseafc.com/en/news/article/ticket-news-event','https://www.chelseafc.com/en/news/article/supporters-challenge-ticket-price-rise','https://www.chelseafc.com/en/news/article/legends-win-charity-match'])
def test_other_hosts_and_real_reporting_not_held_by_sales_path(url):
    assert non_article_news_reason({'title':'Club football update','url':url}) is None
