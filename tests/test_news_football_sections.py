from datetime import date
from types import SimpleNamespace
import pytest
from bot.news_football_sections import football_news_section, assign_public_football_section
from bot.news_policy import non_article_news_reason

TODAY=date(2026,9,30)
def section(title, summary='', content=''):
    return football_news_section(SimpleNamespace(title=title,summary=summary,content=content,
        published_at='2026-09-29T12:00:00'),today=TODAY)

@pytest.mark.parametrize('title,summary,body,expected',[
    ('England defeats Czechia 2:0 in Nations League match after red card','','','uefa-nations-league'),
    ('Czech Republic loses to England','A Nations League match ended 0:2.','','uefa-nations-league'),
    ('Kita signs sale agreement for FC Nantes','The Ligue 2 football club has a new owner.','','france-ligue-2'),
    ('Ryotaro Ito signs for Real Valladolid after failed medical at Blackburn Rovers',
     'He joins the Spanish second-division side.','Previously he had a move to Championship club Blackburn collapse.','spain-la-liga-2'),
    ('Mallorca goalkeeper hospitalized after accident','','','spain-la-liga-2'),
    ('Chelsea defender returns to Lyon in the Women’s Champions League','','','uefa-womens-champions-league'),
    ('Full-Backs drive goals in Women’s Champions League opener','','','uefa-womens-champions-league'),
    ('England women select squad for World Cup playoff against Greece','','','fifa-womens-world-cup'),
    ('Emma Hayes names squad for USWNT friendlies against Spain',
     'The United States women’s national team face defending World Cup champion Spain. NWSL standouts are included.','','football-women'),
    ('Arsenal fall to Chelsea while Putellas scores for London City',
     'Alexia Putellas scored for London City Lionesses.','','england-womens-super-league'),
    ('Chelsea midfielder Walsh praises win over Arsenal','Keira Walsh praised the team.','','england-womens-super-league'),
    ('Ethan Mbappé leaves France Under-21s match with injury','He was injured in a European Championship qualifier.','','uefa-under-21-euro'),
    ('Hungary wins memorial tournament','They defeated Serbia U-19.','','football-youth'),
    ('France U-twenty-one players injured','They played Estonia.','','football-youth'),
    ('Teleoptik sign defender for Mozzart Bet Prva Liga','','','serbia-prva-liga'),
    ('Heist stun Kortrijk in Croky Cup','','','belgium-cup'),
    ('Juventus seek shareholder mandate for capital increase','','','italy-serie-a'),
    ('Gudelj ranked in under-22 study','Red Star Belgrade’s Stefan Gudelj is eighth.','','serbia-superliga'),
    ('Parma appoint coach','The men’s first team has a new head coach.','','italy-serie-a'),
    ('Real Madrid left-back Mendy returns','The French international is recovering.','','spain-la-liga'),
    ('Paulinho joins Botafogo after seven years in Denmark','','','brazil-serie-a'),
    ('Spain’s squad returns to action','Spain’s national team has returned after the World Cup roster was announced.',
     'He recalled watching the World Cup from the sidelines and the World Cup win.','football-national-teams'),
    ('USMNT beats Chile','The national football team won.','He plays for Liverpool in the Premier League.','football-national-teams'),
    ('Prosecutors drop Bari liquidation request','The club meets financial conditions.',
     'They aim to build a squad capable of returning to Serie B.',None),
    ('Chema Andrés rules out Real Madrid return citing midfield depth','','',None),
    ('Chema Andrés rules out Real Madrid return','Brighton midfielder Chema Andrés says his former club has no need for him.','','england-premier-league'),
    ('Nicolo Zaniolo ruled out for three weeks','Udinese confirmed he was injured on Italy duty.',
     'The player was injured with the Italian national team.','italy-serie-a'),
    ('Liverpool FC Academy appoint new coach','','','football-youth'),
    ('Concacaf Nations League final announced','','',None),
    ('Arsenal prepare for FA Cup tie','','',None),
    ('England Women’s Blind Football captain prepares for European Championship','','',None),
    ('Real Madrid face Barcelona in UEFA Champions League','','','uefa-champions-league'),
    ('AFC Champions League Elite draw confirmed','','','afc-champions-league-elite'),
    ('Brazilian Serie B match decided','','','brazil-serie-b'),
    ('Austrian Bundesliga coach leaves','','','austria-bundesliga'),
    ('A club has a new coach','','Read more: Premier League Champions League La Liga',None),
])
def test_real_news_routing_boundaries(title, summary, body, expected):
    assert section(title,summary,body)==expected


def test_expired_club_directory_cannot_assign_a_future_season():
    a=SimpleNamespace(title='Juventus appoint new coach',summary='',content='')
    assert football_news_section(a,today=date(2027,7,1)) is None


@pytest.mark.parametrize('public,sport,ai',[(False,'football',True),(True,'basketball',True),(True,'football',False)])
def test_menu_assignment_cannot_admit_held_articles_or_change_another_sport(public,sport,ai):
    a=SimpleNamespace(ai_generated=ai,title='England wins Nations League match',summary='',content='',league=None)
    tax=SimpleNamespace(public_ok=public,resolved_sport=sport,resolved_competition=None)
    assert not assign_public_football_section(a,tax)
    assert a.league is None and tax.resolved_competition is None


def test_existing_mens_tag_is_corrected_without_changing_public_status_or_copy():
    a=SimpleNamespace(ai_generated=True,title='Chelsea wins Women’s Champions League match',
        summary='',content='Preserve copy',league='uefa-champions-league',published_at='2026-09-29T12:00:00')
    tax=SimpleNamespace(public_ok=True,quality_ok=True,resolved_sport='football',resolved_competition=a.league)
    assert assign_public_football_section(a,tax)
    assert tax.resolved_competition==a.league=='uefa-womens-champions-league'
    assert tax.public_ok and tax.quality_ok and a.content=='Preserve copy'
    assert a.published_at=='2026-09-29T12:00:00'


def test_cartoon_product_is_not_a_report_but_news_about_a_cartoon_is_allowed():
    assert non_article_news_reason({'title':'Manchester City await ruling','summary':'David Squires presents a new cartoon.'})=='non_article_cartoon'
    assert non_article_news_reason({'title':'Club condemns offensive cartoon targeting player'}) is None
