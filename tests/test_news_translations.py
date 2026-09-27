import copy

import bot.news_translations as translations


SOURCE={
    'title':'Northbridge Athletic beat Southport United 2-1',
    'summary':'Luka Marin helped Northbridge Athletic win 2-1.',
    'body':(
        'Northbridge Athletic beat Southport United 2-1 after Luka Marin scored in the 18th minute. '
        'The result was confirmed after a competitive match in the Summer Shield. '
        'Northbridge Athletic protected the advantage while Southport United remained in the contest.'
    ),
}


def _valid_payload():
    return {
        language:{
            'title':'Northbridge Athletic beat Southport United 2-1',
            'summary':'Luka Marin helped Northbridge Athletic win 2-1.',
            'body':(
                'Northbridge Athletic beat Southport United 2-1 after Luka Marin scored in the 18th minute. '
                'The result was confirmed after a competitive match in the Summer Shield. '
                'Northbridge Athletic protected the advantage while Southport United remained in the contest.'
            ),
        }
        for language in translations.LANGUAGES
    }


def test_translation_validator_accepts_complete_name_number_preserving_payload():
    assert translations._validate(SOURCE, _valid_payload())


def test_translation_validator_rejects_invented_number():
    payload=_valid_payload()
    payload['de']['body'] += ' 99.'
    assert translations._validate(SOURCE, payload) is None


def test_translation_validator_rejects_changed_proper_name():
    payload=_valid_payload()
    payload['fr']['body']=payload['fr']['body'].replace('Southport United','Southport Club')
    payload['fr']['title']=payload['fr']['title'].replace('Southport United','Southport Club')
    assert translations._validate(SOURCE, payload) is None


def test_serbian_translation_must_be_latin_only():
    payload=_valid_payload()
    payload['sr']['summary']='Лука Marin helped Northbridge Athletic win 2-1.'
    assert translations._validate(SOURCE, payload) is None


def test_translation_validator_rejects_links_and_incomplete_shape():
    payload=_valid_payload()
    payload['es']['body'] += ' https://example.com'
    assert translations._validate(SOURCE, payload) is None
    payload=_valid_payload()
    del payload['it']['summary']
    assert translations._validate(SOURCE, payload) is None
