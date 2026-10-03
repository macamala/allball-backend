import pytest
from bot import news_fact_guard as guard
from bot.extract import _ArticleExtractor, _ScopedNewsBody, article_text_from_html, paragraphs_from_html

FIRST='The football club confirmed its training programme and explained the preparations for its next scheduled match.'
SECOND='The coach said the available squad would train together while the remaining players continued their individual work.'
JUNK='Unrelated recommendations mention another club and should never become facts in this article.'
def draft(token):
    return {'title':'Football organisation discusses its programme','summary':f'The {token} committee confirmed the programme.','body':'The organisation discussed its plans and explained the preparations.'}
def check(monkeypatch,source,token='CONCACAF',sport='football'):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    return guard.fact_lock_reason(draft(token),'Football organisation update',source,expected_sport=sport)

@pytest.mark.parametrize('token',['Concacaf','concacaf','CONCACAF','Conmebol','conmebol','CONMEBOL'])
def test_same_explicit_confederation_casing_is_not_a_new_fact(monkeypatch,token):
    assert check(monkeypatch,f'The {token} committee confirmed the programme.',token.upper()) is None

@pytest.mark.parametrize('source',['Another organisation confirmed its programme.','The PreConcacaf committee met.','The ConcacafExtra committee met.','The CONMEBOL committee met.','A concacaf_example label is not this organisation.','The Concacaf2 committee met.'])
def test_new_or_substring_confederations_remain_rejected(monkeypatch,source):
    assert check(monkeypatch,source)=='unsupported_acronym:CONCACAF'

@pytest.mark.parametrize('source,token',[('We can discuss the programme.','CAN'),('Use ac for the room.','AC'),('The MRI scan was mentioned.','UEFA')])
def test_case_handling_does_not_allow_arbitrary_acronyms(monkeypatch,source,token):
    assert check(monkeypatch,source,token)=='unsupported_acronym:'+token

def test_new_confederation_case_rule_is_scoped_to_football(monkeypatch):
    assert check(monkeypatch,'The Concacaf committee confirmed the programme.',sport='basketball')=='unsupported_acronym:CONCACAF'

@pytest.mark.parametrize('reason',['unsupported_number','direct_quote_requires_review','copied_source_headline'])
def test_originality_and_numeric_failures_cannot_be_bypassed(monkeypatch,reason):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:reason)
    assert guard.fact_lock_reason(draft('CONCACAF'),'Football update','Concacaf',expected_sport='football')==reason

@pytest.mark.parametrize('opening',['<article class>','<article CLASS>','<article class="">','<article>'])
@pytest.mark.parametrize('paragraph',['<p class>','<p class="">','<p id class>'])
def test_empty_attributes_never_abort_or_truncate_the_article(opening,paragraph):
    raw=opening+paragraph+FIRST+'</p><p>'+SECOND+'</p></article>'
    parser=_ArticleExtractor();parser.feed(raw);parser.close()
    assert len(parser.main_parts)==2
    result=paragraphs_from_html(raw)
    assert FIRST.rstrip('.') in result and SECOND.rstrip('.') in result

def test_extra_chrome_and_sidebar_exclusion_survive_empty_attributes():
    raw='<article class><p class>'+FIRST+'</p><div class="related-card"><p>'+JUNK+'</p></div><aside class><p>'+JUNK+'</p></aside><p>'+SECOND+'</p></article>'
    result=paragraphs_from_html(raw,extra_chrome_classes=('related-card',))
    assert FIRST.rstrip('.') in result and SECOND.rstrip('.') in result and JUNK[:30] not in result

@pytest.mark.parametrize('class_value',['content is-relative','is-relative content extra'])
def test_empty_layout_attributes_do_not_break_exact_scoped_body(class_value):
    raw='<meta property="og:url" content="https://www.gazzetta.gr/football/superleague/123/story"><div class><p>'+JUNK+'</p></div><div class="'+class_value+'"><p class>'+FIRST+'</p><p>'+SECOND+'</p></div>'
    result=article_text_from_html(raw)
    assert FIRST.rstrip('.') in result and SECOND.rstrip('.') in result and JUNK[:30] not in result

@pytest.mark.parametrize('class_value',['','content','is-relative','contents is-relative'])
def test_scoped_body_still_requires_both_exact_classes(class_value):
    raw='<meta property="og:url" content="https://www.gazzetta.gr/football/superleague/123/story"><div class><p>'+JUNK+'</p></div><div class="'+class_value+'"><p>'+FIRST+'</p></div>'
    assert article_text_from_html(raw)==''

def test_null_class_is_not_a_wildcard_scoped_container():
    parser=_ScopedNewsBody('verified-body')
    parser.feed('<div class><p>'+JUNK+'</p></div>');parser.close()
    assert not parser.finished and not parser.parts
