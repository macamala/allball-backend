import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from bot.taxonomy import COMPETITIONS
from taxonomy_resolver import resolve_article_competition

CATALOG=json.loads(Path('bot/news_football_leagues.json').read_text())

def test_navigation_ids_are_unique_and_all_have_news_taxonomy():
    assert len(CATALOG)>=50
    assert len({r['league'] for r in CATALOG})==len(CATALOG)
    assert len({r['path'] for r in CATALOG})==len(CATALOG)
    assert all(COMPETITIONS[r['league']]['sport']=='football' for r in CATALOG)

@pytest.mark.parametrize('key,title',[
 ('uefa-nations-league','England win UEFA Nations League football match'),
 ('japan-j2-league','J2 League football match ends in draw'),
 ('serbia-prva-liga','Prva liga Srbije: fudbal donosi novi derbi'),
 ('australia-a-league-women','A-League Women football club announces signing'),
 ('brazil-serie-b','Brasileirão Série B football match report'),
 ('caf-champions-league','CAF Champions League football final decided'),
 ('afc-champions-league-elite','AFC Champions League Elite football draw confirmed'),
 ('fifa-club-world-cup','FIFA Club World Cup football draw confirmed'),
 ('germany-2-bundesliga','2. Bundesliga football club announces signing'),
])
def test_explicit_competition_resolves_to_own_page(key,title):
    article=SimpleNamespace(title=title,summary=title,body=title,sport='football',league=None,source_url='',url='')
    assert resolve_article_competition(article).public_competition==key
