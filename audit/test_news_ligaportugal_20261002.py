import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import pytest
from types import SimpleNamespace
from bot.news_ligaportugal import read_ligaportugal_article, MAX_NODES
from bot import news_official_indexes as ni
from bot.news_policy import non_article_news_reason, fair_news_queue

URL = 'https://www.ligaportugal.pt/news/123/league-announces-arrangements'
HERO = 'https://www.ligaportugal.pt/backoffice/assets/selected-story.jpg'
TITLE = 'League announces arrangements'
BODY = '<p>The football league confirmed the arrangements after the meeting with the clubs.</p>'


def document(*, date='2026-10-02T09:00:00Z', identity=123, title=TITLE, body=BODY,
             og_title=TITLE, og_url='/news/123/league-announces-arrangements', hero=HERO,
             record_hero=HERO, duplicate=False):
    nodes=[]
    def put(value):
        index=len(nodes);nodes.append(None)
        if type(value) is dict:value={k:put(v) for k,v in value.items()}
        elif type(value) is list:value=[put(v) for v in value]
        nodes[index]=value;return index
    selected={'id':identity,'title':title,'date':date,'banner':[{'url':record_hero}],
              'blocks':[{'type':'content-fields.text-content','text':body},
                        {'type':'related-articles','text':'<p>Unrelated club beat another team 9-0</p>'}]}
    put({'id':999,'title':'Different match','date':'2026-10-02T11:00:00Z',
         'blocks':[{'type':'content-fields.text-content','text':'Other story must not be used.'}]})
    put(selected)
    if duplicate:put(selected)
    html=(f'<meta property="og:url" content="{escape(og_url, quote=True)}">'
          f'<meta property="og:title" content="{escape(og_title, quote=True)}">'
          f'<meta property="og:image" content="{hero}">'
          f'<script id="__NUXT_DATA__" type="application/json">{json.dumps(nodes)}</script>')
    return html


def test_selects_only_the_url_article_and_its_timestamp_text_and_hero():
    row=read_ligaportugal_article(document(),URL)
    assert row['title']==TITLE
    assert row['published_at']==datetime(2026,10,2,9,tzinfo=timezone.utc)
    assert 'confirmed the arrangements' in row['body']
    assert 'Other story' not in row['body'] and '9-0' not in row['body']
    assert row['image_candidates']==[{'url':HERO,'source':'og','in_article':True}]


@pytest.mark.parametrize('options',[
    {'identity':999}, {'date':'2026-10-02'}, {'date':'2026-10-02T10:00:00'},
    {'date':'invalid'}, {'og_title':'Another story'}, {'og_url':'/news/999/another-story'},
    {'og_url':'https://other.example/news/123/league-announces-arrangements'},
    {'og_url':''}, {'body':''}, {'record_hero':'https://www.ligaportugal.pt/backoffice/assets/other.jpg'},
    {'duplicate':True}, {'hero':'https://other.example/photo.jpg','record_hero':'https://other.example/photo.jpg'},
])
def test_ambiguous_or_changed_article_payload_fails_closed(options):
    assert read_ligaportugal_article(document(**options),URL) is None


@pytest.mark.parametrize('url',[
    URL.replace('https:','http:'), URL.replace('www.ligaportugal.pt','www.ligaportugal.pt.evil.test'),
    'https://www.ligaportugal.pt/noticias', URL.replace('https://','https://user@'),
    URL.replace('www.ligaportugal.pt','www.ligaportugal.pt:444'),
])
def test_host_and_exact_article_route_are_mandatory(url):
    assert read_ligaportugal_article(document(),url) is None


def test_inert_json_limits_malformed_references_and_no_script_execution():
    for payload in ['window.evil()', '{}', '[[0]]', json.dumps([None]*(MAX_NODES+1))]:
        html=document().split('<script')[0]+'<script id="__NUXT_DATA__">'+payload+'</script>'
        assert read_ligaportugal_article(html,URL) is None
    assert read_ligaportugal_article(document()+' ' * 2_000_000,URL) is None
    assert read_ligaportugal_article(document()+document(),URL) is None


def test_references_cannot_use_negative_or_boolean_indices():
    html=document()
    # Replace every scalar ID reference with an invalid reference, not a value.
    import re
    for bad in ['-1','true',str(MAX_NODES+9)]:
        broken=re.sub(r'"id": \d+', '"id": '+bad, html)
        assert read_ligaportugal_article(broken,URL) is None


def test_exact_original_offset_is_preserved_as_utc():
    row=read_ligaportugal_article(document(date='2026-10-02T10:00:00+01:00'),URL)
    assert row['published_at']==datetime(2026,10,2,9,tzinfo=timezone.utc)


def test_index_hydration_reuses_existing_freshness_image_and_publication_gates(monkeypatch):
    stamp=datetime.now(timezone.utc).replace(microsecond=0)
    cfg={'id':'ligaportugal-official-news','url':'https://www.ligaportugal.pt/noticias',
         'host':'www.ligaportugal.pt','publisher':'Liga Portugal','sport':'football'}
    monkeypatch.setattr(ni,'read_news_feed',lambda _:document(date=stamp.isoformat()).encode())
    monkeypatch.setattr('bot.news_image_http.pick_news_article_image',lambda rows:rows[0]['url'])
    row=ni._hydrate(cfg,URL,'Ignored index title')
    assert row['title']==TITLE and row['published_at']==stamp
    assert row['_publication_evidence']=='article-published'
    assert row['feed']['league'] is None
    assert row['_extracted'].startswith('The football league')
    monkeypatch.setattr(ni,'read_news_feed',lambda _:document(date=(stamp-timedelta(days=2)).isoformat()).encode())
    assert ni._hydrate(cfg,URL,'Ignored index title') is None
    monkeypatch.setattr(ni,'read_news_feed',lambda _:document(identity=999).encode())
    assert ni._hydrate(cfg,URL,'Ignored index title') is None


@pytest.mark.parametrize('title',[
    '3 free agent midfielders for Watford to consider after Krepin Diatta deal',
    'Three free-agent strikers for a football club to target this winter',
    '5 players for Leeds to sign before the window closes',
])
def test_transfer_wishlist_is_rejected_before_any_writer_queue(title):
    now=datetime.now(timezone.utc)
    item={'title':title,'url':'https://the72.co.uk/2026/10/02/proposals/','published_at':now}
    assert non_article_news_reason(item)=='non_article_transfer_wishlist'
    queue,reasons=fair_news_queue([item],lambda _:SimpleNamespace(sport='football',league='england-championship'),now=now)
    assert not queue and reasons=={'non_article_transfer_wishlist':1}


@pytest.mark.parametrize('title',[
    'Watford sign three free agent midfielders',
    'Three midfielders sign new contracts at Leeds',
    'Coach confirms talks with a free agent midfielder',
    'Watford confirm Krepin Diatta deal',
])
def test_factual_transfer_announcements_remain_eligible(title):
    assert non_article_news_reason({'title':title,'url':'https://the72.co.uk/2026/10/02/news/'}) is None


def test_new_wishlist_filter_is_limited_to_verified_publisher_format():
    assert non_article_news_reason({'title':'3 free agent midfielders for Watford to consider',
        'url':'https://another.example/news/'}) is None
