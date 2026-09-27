import copy
import json

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


def test_long_article_is_held_instead_of_partially_translated(monkeypatch):
    article=type('ArticleFixture', (), {
        'title':'Northbridge Athletic update',
        'summary':'A complete update.',
        'ai_content':None,
        'content':'A' * 12001,
    })()
    called=[]
    monkeypatch.setattr(translations, 'free_json_completion', lambda *args, **kwargs: called.append(True))
    assert translations.translate_article_payload(article) is None
    assert called == []

def test_translation_masks_and_restores_exact_protected_name(monkeypatch):
    article=type('ArticleFixture', (), {
        'id':22002,
        'title':'Alcaraz lifts Laver Cup after a dramatic contest',
        'summary':'Laver Cup stays with Europe after a narrow finish.',
        'ai_content':(
            'Alcaraz carried the final passage of the contest with patience and nerve as Laver Cup '
            'remained the centre of the story. Europe found its finish after a long sporting afternoon, '
            'and the article keeps its warmth without adding any new event, statistic, quote or claim.'
        ),
        'content':None,
    })()
    seen={}
    token='__NINKONAME_A__'

    def fake_completion(system, prompt, **kwargs):
        seen['prompt']=prompt
        body=(
            f'Alcaraz carried the final passage of the contest with patience and nerve as {token} '
            'remained the centre of the story. Europe found its finish after a long sporting afternoon, '
            'and the article keeps its warmth without adding any new event, statistic, quote or claim.'
        )
        payload={
            language:{
                'title':f'Alcaraz lifts {token} after a dramatic contest',
                'summary':f'{token} stays with Europe after a narrow finish.',
                'body':body,
            }
            for language in translations.LANGUAGES
        }
        return json.dumps(payload)

    monkeypatch.setattr(translations, 'free_json_completion', fake_completion)
    result=translations.translate_article_payload(article)

    assert result
    assert token in seen['prompt']
    assert 'Laver Cup' not in seen['prompt']
    for language in translations.LANGUAGES:
        combined='\n'.join(result[language].values())
        assert 'Laver Cup' in combined
        assert token not in combined

