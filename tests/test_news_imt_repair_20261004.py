"""Exact observed source spelling, not guessed entities or publication approval."""
import pytest
from bot.news_fact_guard import source_attested_acronyms
from bot.news_policy import non_article_news_reason

@pytest.mark.parametrize('source',['Против ИМТ је постигнут погодак.','ИМТ','Против имт.'])
def test_only_literal_serbian_acronym_has_latin_equivalent(source):
    assert 'IMT' in source_attested_acronyms(source,'football')
    assert 'IMT' not in source_attested_acronyms(source,'basketball')
    assert 'MVP' not in source_attested_acronyms(source,'football')

@pytest.mark.parametrize('source',['Против ИНТ.','ИМТА','СИМТ','The source mentions a club but no acronym.','MTI'])
def test_similar_spellings_or_context_do_not_supply_imt(source):
    assert 'IMT' not in source_attested_acronyms(source,'football')

def test_existing_latin_and_federation_spellings_remain():
    assert 'IMT' in source_attested_acronyms('IMT','football')
    assert {'UEFA','FIFA'}<=source_attested_acronyms('УЕФА и ФИФА','football')

@pytest.mark.parametrize('title',['Papers: Arsenal leading race for a winger','PAPERS: Clubs consider transfer targets'])
def test_branded_newspaper_roundup_rejected_before_ai(title):
    assert non_article_news_reason({'title':title})=='non_article_newspaper_roundup'

@pytest.mark.parametrize('title',['Club submits registration papers','Manager papers over cracks in defensive display','Players review competition rules'])
def test_ordinary_reporting_not_a_branded_roundup(title):
    assert non_article_news_reason({'title':title})!='non_article_newspaper_roundup'

URL='https://www.crvenazvezdafk.com/vesti/dijeng-postigao-najlepsi-gol-u-septembru'

def test_source_retry_matches_exact_hash_reason_and_pre_fix_time(monkeypatch):
    from bot import news_source_holds as holds
    class Cursor:
        rowcount=0
        def __init__(self):self.calls=[]
        def execute(self,sql,args=None):self.calls.append((sql,args))
        def fetchall(self):return []
        def close(self):pass
    class Conn:
        def __init__(self,c):self.c=c
        def cursor(self):return self.c
        def commit(self):pass
        def rollback(self):pass
        def close(self):pass
    cursor=Cursor()
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:'unused')
    monkeypatch.setattr(holds,'_connect',lambda _:Conn(cursor))
    monkeypatch.setattr(holds,'_SCHEMA_READY',True)
    holds.held_source_urls([URL,URL+'?different=true'])
    updates=[(sql,args) for sql,args in cursor.calls if 'audited-source-imt-spelling' in sql]
    assert len(updates)==1
    sql,args=updates[0]
    assert 'source_hash=%s' in sql and "reason='unsupported_acronym:IMT'" in sql
    assert 'updated_at < %s::timestamptz' in sql and 'expires_at > NOW()' in sql
    assert args==(holds._fingerprint(URL),'2026-10-04T06:45:00Z')
    assert 'UPDATE articles' not in sql and 'public_ok' not in sql
    cursor.calls.clear()
    holds.held_source_urls([URL+'?different=true','https://other.example/story'])
    assert not any('audited-source-imt-spelling' in sql for sql,_ in cursor.calls)
