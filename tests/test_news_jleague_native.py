from copy import deepcopy
from datetime import datetime,timezone
import pytest
from bot.news_jleague_native import read_jleague_article,article_identity,NATIVE_INDEXES

URL='https://www.jleague.jp/news/article/99999/'
PHOTO='https://www.jleague.jp/images/media/reported-photo.webp'
TEXT='サンフレッチェ広島は、所属選手とプロ契約を締結したことを発表しました。選手はクラブを通じて、日々の練習から努力していくとコメントしています。クラブは今後も選手の成長をサポートしていきます。'

def page(tier=1,category=None,body=None,extra='',date='2026/10/2 (金) 18:20',title='MF野口がプロ契約を締結【広島】'):
    category=category or f'明治安田Ｊ{tier}リーグ'
    return (f'<meta property="og:type" content="article"><meta property="og:url" content="{URL}">'
        f'<meta property="og:image" content="{PHOTO}"><main><div class="p-news-details__content">'
        f'<div class="p-news-details__title-module"><h1 class="m-article-module__title">{title}</h1>'
        f'<span class="m-article-module__category-title">{category}</span>'
        f'<p class="m-article-module__date">{date}</p></div>'
        f'<img class="m-article-module__image" src="{PHOTO}">'
        f'<div class="lexical-content"><p>{TEXT if body is None else body}</p></div>'
        '</div><aside><p>Unrelated recommendations must never supply names or facts.</p></aside>'
        f'</main>{extra}')

@pytest.mark.parametrize('tier',[1,2])
def test_article_header_not_url_tracking_decides_competition(tier):
    result=read_jleague_article(page(tier),URL+f'?navicode=j{3-tier}')
    assert result['url']==URL
    assert result['title']=='MF野口がプロ契約を締結【広島】'
    assert result['source_category']==f'japan-j{tier}-league'
    assert result['body']==f'Source article category: J{tier} League.\n\n'+TEXT
    assert result['published_at']==datetime(2026,10,2,9,20,tzinfo=timezone.utc)
    assert result['image_candidates'][0]['url']==PHOTO
    assert read_jleague_article(page(tier),URL,expected_tier=3-tier) is None

@pytest.mark.parametrize('url',[None,{},'https://www.jleague.jp.evil.test/news/article/99999/',
    'http://www.jleague.jp/news/article/99999/','https://user:pass@www.jleague.jp/news/article/99999/',
    'https://www.jleague.jp:444/news/article/99999/','https://www.jleague.jp/en/news/article/99999/',
    'https://www.jleague.jp/j1/news/','https://www.jleague.jp/news/article/99998/'])
def test_wrong_identity_cannot_borrow_this_articles_content(url):
    assert read_jleague_article(page(),url) is None

@pytest.mark.parametrize('field',['p-news-details__content','p-news-details__title-module',
    'm-article-module__title','m-article-module__category-title','m-article-module__date','lexical-content','m-article-module__image'])
def test_absent_visible_structure_fails_without_hidden_json_fallback(field):
    raw=page(extra='<script type="application/ld+json">{"articleBody":"Hidden article must not be substituted"}</script>')
    assert read_jleague_article(raw.replace(field,'changed-structure'),URL) is None

@pytest.mark.parametrize('category',['Ｊリーグニュース','JFA','日本代表','ルヴァンカップ','明治安田Ｊ３リーグ','U-21','明治安田Ｊ１リーグ 明治安田Ｊ２リーグ'])
def test_index_membership_site_keywords_and_other_competitions_do_not_assign_a_league(category):
    assert read_jleague_article(page(category=category),URL+'?navicode=j1') is None

@pytest.mark.parametrize('date',['2026/10/2','2026/10/2 18:20','2026/13/2 (金) 18:20','2026/10/2 (金) 25:20','tomorrow','2026/10/2 (金) 18:20 updated 18:30'])
def test_no_invented_date_time_or_timezone(date):
    assert read_jleague_article(page(date=date),URL) is None

@pytest.mark.parametrize('title',['試合のプレビューを掲載','テレビの放送告知について','チケット発売のお知らせ','新しいキャンペーンについて','選手の人気投票が開始','マンスリーレポートを公開'])
def test_promotions_and_analysis_do_not_use_writer_budget(title):
    assert read_jleague_article(page(title=title),URL) is None


def test_paragraphs_preserve_japanese_short_sentences_and_omit_navigation():
    result=read_jleague_article(page(body=TEXT+'<br/><br/>応援よろしくお願いします！<script>Injected narrative</script>'),URL)
    assert '\n\n応援よろしくお願いします！' in result['body']
    assert 'Injected' not in result['body'] and 'Unrelated' not in result['body']

@pytest.mark.parametrize('kind',['duplicate-root','duplicate-header','duplicate-body','duplicate-category','conflicting-date','different-hero','hidden-body'])
def test_ambiguous_or_inaccessible_article_cannot_be_admitted(kind):
    s=page()
    if kind=='duplicate-root':s+='<div class="p-news-details__content"></div>'
    elif kind=='duplicate-header':s=s.replace('</h1>','</h1><h1 class="m-article-module__title">Other title</h1>')
    elif kind=='duplicate-body':s=s.replace('<div class="lexical-content">','<div class="lexical-content"></div><div class="lexical-content">')
    elif kind=='duplicate-category':s=s.replace('</span>','</span><span class="m-article-module__category-title">JFA</span>')
    elif kind=='conflicting-date':s+='<meta property="article:published_time" content="2026-10-03T09:20:00Z">'
    elif kind=='different-hero':s=s.replace('src="'+PHOTO+'"','src="https://www.jleague.jp/images/media/other.webp"')
    elif kind=='hidden-body':s=s.replace('class="lexical-content"','class="lexical-content" hidden')
    assert read_jleague_article(s,URL) is None


def test_existing_hydrator_enforces_freshness_and_returns_canonical_source(monkeypatch):
    from bot import news_official_indexes as indices
    import bot.news_image_http as image
    class Clock:
        @staticmethod
        def now(tz=None):return datetime(2026,10,3,1,tzinfo=timezone.utc)
    monkeypatch.setattr(indices,'datetime',Clock)
    monkeypatch.setattr(indices,'read_news_feed',lambda url:page().encode())
    monkeypatch.setattr(image,'pick_news_article_image',lambda rows:rows[0]['url'])
    cfg=deepcopy(NATIVE_INDEXES[0]);a=indices._hydrate(cfg,URL+'?navicode=j1','Wrong card heading')
    assert a['url']==URL and a['title']=='MF野口がプロ契約を締結【広島】'
    assert a['_classification_text'].startswith('Source article category: J1 League.')
    assert a['feed']['league'] is None
    monkeypatch.setattr(indices,'read_news_feed',lambda url:page(date='2020/10/2 (金) 18:20').encode())
    assert indices._hydrate(cfg,URL,'Old story') is None


def test_two_native_feeds_join_only_existing_index_intake():
    from bot.news_football_sources import HTML_INDEXES
    for cfg in NATIVE_INDEXES:
        assert cfg in HTML_INDEXES and cfg['sport']=='football'
        assert cfg.get('league') is None and cfg['host']=='www.jleague.jp'
