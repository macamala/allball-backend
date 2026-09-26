from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bot.news_policy import canonical_news_url, fair_news_queue, freshness_reason, original_draft_reason
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
