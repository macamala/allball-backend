from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.news_fact_guard import competition_in_source
from bot.news_football_priority import candidate_football_section
from bot.news_policy import fair_news_queue, numeric_tokens

NOW = datetime(2026, 9, 30, 6, tzinfo=timezone.utc)


def test_empty_major_leagues_and_other_leagues_get_slots_without_displacing_zvezda():
    def row(index, title, league=None, host='news.test'):
        return dict(url=f'https://{host}/{index}', title=title, league=league,
                    summary='', published_at=NOW-timedelta(hours=2))
    items = [row(i, 'Nations League team confirms injury', 'uefa-nations-league') for i in range(10)]
    items += [row(20, 'Bayern Munich confirm contract extension'),
              row(21, 'La Liga club confirms new manager', 'spain-la-liga'),
              row(22, 'Coventry City confirm new contract'),
              row(23, 'Brazil Serie A club confirms new coach', 'brazil-serie-a'),
              row(24, 'Crvena zvezda confirm signing', host='crvenazvezdafk.com')]
    items.append(dict(items[-1], url='https://crvenazvezdafk.com/old', published_at=NOW-timedelta(days=2)))
    original = repr(items)
    classify = lambda item: SimpleNamespace(sport='football', league=item['league'])
    ordered, rejected = fair_news_queue(items, classify, now=NOW, max_age_hours=24,
        football_inventory={'uefa-nations-league':27}, spread_publishers=True)
    assert ordered[0]['url'].endswith('/24')
    assert {row['url'] for row in ordered[1:4]} == {'https://news.test/20', 'https://news.test/21', 'https://news.test/22'}
    assert ordered[4]['url'].endswith('/23')
    assert rejected['stale_publication'] == 1
    assert repr(items) == original


def test_verified_source_body_supplies_scheduling_context_but_never_sport():
    item = {'title':'Coach confirms new injury', '_extracted':'The Bundesliga club confirmed the injury.',
            'published_at':NOW}
    assert candidate_football_section(item, SimpleNamespace(sport='football', league=None), today=NOW.date()) == 'germany-bundesliga'
    assert candidate_football_section(item, SimpleNamespace(sport=None, league=None), today=NOW.date()) is None


def test_bundesliga_discovery_is_scoped_to_articles_and_explicit_other_sport_wins():
    from bot.news_official_indexes import HTML_INDEXES, _same_host_url
    from bot.fetch_sources import _classify_candidate
    for name in ('bundesliga-german-news', 'bundesliga-english-news', 'bundesliga-2-news'):
        cfg = next(row for row in HTML_INDEXES if row['id'] == name)
        assert _same_host_url(cfg['url'], cfg['paths'][0]+'club-confirms-injury-39381', cfg['host'], cfg)
        assert _same_host_url(cfg['url'], cfg['paths'][0]+'table', cfg['host'], cfg) is None
        assert _same_host_url(cfg['url'], 'https://foreign.test/news/article-39381', cfg['host'], cfg) is None
    candidate = {'url':'https://www.bundesliga.com/de/bundesliga/news/test-39381',
                 'title':'Club confirms new injury', 'feed':{'sport':'football'}}
    assert _classify_candidate(candidate).sport == 'football'
    candidate['title'] = 'Basketball team confirms new injury'
    assert _classify_candidate(candidate).sport == 'basketball'


def test_serbian_score_and_competition_translation_keep_exact_source_facts():
    source = 'Графичар је убедљиво савладао екипу Телеоптика (4:1) у оквиру 11. кола Прве лиге Србије.'
    assert '4-1' in numeric_tokens(source, include_spelled=True)
    assert '4-1' not in numeric_tokens(source)
    assert '1-4' not in numeric_tokens(source, include_spelled=True)
    assert competition_in_source('serbia-prva-liga', source)
    assert not competition_in_source('serbia-superliga', source)


@pytest.mark.parametrize('text', ['Однос је 4:1.', 'Воз полази у 4:10.',
    'Савладао је потешкоће у 4:10 током ноћи.', 'Прве лиге Хрватске', 'Женске Прве лиге Србије'])
def test_local_equivalents_do_not_invent_scores_or_mens_serbian_competition(text):
    assert '4-1' not in numeric_tokens(text, include_spelled=True)
    assert not competition_in_source('serbia-prva-liga', text)


def test_inventory_excludes_held_stale_future_wrong_version_and_missing_image():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Base, Article, ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    from bot.news_league_index import recent_public_football_inventory
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i, changes in enumerate(({}, {'public_ok':False}, {'age':25}, {'age':-1},
                                    {'resolver_version':'old'}, {'image':None}, {'sport':'basketball'})):
            article = Article(title='Club confirms signing', content='Verified article.', ai_generated=True,
                slug=f'fill-{i}', published_at=NOW.replace(tzinfo=None)-timedelta(hours=changes.get('age',1)),
                image_url=changes.get('image','https://photo.test/valid.jpg'))
            db.add(article); db.flush()
            db.add(ArticleTaxonomyResolution(article_id=article.id,
                resolver_version=changes.get('resolver_version',RESOLVER_VERSION),
                resolved_sport=changes.get('sport','football'), resolved_competition='germany-bundesliga',
                public_ok=changes.get('public_ok',True), hero_media_kind='EDITORIAL_PHOTO'))
        db.commit()
        assert recent_public_football_inventory(db, now=NOW) == {'germany-bundesliga':1}


@pytest.mark.parametrize('host,container', [
    ('www.mlssoccer.com','<div class="oc-c-article__body">{body}</div>'),
    ('www.bundesliga.com','<dfl-editorial-news><section>{body}</section></dfl-editorial-news>'),
    ('eredivisie.nl','<div class="news-grid-main__content">{body}</div>'),
])
def test_new_publisher_bodies_exclude_recommendations_and_fail_closed(host, container):
    from bot.extract import article_text_from_html
    body = '<p>' + 'The club confirmed a new contract after discussions with the player. '*15 + '</p>'
    head = f'<meta property="og:url" content="https://{host}/news/test">'
    html = head + container.format(body=body) + '<main><h2>Unrelated fantasy promotion</h2><p>Other club signs a new coach.</p></main>'
    extracted = article_text_from_html(html)
    assert 'confirmed a new contract' in extracted
    assert 'fantasy' not in extracted and 'new coach' not in extracted
    assert article_text_from_html(head+'<main>'+body+'</main>') == ''


@pytest.mark.parametrize('title', ['Fantasy Manager: Jetzt nach Herzenslust den Kader umbauen',
    'Unlimited transfers in Bundesliga Fantasy Manager!', 'Het ESPN Fantasy Voetbal elftal tot dusver'])
def test_fantasy_products_never_consume_an_empty_leagues_writer_slot(title):
    from bot.news_policy import non_article_news_reason
    assert non_article_news_reason({'title':title}) == 'non_article_fantasy_product'


@pytest.mark.parametrize('title,expected', [
    ('PSG confirm contract extension','france-ligue-1'),
    ('Marseille name new coach','france-ligue-1'),
    ('Le Mans FC confirm signing','france-ligue-1'),
    ('Ajax confirm injury','netherlands-eredivisie'),
    ('PSG women confirm new coach','football-women'),
    ('PSG academy announce new coach','football-youth'),
    ('Nantes confirm new coach',None),
])
def test_verified_french_and_dutch_clubs_keep_women_youth_and_relegated_teams_separate(title,expected):
    from bot.news_football_sections import football_news_section
    assert football_news_section(SimpleNamespace(title=title),today=NOW.date()) == expected
