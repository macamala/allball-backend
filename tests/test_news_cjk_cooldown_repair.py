from bot import news_source_holds as holds

class Cursor:
    rowcount=0
    def __init__(self): self.calls=[]
    def execute(self,sql,args=None): self.calls.append((sql,args))
    def fetchall(self): return []
    def close(self): pass
class Conn:
    def __init__(self,cursor): self.c=cursor;self.committed=False
    def cursor(self): return self.c
    def commit(self): self.committed=True
    def close(self): pass
    def rollback(self): pass

def test_only_requested_known_pre_fix_reason_hashes_expire(monkeypatch):
    c=Cursor();conn=Conn(c)
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:'unused')
    monkeypatch.setattr(holds,'_connect',lambda dsn:conn)
    monkeypatch.setattr(holds,'_SCHEMA_READY',True)
    urls=list(holds._CJK_REPAIR_REASONS)
    assert holds.held_source_urls(urls+['https://www.jleague.jp/news/article/99999/'])==set()
    updates=[(sql,args) for sql,args in c.calls if 'audited-cjk' in sql]
    assert len(updates)==3 and conn.committed
    for (sql,args),url in zip(updates,urls):
        assert 'source_hash=%s' in sql and 'reason=%s' in sql and 'updated_at < %s::timestamptz' in sql
        assert args==(holds._fingerprint(url),holds._CJK_REPAIR_REASONS[url],'2026-10-03T04:10:00Z')
        assert 'public_ok' not in sql and 'article' not in sql.lower()

def test_no_global_reset_or_query_parameter_url_guess(monkeypatch):
    c=Cursor();conn=Conn(c)
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:'unused');monkeypatch.setattr(holds,'_connect',lambda _:conn);monkeypatch.setattr(holds,'_SCHEMA_READY',True)
    holds.held_source_urls(['https://other.example/story','https://www.jleague.jp/news/article/35031/?arbitrary=true'])
    assert not any('audited-cjk' in sql for sql,args in c.calls)

def test_offline_holds_and_new_failures_are_not_cleared(monkeypatch):
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:None)
    monkeypatch.setattr(holds,'_MEMORY',{})
    url=next(iter(holds._CJK_REPAIR_REASONS));holds.hold_source(url,'unsupported_number')
    assert holds.source_on_cooldown(url)
    assert holds.held_source_urls([url])=={url}
