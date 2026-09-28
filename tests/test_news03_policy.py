from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bot.news_policy import canonical_news_url, fair_news_queue, freshness_reason, non_article_news_reason, original_draft_reason, source_path_sport_hint
from sports_registry.sports import SPORTS

NOW = datetime(2026, 9, 26, 6, tzinfo=timezone.utc)
SOURCE = ('Arsenal confirmed the midfielder will miss the next Premier League match after a training injury. '
          'The club announced further tests and did not give a date for his return to the squad.')
DRAFT = {'title':'Arsenal midfielder ruled out of upcoming league fixture',
         'summary':'Further tests are planned following an injury in training.',
         'body':('An injury sustained during training has ruled an Arsenal midfielder out of the upcoming Premier League fixture. '
                 'Arsenal said further tests are planned, while a return date remains unconfirmed by the club.')}

def item(sport='football', index=0, stamp=None, url=None):
    return {'sport_fixture':sport, 'title':f'{sport} original report {index}', 'url':url or f'https://example.test/{sport}/{index}',
            'published_at':stamp or NOW-timedelta(hours=1)}

def classify(row): return SimpleNamespace(sport=row.get('sport_fixture'))

@pytest.mark.parametrize('value', [None, '', 'javascript:alert(1)', 'https://u:p@example.test/a', 'https://example.test:12/a', 'http://', [], 'https://[bad'])
def test_invalid_source_urls(value): assert canonical_news_url(value) is None

def test_canonical_url_preserves_semantic_queries_and_removes_only_tracking():
    assert canonical_news_url('https://EXAMPLE.test/story?id=24&utm_source=x&fbclid=x#one')=='https://example.test/story?id=24'
    assert canonical_news_url('https://example.test/story?id=25') != canonical_news_url('https://example.test/story?id=24')

@pytest.mark.parametrize('stamp,reason', [(None,'publication_time_unverified'),('2026-09-26','publication_time_unverified'),
    (NOW.replace(tzinfo=None),'publication_time_unverified'),(NOW+timedelta(seconds=1),'future_publication'),
    (NOW-timedelta(hours=73),'stale_publication'),(NOW-timedelta(hours=72),None),(NOW,None)])
def test_freshness_never_invents_source_time(stamp,reason): assert freshness_reason(stamp,NOW)==reason

def test_round_robin_includes_every_sport_before_second_item():
    sports=[s['id'] for s in SPORTS if s['active'] and s['supports_news']]
    rows=[item(s,i) for s in sports for i in range(3)]
    before=repr(rows)
    result,reasons=fair_news_queue(rows,classify,now=NOW,sport_order=sports)
    assert len(result)==123 and not reasons
    assert {r['sport_fixture'] for r in result[:41]}==set(sports)
    assert repr(rows)==before

def test_small_budget_rotates_start_across_cycles():
    rows=[item(s) for s in ('football','basketball','tennis')]
    starts={fair_news_queue(rows,classify,now=NOW+timedelta(minutes=10*i))[0][0]['sport_fixture'] for i in range(3)}
    assert starts=={'football','basketball','tennis'}

def test_newest_first_inside_each_sport_not_feed_order():
    rows=[item('football',1,NOW-timedelta(hours=20)),item('football',2,NOW-timedelta(hours=1))]
    result,_=fair_news_queue(rows,classify,now=NOW)
    assert result[0]['title'].endswith('2')

def test_old_future_unknown_and_duplicate_metadata_are_not_queued():
    rows=[item(url='https://example.test/story?utm_source=a'),item(url='https://example.test/story?utm_source=b'),
          item(index=3,stamp=NOW-timedelta(days=20)),item(index=4,stamp=NOW+timedelta(days=1)),item(sport=None,index=5)]
    result,reasons=fair_news_queue(rows,classify,now=NOW)
    assert len(result)==1
    assert reasons=={'duplicate_source_url':1,'stale_publication':1,'future_publication':1,'unknown_sport':1}

def test_original_factual_brief_passes_without_padding(): assert original_draft_reason(DRAFT,'Arsenal injury update',SOURCE) is None

@pytest.mark.parametrize('body,reason', [(SOURCE,'copied_source_body'),('Read the full story at https://example.test/x','external_link_in_copy'),
    ('The midfielder will return in 37 days. '+DRAFT['body'],'unsupported_number'),
    ('The manager said "We will win every single match this year." '+DRAFT['body'],'direct_quote_requires_review'),
    (DRAFT['body']+'\nSource: Example News','publisher_footer'),('Tiny incomplete story','insufficient_original_body')])
def test_unsafe_drafts_held(body,reason):
    assert original_draft_reason({**DRAFT,'body':body},'Arsenal injury update',SOURCE)==reason

def test_reordered_copied_paragraphs_are_held():
    source=SOURCE+' '+('A lengthy account described the club medical assessment and the next planned training session. '*6)
    output='A lengthy account described the club medical assessment and the next planned training session. '+SOURCE
    assert original_draft_reason({**DRAFT,'body':output},'Arsenal injury update',source)=='excessive_source_overlap'

@pytest.mark.parametrize('draft', [None,{},[],{'title':'ok','summary':'ok','body':{}},{**DRAFT,'title':''}])
def test_missing_drafts_do_not_publish(draft): assert original_draft_reason(draft,'Title',SOURCE)=='missing_original_draft'

def test_personal_life_headline_is_rejected_before_queueing():
    row=item('winter-sports', 90)
    row['title']='Ex-Ski-Weltmeisterin ist kurz nach Hochzeit Mama geworden'
    result,reasons=fair_news_queue([row],classify,now=NOW)
    assert result == []
    assert reasons == {'non_sports_personal_life': 1}


def test_personal_news_with_explicit_competition_impact_is_kept():
    row=item('tennis', 91)
    row['title']='Player misses final after becoming a father'
    result,reasons=fair_news_queue([row],classify,now=NOW)
    assert result == [row]
    assert reasons == {}



def test_underfilled_sport_beats_overstocked_high_score_sport():
    hockey=item('ice-hockey', 1)
    hockey['title']='Ice hockey champion wins final title trophy'
    lacrosse=item('lacrosse', 1)
    lacrosse['title']='Lacrosse team names squad'
    result,_=fair_news_queue(
        [hockey,lacrosse],
        classify,
        now=NOW,
        sport_order=['ice-hockey','lacrosse'],
        sport_inventory={'ice-hockey':169,'lacrosse':1},
        coverage_floor=6,
    )
    assert result[0]['sport_fixture']=='lacrosse'


def test_lowest_inventory_wins_after_basic_floor():
    football=item('football', 1)
    tennis=item('tennis', 1)
    result,_=fair_news_queue(
        [football,tennis],
        classify,
        now=NOW,
        sport_order=['football','tennis'],
        sport_inventory={'football':30,'tennis':7},
        coverage_floor=6,
    )
    assert result[0]['sport_fixture']=='tennis'


def test_major_sport_gets_early_lane_while_emptiest_sport_stays_first():
    football=item('football', 1)
    lacrosse=item('lacrosse', 1)
    netball=item('netball', 1)
    result,_=fair_news_queue(
        [football,lacrosse,netball],
        classify,
        now=NOW,
        sport_order=['football','lacrosse','netball'],
        sport_inventory={'football':4,'lacrosse':0,'netball':0},
        coverage_floor=6,
    )
    assert result[0]['sport_fixture'] in {'lacrosse','netball'}
    assert result[1]['sport_fixture']=='football'


def test_major_sport_anchor_stops_after_target_is_reached():
    football=item('football', 1)
    lacrosse=item('lacrosse', 1)
    netball=item('netball', 1)
    result,_=fair_news_queue(
        [football,lacrosse,netball],
        classify,
        now=NOW,
        sport_order=['football','lacrosse','netball'],
        sport_inventory={'football':12,'lacrosse':0,'netball':0},
        coverage_floor=6,
    )
    assert {result[0]['sport_fixture'], result[1]['sport_fixture']} == {'lacrosse','netball'}


def test_equally_empty_sports_prefer_admission_ready_candidate():
    raw=item('lacrosse', 1)
    raw['title']='Lacrosse team prepares for international match'
    ready=item('netball', 1)
    ready['title']='Netball team prepares for international match'
    ready['_extracted']='Netball source body with verified competition facts.'
    ready['_extracted_image']='https://example.test/netball-photo.jpg'
    result,_=fair_news_queue(
        [raw,ready],
        classify,
        now=NOW,
        sport_order=['lacrosse','netball'],
        sport_inventory={'lacrosse':0,'netball':0},
        coverage_floor=6,
    )
    assert result[0]['sport_fixture']=='netball'


@pytest.mark.parametrize(
    "url,sport",
    [
        ("https://www.record.pt/modalidades/tenis/detalhe/francisco-cabral", "tennis"),
        ("https://www.novosti.rs/sport/fudbal/1653155/srbija-holandija", "football"),
        ("https://www.record.pt/internacional/competicoes-de-selecoes/liga-das-nacoes/detalhe/alemanha", "football"),
        ("https://isport.blesk.cz/clanek/fotbal-reprezentace-liga-narodu/480343/nemecko-recko.html", "football"),
        ("https://isport.blesk.cz/clanek/ostatni-cyklistika/480345/pad-vacka.html", "cycling"),
        ("https://www.blick.ch/sport/motorsport/buemi-toyota-japan-id1.html", "motorsport"),
        ("https://www.bbc.co.uk/sport/rugby-union/articles/cx05r4gg209ro", "rugby"),
        ("https://www.bbc.co.uk/sport/cricket/videos/cmdx0wvdlkwjo", "cricket"),
        ("https://www.bbc.co.uk/sport/boxing/articles/c69w42r4zel9o", "boxing"),
    ],
)
def test_trusted_source_path_sport_hints(url, sport):
    assert source_path_sport_hint(url) == sport


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/www.bbc.co.uk/sport/rugby-union/articles/x",
        "https://www.bbc.co.uk/news/articles/x",
        "https://www.record.pt/fora-de-campo/detalhe/x",
        "https://blick.ch/sport/motorsport/x",
    ],
)
def test_source_path_hint_requires_exact_trusted_host_and_path(url):
    assert source_path_sport_hint(url) is None


@pytest.mark.parametrize(
    "url,reason",
    [
        (
            "https://www.record.pt/jogo-da-vida/detalhe/queda-em-direto-debora-monteiro",
            "non_sports_lifestyle_section",
        ),
        (
            "https://www.record.pt/fora-de-campo/detalhe/centeno-politica",
            "non_sports_off_field_section",
        ),
    ],
)
def test_record_non_sports_sections_are_rejected_before_classification(url, reason):
    row={"title":"Publisher lifestyle item","url":url}
    assert non_article_news_reason(row)==reason


def test_record_sport_sections_are_not_blocked_by_section_filter():
    row={
        "title":"Francisco Cabral vence em Hangzhou",
        "url":"https://www.record.pt/modalidades/tenis/detalhe/francisco-cabral",
    }
    assert non_article_news_reason(row) is None


def test_today_candidate_outranks_equivalent_yesterday_candidate(monkeypatch):
    from bot.news_policy import queue_priority_score
    monkeypatch.setenv("NEWS_EDITORIAL_TIMEZONE","Australia/Sydney")
    now=datetime(2026,9,28,3,0,tzinfo=timezone.utc)
    today={"title":"Football squad update","published_at":datetime(2026,9,28,1,0,tzinfo=timezone.utc)}
    yesterday={"title":"Football squad update","published_at":datetime(2026,9,27,12,0,tzinfo=timezone.utc)}
    assert queue_priority_score(today,now) > queue_priority_score(yesterday,now)
