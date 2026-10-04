"""Observed football fill failures: extraction, editorial menus and source quota."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import json
import pytest
from bot.news_football_subject_context import national_primary_subject
from bot.news_football_sections import football_news_section
from bot.news_football_source_context import source_menu_association
from bot.news_football_scope_guard import football_scope_conflict
from bot.news_football_club_intake_b import RSS_FEEDS,HTML_INDEXES,YOUTH_CONTEXT,preserve_youth_qualifier_reason
from bot.extract import article_text_from_html,collect_page_image_candidates

@pytest.mark.parametrize('title',[
 'Canada coach Jesse Marsch cites win over Peru ahead of USA friendly',
 'Jacob Shaffelburg leads Canada to victory over Peru in football friendly',
 'Lamine Yamal leads Spain to victory against the Czech Republic',
 'France and Italy prepare for football match',
 'Tyler Adams named USA captain as leadership changes',
 'Klopp suggests Jonas Urbig will remain Germany goalkeeper against Greece',
 'Tensions rise before Republic of Ireland versus Israel',
 'Serbia weigh rotation as coach considers player for Netherlands match',
 'Heimir Hallgrimsson is the coach of Ireland','Yemen coach keeps focus on football'])
def test_literal_primary_national_subject(title):
    assert national_primary_subject(title)

@pytest.mark.parametrize('title',[
 'Austria Vienna face Rapid Wien','France defender joins Italy club in transfer deal',
 'France and Italy discuss trade policy','Spain and Germany governments discuss football security',
 'Club introduces new player after his national team debut','West Ham confirms training preparations for the Championship',
 'Canada midfielder plays for an Italy club','Portugal scout visits Spain club ahead of transfer talks'])
def test_countries_and_biographies_are_not_fixtures(title):
    assert not national_primary_subject(title)

def article(title,summary='',body='',source_url=''):
    return SimpleNamespace(title=title,summary=summary,content=body,ai_content=None,source_url=source_url,external_id=None,league=None,published_at=datetime(2026,10,4,tzinfo=timezone.utc))

@pytest.mark.parametrize('url,key',[
 ('https://www.marca.com/futbol/primera-division/2026/10/04/racing-necesita-acoplarse.html','spain-la-liga'),
 ('https://www.marca.com/futbol/segunda-division/2026/10/04/report.html','spain-la-liga-2'),
 ('https://www.record.pt/futebol/futebol-nacional/liga-betclic/moreirense/detalhe/report','portugal-primeira-liga'),
 ('https://www.record.pt/futebol/futebol-nacional/2--liga/leixoes/detalhe/report','portugal-liga-2')])
def test_club_source_category_beats_incidental_national_debut(url,key):
    a=article('Club coach calls for patience with the squad','The football club is adapting to its division.','A newly signed forward has already made his national team debut.',url)
    assert source_menu_association(url)==key and football_news_section(a)==key

@pytest.mark.parametrize('url',[
 'https://www.marca.com.evil.test/futbol/primera-division/2026/10/04/report.html',
 'https://www.marca.com@evil.test/futbol/primera-division/2026/10/04/report.html',
 'https://www.marca.com:444/futbol/primera-division/2026/10/04/report.html',
 'https://www.marca.com/futbol/primera-division.html',
 'https://www.marca.com/futbol/futbol-femenino/2026/10/04/report.html',
 'https://www.record.pt/futebol/futebol-nacional/liga-betclic/news'])
def test_unverified_article_paths_do_not_gain_a_domestic_menu(url):
    assert source_menu_association(url) is None

def test_national_women_youth_and_uncovered_cups_are_not_forced_to_domestic_category():
    url='https://www.marca.com/futbol/primera-division/2026/10/04/report.html'
    assert football_news_section(article('Canada beat Peru in football friendly',body='The team captain plays for a domestic club.',source_url=url))=='football-national-teams'
    assert football_news_section(article('Youth football teams win their matches',source_url=url))=='football-youth'
    assert football_news_section(article('Women football team announces preparations',source_url=url))=='football-women'
    assert football_news_section(article('Unknown cup final ends after extra time',source_url=url)) is None

def test_club_governance_has_its_own_menu():
    assert football_news_section(article('European clubs gain a larger role in football governance through EFC and UC3'))=='football-international'

BODY='U šestom kolu lige pioniri su na gostovanju bili ubedljivi protiv rivala i ostvarili pobedu. '*12
OTHER='UNRELATED RECOMMENDATION CARD WITH INVENTED PLAYERS'
PHOTO='https://fknapredak.rs/wp-content/uploads/2026/08/bozanic.jpg'
URL='https://fknapredak.rs/tri-pobede-danas-3/'

def napredak(root=True,content=True,hero=True,extra_image=False,paid=False,canonical=URL,prose=BODY):
    photo=f'<img width="2048" height="1365" src="{PHOTO}"/>'
    if extra_image:photo+='<img width="1200" height="800" src="https://fknapredak.rs/wp-content/uploads/2026/08/another.jpg"/>'
    return (f'<link rel="canonical" href="{canonical}">'
      '<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','isAccessibleForFree':not paid,'articleBody':BODY})+'</script>'
      '<main><p>'+OTHER+'</p>'
      f'<div class="{"elementor-location-single type-post status-publish post-25059" if root else "changed-root"}">'
      f'<div class="{"elementor-widget-theme-post-content" if content else "changed-content"}"><p>{prose}</p></div>'
      f'<div class="{"elementor-widget-theme-post-featured-image" if hero else "changed-hero"}">{photo}</div></div>'
      '<aside><p>'+OTHER+'</p><img width="1400" height="800" src="https://other.example/card.jpg"/></aside></main>')

def test_napredak_own_body_and_single_featured_photo():
    text=article_text_from_html(napredak())
    assert text.startswith(YOUTH_CONTEXT) and BODY.strip() in text and OTHER not in text
    photos=collect_page_image_candidates(napredak())
    assert len(photos)==1 and photos[0]['url']==PHOTO and photos[0]['width']==2048

@pytest.mark.parametrize('kwargs',[{'root':False},{'content':False},{'paid':True},{'prose':''}])
def test_changed_or_paid_body_never_uses_hidden_schema(kwargs):
    assert not article_text_from_html(napredak(**kwargs))

@pytest.mark.parametrize('kwargs',[{'root':False},{'content':False},{'hero':False},{'paid':True},{'extra_image':True},{'prose':''},{'canonical':'https://fknapredak.rs/feed/'}])
def test_missing_or_ambiguous_hero_never_uses_other_cards(kwargs):
    assert not collect_page_image_candidates(napredak(**kwargs))

def test_senior_contract_with_youth_biography_is_not_youth_news():
    senior='The football club has confirmed a new first-team signing for the coming season. The player previously represented the club as a junior and has now joined the senior squad.'
    assert YOUTH_CONTEXT not in article_text_from_html(napredak(prose=senior))

def test_youth_marker_must_be_preserved_in_generated_lead():
    assert preserve_youth_qualifier_reason(YOUTH_CONTEXT,{'title':'Napredak record three victories','summary':'The club won its matches.'})
    assert not preserve_youth_qualifier_reason(YOUTH_CONTEXT,{'title':'Napredak youth teams record three victories'})
    assert not preserve_youth_qualifier_reason('The senior squad welcomes a former youth player.',{'title':'Club signs a player'})

@pytest.mark.parametrize('host,cls',[('www.asroma.com','asr-article-main-content'),('www.juventus.com','oc-c-article__body')])
def test_italian_club_prose_scoped_no_schema_fallback(host,cls):
    path='/en/news/76025/interview' if 'asroma' in host else '/en/news/articles/report'
    intro=f'<link rel="canonical" href="https://{host}{path}">'
    schema='<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','articleBody':BODY})+'</script>'
    html=intro+schema+f'<main><p>{OTHER}</p><div class="{cls}"><p>{BODY}</p></div><aside><p>{OTHER}</p></aside></main>'
    assert BODY.strip() in article_text_from_html(html) and OTHER not in article_text_from_html(html)
    assert article_text_from_html(html.replace(f'class="{cls}"','class="changed"'))==''

def test_new_desks_join_existing_intake_without_blanket_league():
    from bot.news_football_sources import RSS_FEEDS as all_rss,HTML_INDEXES as all_html
    for cfg in RSS_FEEDS:assert cfg in all_rss and cfg['article_body_required'] and not cfg.get('league')
    for cfg in HTML_INDEXES:assert cfg in all_html and cfg['article_path_re'] and not cfg.get('league')
    assert len({c['id'] for c in all_html})==len(all_html)

@pytest.mark.parametrize('item',[
 {'title':'Asier Aguirre leads the Porto Santo Iberian Open','body':'The Spanish golfer recorded seven birdies, no bogeys and completed the round in 65 strokes.'},
 {'title':'Comité Olímpico de Portugal awards five grants for sports research projects'},
 {'title':'Competitor finishes the opening round','url':'https://www.record.pt/modalidades/golfe/detalhe/report'}])
def test_non_football_evidence_held_not_rewritten(item):
    assert football_scope_conflict(item,'football')=='taxonomy_football_scope_conflict'
    assert football_scope_conflict(item,'golf') is None

@pytest.mark.parametrize('item',[
 {'title':'Football club holds a charity golf day','body':'A golfer made birdies and completed the holes.'},
 {'title':'Comité Olímpico de Portugal awards football research grants'},
 {'title':'Club wins opening match','body':'The team played well and won.'},
 {'title':'Investor joins club','body':'He also plays golf.'}])
def test_incidental_golf_and_football_research_not_rejected(item):
    assert football_scope_conflict(item,'football') is None

def test_published_leaves_do_not_consume_official_hydration_quota(monkeypatch):
    from bot import news_official_indexes as idx
    cfg={'id':'bounded-fixture','host':'club.example','sport':'football'}
    urls=['https://club.example/news/'+str(i) for i in range(8)]
    monkeypatch.setattr(idx,'_anchor_candidates',lambda cfg:[(u,'Story') for u in urls])
    calls=[]
    monkeypatch.setattr(idx,'_hydrate',lambda cfg,url,title,**kwargs:calls.append(url) or {'url':url})
    rows=idx._hydrate_source(cfg,3,known_urls=urls[:3])
    assert [r['url'] for r in rows]==urls[3:6] and calls==urls[3:6]
    calls.clear()
    assert idx._hydrate_source(cfg,3,known_urls=urls)==[] and calls==[]

def test_new_candidate_still_needs_full_hydration(monkeypatch):
    from bot import news_official_indexes as idx
    cfg={'id':'bounded-fixture','host':'club.example','sport':'football'}
    urls=['https://club.example/news/'+str(i) for i in range(8)]
    monkeypatch.setattr(idx,'_anchor_candidates',lambda cfg:[(u,'Story') for u in urls])
    calls=[]
    def hydrate(cfg,url,title,**kwargs):
        calls.append(url)
        return None if url==urls[3] else {'url':url}
    monkeypatch.setattr(idx,'_hydrate',hydrate)
    assert [r['url'] for r in idx._hydrate_source(cfg,2,known_urls=urls[:3])]==urls[4:6]
    assert calls==urls[3:6]

def test_missing_dates_not_admitted_by_new_intake(monkeypatch):
    from bot import news_official_indexes as idx
    monkeypatch.setattr(idx,'read_news_feed',lambda _:b'<html>No current source date</html>')
    assert idx._hydrate(HTML_INDEXES[0],'https://www.asroma.com/en/news/76025/interview','Interview') is None

def test_menu_repair_preserves_copy_dates_and_held_rows():
    from database import SessionLocal
    from models import Article,ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    from bot.news_league_index import repair_football_league_menus
    db=SessionLocal();ids=[]
    stamp=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(hours=1)
    try:
        for i,public in enumerate((True,False)):
            a=Article(title='France and Italy prepare for football match',summary='The national sides are preparing.',content='Keep the original copy.',slug='fill-b-preserve-'+str(i),sport='football',ai_generated=True,published_at=stamp,image_url='https://example.test/own.jpg')
            db.add(a);db.flush();ids.append(a.id)
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolver_version=RESOLVER_VERSION,resolved_sport='football',public_ok=public,quality_ok=True))
        db.commit()
        assert repair_football_league_menus(db)==1
        assert db.get(Article,ids[0]).league=='football-national-teams' and db.get(Article,ids[1]).league is None
        assert repair_football_league_menus(db)==0
        assert all(a.published_at==stamp and a.content=='Keep the original copy.' for a in db.query(Article).filter(Article.id.in_(ids)))
    finally:
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit();db.close()
