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


def test_existing_public_news_is_tagged_without_republishing_or_changing_copy():
    from datetime import datetime, timedelta
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    from bot.news_league_index import repair_football_league_menus
    db=SessionLocal()
    rows=[]
    stamp=datetime.utcnow()-timedelta(hours=1)
    try:
        for suffix,title,public,sport,age in [
            ('visible','England win UEFA Nations League football match',True,'football',0),
            ('held','England win UEFA Nations League football match',False,'football',0),
            ('old','England win UEFA Nations League football match',True,'football',10),
            ('unrelated','Basketball coach discusses next season',True,'basketball',0),
            ('unspecified','A coach assesses the victory',True,'football',0),
        ]:
            a=Article(slug='league-menu-'+suffix,external_id='league-menu-'+suffix,title=title,
                sport=sport,ai_generated=True,summary=title,content='Preserve this original article body.',
                published_at=stamp-timedelta(days=age),image_url='https://example.com/editorial.jpg')
            db.add(a);db.flush()
            tax=ArticleTaxonomyResolution(article_id=a.id,resolved_sport=sport,resolved_competition=None,
                resolver_version=RESOLVER_VERSION,public_ok=public,quality_ok=True,
                sport_confidence='0.970',competition_confidence='0.000',hero_media_kind='EDITORIAL_PHOTO')
            db.add(tax);rows.append((a,tax))
        db.commit()
        assert repair_football_league_menus(db)==1
        a,tax=rows[0]
        assert tax.resolved_competition==a.league=='uefa-nations-league'
        assert a.published_at==stamp and a.content=='Preserve this original article body.'
        assert tax.public_ok and tax.quality_ok and tax.hero_media_kind=='EDITORIAL_PHOTO'
        assert all(t.resolved_competition is None for a,t in rows[1:])
        assert repair_football_league_menus(db)==0
    finally:
        for a,t in rows: db.delete(t);db.delete(a)
        db.commit();db.close()
