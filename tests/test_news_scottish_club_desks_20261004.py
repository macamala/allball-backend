"""Regression fixtures are synthetic; no dates or public news are rewritten."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bot import news_scottish_club_desks as desk
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_football_source_context import WOMEN_CONTEXT, preserve_women_qualifier_reason

URL='https://www.motherwellfc.co.uk/2026/10/02/own-report/'
OTHER='https://www.motherwellfc.co.uk/2026/10/02/other-report/'
PHOTO='https://www.motherwellfc.co.uk/wp-content/uploads/2026/10/own_790x500_acf_cropped.jpg'
OTHER_PHOTO='https://www.motherwellfc.co.uk/wp-content/uploads/2026/10/other_790x500_acf_cropped.jpg'
BODY='The football club confirmed its training arrangements and announced preparations for the next match. ' * 15
ALIEN='UNRELATED PLAYERS AND INVENTED TRANSFERS'


def item(url=URL, *, category='First team', body=BODY, photo=PHOTO, identity='134825'):
    return (f'<li class="infinite-item" data-href="{url}" data-article-id="{identity}">'
            f'<div class="innerText"><div class="primaryCategory">{category}</div><h2>Report</h2>'
            f'<div class="imageWrap"><picture><img src="{photo}" alt="Own article"></picture></div>'
            f'<div class="postContent"><p>{body}</p></div></div></li>')


def page(*items, canonical=URL, free=True):
    metadata=(f'<link rel="canonical" href="{canonical}">'
              f'<meta property="og:image" content="{OTHER_PHOTO}">'
              '<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle',
                  'isAccessibleForFree':free,'articleBody':ALIEN})+'</script>')
    return metadata+'<main><ul>'+''.join(items or [item()])+'</ul><p>'+ALIEN+'</p></main>'


def test_other_loaded_articles_cannot_supply_body_category_or_hero():
    html=page(item(OTHER,category='Women',body=ALIEN,photo=OTHER_PHOTO), item(),
              item(OTHER.replace('other','third'),body=ALIEN,photo=OTHER_PHOTO))
    text=article_text_from_html(html)
    assert BODY.strip() in text and ALIEN not in text and WOMEN_CONTEXT not in text
    photos=collect_page_image_candidates(html)
    assert len(photos)==1 and photos[0]['url']==PHOTO


def test_own_women_category_is_preserved_without_using_other_article_prose():
    html=page(item(category='Women'), item(OTHER,body=ALIEN,category='First team'))
    text=article_text_from_html(html)
    assert text.startswith(WOMEN_CONTEXT) and ALIEN not in text
    assert preserve_women_qualifier_reason(text,{'title':'Motherwell prepare for the next match','summary':'Training update'})
    assert not preserve_women_qualifier_reason(text,{'title':'Motherwell Women prepare for the next match','summary':'Training update'})


@pytest.mark.parametrize('case',['missing','duplicate','mismatch','no-id','bad-id','unclosed','body-missing','paid'])
def test_unverified_current_article_never_uses_neighbors_or_hidden_schema(case):
    own=item()
    if case=='missing':own=''
    if case=='duplicate':own+=item()
    if case=='mismatch':own=item(OTHER)
    if case=='no-id':own=item(identity='')
    if case=='bad-id':own=item(identity='wrong')
    if case=='unclosed':own=own.replace('</li>','')
    if case=='body-missing':own=own.replace('postContent','changedContent')
    html=page(own,free=case!='paid')
    assert article_text_from_html(html)==''
    assert collect_page_image_candidates(html)==[]


@pytest.mark.parametrize('url',['https://www.motherwellfc.co.uk/',
    'https://www.motherwellfc.co.uk/2026/10/02/own-report/?unexpected=1',
    'http://www.motherwellfc.co.uk/2026/10/02/own-report/',
    'https://user@www.motherwellfc.co.uk/2026/10/02/own-report/',
    'https://www.motherwellfc.co.uk:444/2026/10/02/own-report/'])
def test_invalid_article_identity_does_not_unlock_scoped_prose(url):
    assert desk.motherwell_single_post(page(),url)==''


def test_article_hero_cannot_fall_back_to_social_avatar_or_neighbor():
    for value in ('https://evil.test/image.jpg','data:image/png,aaa','https://www.motherwellfc.co.uk/logo.png'):
        assert collect_page_image_candidates(page(item(photo=value)))==[]
    html=page(item().replace('</picture>','<img src="'+OTHER_PHOTO+'"></picture>'))
    assert collect_page_image_candidates(html)==[]


def test_kilmarnock_visible_body_only_and_exact_social_hero():
    url='https://kilmarnockfc.co.uk/news/own-report/'
    html=(f'<link rel="canonical" href="{url}"><meta property="og:image" content="https://kilmarnockfc.co.uk/wp-content/uploads/2026/10/own.jpg">'
          f'<main><div class="article__body"><p>{BODY}</p></div><aside><p>{ALIEN}</p></aside></main>')
    assert BODY.strip() in article_text_from_html(html) and ALIEN not in article_text_from_html(html)
    assert len(collect_page_image_candidates(html))==1
    assert article_text_from_html(html.replace('article__body','changed-body'))==''


def test_new_source_fetch_is_robots_aware_and_canonical_bound(monkeypatch):
    from bot import news_feed_http, extract, news_image_http
    calls=[]
    monkeypatch.setattr(news_feed_http,'read_news_feed',lambda url:calls.append(url) or page().encode())
    monkeypatch.setattr(news_image_http,'pick_news_article_image',lambda rows:rows[0]['url'])
    text,photo=extract.extract_from_url(URL)
    assert BODY.strip() in text and photo==PHOTO and calls==[URL]
    assert extract.extract_image_candidates_from_url(URL)[0]['url']==PHOTO


@pytest.mark.parametrize('canonical',['','https://evil.test/own-report/',OTHER,URL+'?other=1'])
def test_wrong_or_missing_canonical_is_not_replaced_with_requested_url(monkeypatch,canonical):
    from bot import news_feed_http, extract
    monkeypatch.setattr(news_feed_http,'read_news_feed',lambda url:page(canonical=canonical).encode())
    assert extract.extract_from_url(URL)==('',None)
    assert extract.extract_image_candidates_from_url(URL)==[]


@pytest.mark.parametrize('error',['feed_robots_disallowed','feed_http_429','feed_cross_host_redirect','feed_response_too_large'])
def test_denied_safe_transport_cannot_fall_back_to_ordinary_http(monkeypatch,error):
    from bot import news_feed_http, extract
    def reject(url):raise ValueError(error)
    def forbidden(*args,**kwargs):raise AssertionError('Unsafe transport fallback')
    monkeypatch.setattr(news_feed_http,'read_news_feed',reject)
    monkeypatch.setattr(extract.httpx,'Client',forbidden)
    assert extract.extract_from_url(URL)==('',None)
    assert extract.extract_image_candidates_from_url(URL)==[]


def test_unrelated_publishers_are_not_fetched_by_this_adapter(monkeypatch):
    from bot import news_feed_http
    monkeypatch.setattr(news_feed_http,'read_news_feed',lambda url:pytest.fail('Unexpected network'))
    assert desk.fetch_scottish_article('https://another.example/news/report')==(False,'')


def test_sources_are_registered_once_without_blanket_league_or_rss_body_fallback():
    from bot.feeds import enabled_feeds
    configs=enabled_feeds()
    for new in desk.RSS_FEEDS:
        assert sum(c['url']==new['url'] for c in configs)==1
        assert new['article_body_required'] and not new.get('league')
        assert not new.get('verified_body_field')


@pytest.mark.parametrize('cfg',desk.RSS_FEEDS)
def test_only_current_same_host_posts_can_enter_the_writer_queue(monkeypatch,cfg):
    from bot import fetch_sources as fetch
    now=datetime.now(timezone.utc)
    path='/2026/10/02/own-report/' if cfg['publisher']=='Motherwell FC' else '/news/own-report/'
    def entry(hours,host=cfg['article_https_host'],suffix=path):
        return {'title':'Football club preparation report','link':'https://'+host+suffix,
                'summary':BODY,'published':(now-timedelta(hours=hours)).isoformat()}
    rows=[entry(1),entry(50),entry(-24),entry(1,'foreign.test')]
    if cfg['publisher']=='Kilmarnock FC':rows.append(entry(1,suffix='/news/motherwell-h-ticket-information/'))
    monkeypatch.setattr(fetch,'read_news_feed',lambda url:b'feed')
    monkeypatch.setattr(fetch.feedparser,'parse',lambda raw:SimpleNamespace(entries=rows,version='rss20',bozo=False))
    found=fetch._fetch_feed_entries(cfg,60)
    assert len(found)==1 and found[0]['published_at']==now-timedelta(hours=1)
