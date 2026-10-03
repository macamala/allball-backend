import pytest
from bot.textutil import clean_text, strip_truncation_markers
from bot.extract import paragraphs_from_html
from bot.rewrite_ai import parse_ai_output
from editorial import sanitize_body

@pytest.mark.parametrize('text',[
    'The club confirmed the signing.', 'The total was 2.5.',
    'The club is based in the U.S.', 'Training has finished!',
    'Who will lead training?', 'The coach confirmed the player’s return.',
])
def test_real_sentence_terminators_are_not_rss_truncation(text):
    assert strip_truncation_markers(text)==text
    assert clean_text(text)==text

@pytest.mark.parametrize('text',['The club announced...','The club announced …','The club announced..','The club announced [+100 chars]'])
def test_actual_truncation_markers_still_disappear(text):
    assert strip_truncation_markers(text)=='The club announced'


def test_multi_paragraph_source_to_editorial_path_keeps_boundaries_and_periods():
    first='The football club announced that the midfielder had completed his return to training.'
    second='The coach confirmed that the remaining squad would continue preparations together at the training ground.'
    extracted=paragraphs_from_html(f'<article><p>{first}</p><p>{second}</p><aside><p>Subscribe to our newsletter for more stories.</p></aside></article>')
    assert extracted==first+'\n\n'+second
    result=parse_ai_output('Club confirms midfielder training return\n\nThe midfielder has rejoined training.\n\n'+extracted)
    assert sanitize_body(result['body'])==extracted
    assert 'Subscribe' not in extracted


def test_cleanup_does_not_add_punctuation_to_an_unfinished_source():
    assert clean_text('The club confirmed')=='The club confirmed'
