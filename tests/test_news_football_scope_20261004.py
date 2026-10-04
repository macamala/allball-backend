"""Observed reader-facing incidents and archive repair regression cases."""
from datetime import datetime, timedelta, timezone
import pytest
from bot.news_policy import explicit_headline_sport, source_path_conflict_reason, source_path_sport_hint, non_article_news_reason
from bot.news_football_scope_guard import football_scope_conflict


@pytest.mark.parametrize('title,sport', [
    ('Kika Veselko finishes second at the São Sebastião Pro surfing event', 'surfing'),
    ('Ricardo Batista targets higher World Championship finish after triathlon bronze', 'triathlon'),
    ('O Parrulo hosts Viña Albali Valdepeñas to 0-0 football draw in Ferrol', 'futsal'),
])
def test_other_sport_cannot_be_forced_to_football_by_a_dedicated_feed(title, sport):
    from bot.fetch_sources import _classify_item
    item = {'title': title, 'url': 'https://example.test/source-report',
            'feed': {'kind': 'league', 'sport': 'football'}}
    assert explicit_headline_sport(title) == sport
    assert _classify_item(item, title).sport != 'football'
    assert source_path_conflict_reason(item, 'football') == 'taxonomy_football_scope_conflict'
    assert source_path_conflict_reason(item, sport) is None


@pytest.mark.parametrize('host', ['www.record.pt', 'record.pt'])
@pytest.mark.parametrize('path,sport', [('surf','surfing'), ('triatlo','triathlon')])
def test_verified_publisher_sections_reject_incorrect_football_identity(host, path, sport):
    url = 'https://' + host + '/modalidades/' + path + '/detalhe/report'
    assert source_path_sport_hint(url) == sport
    assert source_path_conflict_reason({'url':url,'title':'Competitor describes the result'}, 'football')
    assert not source_path_conflict_reason({'url':url,'title':'Competitor describes the result'}, sport)


@pytest.mark.parametrize('url', ['https://record.pt.evil.test/modalidades/surf/detalhe/report',
    'https://record.pt@evil.test/modalidades/surf/detalhe/report',
    'https://example.test/report?url=https://record.pt/modalidades/surf/',
    'https://record.pt/futebol/surfing-player', 'https://record.pt/modalidades/surfboard/report'])
def test_unverified_hosts_queries_and_partial_path_matches_are_not_authority(url):
    assert source_path_sport_hint(url) != 'surfing'


@pytest.mark.parametrize('title', ['Football club arranges surfing lessons for players',
    'Football club announces charity triathlon partnership',
    'Parrulo visits the Barcelona football academy',
    'Valdepeñas sponsors local football training',
    'A new striker makes waves at the football club'])
def test_incidental_activities_and_shared_words_do_not_hide_football(title):
    assert football_scope_conflict({'title': title}, 'football') is None


def test_video_game_product_announcement_is_not_esports_reporting():
    assert non_article_news_reason({'title': 'Battlefield Studios Unveils Season 5 Updates for Battlefield 6 and REDSEC'}) == 'non_article_video_game_product'
    for title in ('Battlefield Studios announces esports championship for next season',
                  'Battlefield 6 team wins tournament final', 'Football club announces new season kit'):
        assert non_article_news_reason({'title': title}) != 'non_article_video_game_product'


def test_public_conflicts_are_held_once_without_deleting_copy_or_changing_dates():
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from taxonomy_resolver import RESOLVER_VERSION
    from public_index import repair_recent_gossip_news
    db, ids = SessionLocal(), []
    stamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    titles = ['Kika Veselko finishes second at the São Sebastião Pro surfing event',
              'O Parrulo hosts Viña Albali Valdepeñas to 0-0 football draw in Ferrol',
              'Ricardo Batista targets higher World Championship finish after triathlon bronze',
              'Battlefield Studios Unveils Season 5 Updates for Battlefield 6 and REDSEC',
              'Football club confirms training schedule']
    try:
        for i,title in enumerate(titles):
            a=Article(title=title,slug='scope-oct4-'+str(i),sport='football',ai_generated=True,
                summary=title,content='Preserve the original article for review.',
                published_at=stamp,source_url='https://fixture.test/oct4/'+str(i),
                image_url='https://fixture.test/own-photo.jpg')
            db.add(a);db.flush();ids.append(a.id)
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,
                resolved_sport='football',public_ok=True,quality_ok=True))
        db.commit()
        assert repair_recent_gossip_news(db) == 4
        visible=[t.article_id for t in db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id.in_(ids),ArticleTaxonomyResolution.public_ok.is_(True))]
        assert visible == ids[-1:]
        assert db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).count() == 4
        assert repair_recent_gossip_news(db) == 0
        for a in db.query(Article).filter(Article.id.in_(ids)):
            assert a.content == 'Preserve the original article for review.' and a.published_at == stamp
            assert a.image_url == 'https://fixture.test/own-photo.jpg'
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close()


def test_unassigned_card_behind_300_newer_rows_is_repaired_without_republishing():
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    from bot.news_league_index import repair_football_league_menus
    db, ids = SessionLocal(), []
    stamp = datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(hours=1)
    try:
        for i in range(302):
            a=Article(title='England win UEFA Nations League football match',slug='menu-bound-oct4-'+str(i),
                sport='football',ai_generated=True,summary='England win UEFA Nations League football match',
                content='Preserve this original football article.',published_at=stamp,
                source_url='https://fixture.test/menubound/'+str(i),image_url='https://fixture.test/photo.jpg')
            db.add(a);db.flush();ids.append(a.id)
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,
                resolved_sport='football',resolved_competition=None if i==0 else 'uefa-nations-league',public_ok=True))
        db.commit()
        assert repair_football_league_menus(db) == 1
        a=db.get(Article,ids[0])
        assert a.league=='uefa-nations-league' and a.published_at==stamp
        assert a.content=='Preserve this original football article.'
        assert repair_football_league_menus(db)==0
    finally:
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close()
