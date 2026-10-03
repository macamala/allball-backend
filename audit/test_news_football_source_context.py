import json
from datetime import date
from types import SimpleNamespace
import pytest
from bot.news_football_source_context import (
    WOMEN_CONTEXT, verified_women_article_category, preserve_women_qualifier_reason,
    source_menu_association, audited_women_article, HTML_INDEXES,
)
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_football_sections import football_news_section, assign_public_football_section

URL='https://www.sportschau.de/regional/wdr/wdr-leverkusen-feiert-comeback-sieg-gegen-bremen-100.html'
TITLE='Bayer Leverkusen overcomes two-goal deficit to defeat Werder Bremen in football'
PROSE='The football team confirmed its preparations and the coach discussed the match and the available players. '*12

def meta(**overrides):
    return {'@type':'NewsArticle','mainEntityOfPage':URL,'keywords':['Fußball','Frauen'],**overrides}

def html(node,body=PROSE,url=URL):
    return f'<link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(node)}</script><main><p>{body}</p></main>'

@pytest.mark.parametrize('identity',[URL,{'@id':URL},URL+'?tracking=1#main'])
def test_womens_category_is_anchored_to_exact_news_article(identity):
    assert verified_women_article_category(html(meta(mainEntityOfPage=identity)),URL)
    assert verified_women_article_category(html({'@graph':[meta(mainEntityOfPage=identity)]}),URL)

@pytest.mark.parametrize('node',[
    meta(mainEntityOfPage=URL.replace('leverkusen','other')),
    meta(mainEntityOfPage='https://other.example/'+URL.split('/')[-1]),
    meta(mainEntityOfPage=None),meta(mainEntityOfPage=[]),meta(mainEntityOfPage={'url':URL}),
    meta(**{'@type':'AudioObject'}),meta(**{'@type':'Organization'}),meta(**{'@type':[{}]}),
    meta(keywords=['Handball','Frauen']),meta(keywords=['Fußball']),meta(keywords={'Frauen':True}),
])
def test_related_audio_navigation_other_sports_and_malformed_nodes_cannot_supply_category(node):
    assert not verified_women_article_category(html(node,body='Frauen football navigation '+PROSE),URL)

@pytest.mark.parametrize('url',[URL.replace('sportschau.de','sportschau.de.evil.example'),
    URL.replace('https://','http://'),URL.replace('https://','https://user:pass@'),
    URL.replace('sportschau.de','sportschau.de:444'),None,{},[]])
def test_unreviewed_or_invalid_canonical_cannot_supply_evidence(url):
    assert not verified_women_article_category(html(meta()),url)


def test_visible_body_gets_category_but_metadata_never_becomes_hidden_prose():
    text=article_text_from_html(html(meta()))
    assert text.startswith(WOMEN_CONTEXT+'\n\n')
    assert 'The football team confirmed' in text
    assert not article_text_from_html(html(meta(articleBody=PROSE),body=''))
    assert WOMEN_CONTEXT not in article_text_from_html(html(meta(keywords=['Fußball'])))

@pytest.mark.parametrize('lead',["Women's football report",'Female players prepare','NWSL match report','UWCL draw'])
def test_explicit_qualifier_is_preserved_in_the_visible_lead(lead):
    assert preserve_women_qualifier_reason(WOMEN_CONTEXT,{'title':lead}) is None


def test_body_only_category_does_not_fix_an_ambiguous_mens_looking_headline_and_summary(monkeypatch):
    from bot import news_fact_guard as guard
    draft={'title':TITLE,'summary':'The side won the game.','body':"The women's team won."}
    assert preserve_women_qualifier_reason(WOMEN_CONTEXT,draft)=='source_subject_qualifier_missing:women'
    assert preserve_women_qualifier_reason('Ordinary source with no category',draft) is None
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    assert guard.fact_lock_reason(draft,'Football update',WOMEN_CONTEXT+'\n'+PROSE,expected_sport='football')=='source_subject_qualifier_missing:women'


def test_existing_admitted_incident_changes_only_menu_fields():
    a=SimpleNamespace(id=22719,title=TITLE,summary='',content=PROSE,source_url=URL,
        published_at='2026-10-02T19:15:09',ai_generated=True,league='germany-bundesliga')
    tax=SimpleNamespace(public_ok=True,resolved_sport='football',resolved_competition=a.league)
    assert audited_women_article(a)
    assert assign_public_football_section(a,tax)
    assert a.league==tax.resolved_competition=='football-women'
    assert a.title==TITLE and a.content==PROSE and a.published_at=='2026-10-02T19:15:09'
    assert not assign_public_football_section(a,tax)
    a.published_at='2027-10-02';assert not audited_women_article(a)

@pytest.mark.parametrize('public,sport,ai',[(False,'football',True),(True,'basketball',True),(True,'football',False)])
def test_audited_source_cannot_admit_a_held_or_other_sport_article(public,sport,ai):
    a=SimpleNamespace(id=22719,title=TITLE,source_url=URL,published_at='2026-10-02',ai_generated=ai,league='germany-bundesliga')
    tax=SimpleNamespace(public_ok=public,resolved_sport=sport,resolved_competition=a.league)
    assert not assign_public_football_section(a,tax)

CASES=[
    ('https://www.gazzetta.gr/football/superleague/123/report','greece-super-league','content is-relative'),
    ('https://www.gazzetta.gr/football/superleague-2/123/report','greece-super-league-2','content is-relative'),
    ('https://www.laola1.at/de/red/fussball/bundesliga/news/report/','austria-bundesliga','editor-text'),
    ('https://www.laola1.at/de/red/fussball/2--liga/news/report/','austria-second-league','editor-text'),
]

@pytest.mark.parametrize('url,menu,classes',CASES)
def test_reviewed_regional_index_has_exact_article_scope_and_scoped_prose(url,menu,classes):
    assert source_menu_association(url)==menu
    markup=f'<meta property="og:url" content="{url}"><meta property="og:image" content="https://images.example/a.jpg"><div class="content mt-5"><p>UNRELATED CARDS</p></div><div class="{classes}"><p>{PROSE}</p></div><aside><p>MORE CARDS</p></aside>'
    text=article_text_from_html(markup)
    assert 'The football team confirmed' in text and 'CARDS' not in text
    assert {i['source'] for i in collect_page_image_candidates(markup)}=={'og'}
    a=SimpleNamespace(title='Club reviews preparations',summary='',content=PROSE,source_url=url,published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))==menu

@pytest.mark.parametrize('classes',['content','is-relative','content mt-5','contents is-relative'])
def test_greek_generic_layout_or_half_a_compound_class_is_not_the_article(classes):
    url=CASES[0][0]
    assert article_text_from_html(f'<meta property="og:url" content="{url}"><div class="{classes}"><p>{PROSE}</p></div>')==''

@pytest.mark.parametrize('url',['https://www.gazzetta.gr/football/superleague',
    'https://www.gazzetta.gr/football/superleague-3/123/report',
    'https://www.gazzetta.gr/basketball/superleague/123/report',
    'https://www.gazzetta.gr.evil.example/football/superleague/123/report',
    'https://www.laola1.at/de/red/fussball/bundesliga/news/',None,{}])
def test_no_country_or_sport_stamp_from_a_publisher_or_wrong_category(url):
    assert source_menu_association(url) is None

@pytest.mark.parametrize('title,expected',[
    ('UEFA Champions League draw confirmed','uefa-champions-league'),
    ("Women's football coach discusses preparations",'football-women'),
    ('Under-23 squad prepares for Asian Games','football-youth'),
    ('England wins Asian Cup match','football-national-teams'),
])
def test_primary_subject_precedes_regional_menu_fallback(title,expected):
    a=SimpleNamespace(title=title,summary='',content=PROSE,source_url=CASES[0][0],published_at='2026-10-03')
    assert football_news_section(a,today=date(2026,10,3))==expected


def test_queue_uses_original_url_but_never_assigns_a_nonfootball_candidate():
    from bot.news_football_priority import candidate_football_section
    item={'url':CASES[1][0],'title':'Club reviews preparations','summary':'','published_at':'2026-10-03'}
    assert candidate_football_section(item,SimpleNamespace(sport='football',league=None),today=date(2026,10,3))=='greece-super-league-2'
    assert candidate_football_section(item,SimpleNamespace(sport='basketball',league=None)) is None
    assert len(HTML_INDEXES)==4 and all(r['verified_official'] is False for r in HTML_INDEXES)
