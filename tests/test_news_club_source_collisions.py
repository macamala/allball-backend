from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from bot import news_football_sections as sections
from bot.news_club_coverage import ClubCoverage
from bot.news_club_identity import ambiguous_club_has_evidence
from bot.news_football_priority import candidate_football_section
from bot.news_policy import non_article_news_reason, fair_news_queue
NOW = datetime(2026, 10, 3, 7, tzinfo=timezone.utc)
LEAGUE = 'italy-serie-a'
@pytest.fixture
def coverage(monkeypatch):
    rosters={LEAGUE:{'clubs':['Como','Roma','Milan','Juventus'],'valid_from':'2026-10-02',
        'valid_until':'2026-10-05','observed_at':NOW.isoformat()}}
    monkeypatch.setattr(sections,'memberships_for_news',lambda:rosters)
    monkeypatch.setattr(sections,'_CLUBS',{'valid_from':'2026-10-01','valid_until':'2026-12-31','leagues':{}})
    return ClubCoverage(rosters,now=NOW)
@pytest.mark.parametrize('title',[
    'Ironia de Potter apanhou Gyökeres desprevenido: Temos quase tantas baixas como acusações',
    'Como o treinador preparou a equipa para o jogo','Jogador descrito como reforço importante',
    'Nuno explica como defendeu a equipa','A seleção tem tantos lesionados como o adversário'])
def test_portuguese_word_is_not_italian_club_identity(coverage,title):
    article=SimpleNamespace(title=title,summary='',content='',published_at=NOW,source_url='https://www.abola.pt/futebol/noticia/test')
    assert coverage.subjects(article,LEAGUE)==()
    assert sections._club_section(sections._norm(title),'',article,False,NOW.date()) is None
    item={'title':title,'published_at':NOW,'summary':'','url':article.source_url}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league=LEAGUE),today=NOW.date()) is None
@pytest.mark.parametrize('title',[
    'Como sign a new midfielder','Como appoint manager','Como announces training schedule',
    'Como defeat Roma','Como 1907 discusses preparations','FC Como plans next match',
    "Como's coach discusses the squad",'Como’s goalkeeper returns to training'])
def test_explicit_club_reporting_keeps_the_verified_team(coverage,title):
    article=SimpleNamespace(title=title,summary='',content='',published_at=NOW)
    assert 'como' in coverage.subjects(article,LEAGUE)
    assert sections._club_section(sections._norm(title),'',article,False,NOW.date())==LEAGUE
def test_other_club_in_headline_is_not_displaced_by_common_como(coverage):
    article=SimpleNamespace(title='Como a Juventus preparou o próximo jogo',summary='',published_at=NOW)
    assert coverage.subjects(article,LEAGUE)==('juventus',)
    assert ambiguous_club_has_evidence('juventus','anything')
@pytest.mark.parametrize('title',[
    'Compra tus entradas para ver el duelo entre el Valencia y el Athletic Club',
    'Consigue tus entradas para el partido','Adquiere las entradas para el partido',
    'Reserva ya tus boletos para el partido','Comprar las entradas para ver al equipo'])
def test_ticket_purchase_instructions_are_not_club_reporting(title):
    assert non_article_news_reason({'title':title})=='non_article_ticket_promotion'
@pytest.mark.parametrize('title',[
    'Valencia anuncia reembolsos por las entradas','Aficionados protestan por el precio de las entradas',
    'Club suspende la venta de entradas por seguridad','El estadio registra un lleno histórico',
    'El jugador compra entradas para aficionados afectados'])
def test_real_reporting_about_ticket_problems_remains_eligible(title):
    assert non_article_news_reason({'title':title}) is None
def test_sales_copy_is_removed_before_club_balancing_or_writer(coverage):
    items=[{'title':'Compra tus entradas para el partido del Como','url':'https://example.com/promo','published_at':NOW},
        {'title':'Como appoint manager','url':'https://example.com/news','published_at':NOW}]
    queue,reasons=fair_news_queue(items,lambda _:SimpleNamespace(sport='football',league=LEAGUE),
        now=NOW,allowed_sports={'football'},football_inventory={LEAGUE:2},football_club_coverage=coverage)
    assert [row['url'] for row in queue]==['https://example.com/news']
    assert reasons['non_article_ticket_promotion']==1
