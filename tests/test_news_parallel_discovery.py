from threading import Barrier, Lock

from bot import fetch_sources as fs


def test_publishers_run_together_but_same_host_stays_serial_and_ordered(monkeypatch):
    feeds = [dict(url='https://a.test/one'), dict(url='https://www.a.test/two'),
             dict(url='https://b.test/one')]
    meet = Barrier(2)
    lock = Lock()
    active = set()
    calls = []

    def fetch(feed, maximum):
        url = feed['url']
        host = 'a' if 'a.test' in url else 'b'
        with lock:
            assert host not in active
            active.add(host)
            calls.append(url)
        if url.endswith('/one'):
            meet.wait(timeout=2)
        with lock:
            active.remove(host)
        assert maximum == 20
        return [dict(url=url)]

    monkeypatch.setattr(fs, '_fetch_feed_entries', fetch)
    assert fs._collect_rss_entries(feeds, 20) == feeds
    assert calls.index(feeds[0]['url']) < calls.index(feeds[1]['url'])


def test_one_failed_feed_keeps_other_feeds_and_does_not_retry(monkeypatch):
    feeds = [dict(url='https://a.test/broken'), dict(url='https://a.test/good')]
    calls = []
    def fetch(feed, maximum):
        calls.append(feed['url'])
        if feed['url'].endswith('broken'):
            raise ValueError('robots denied')
        return [feed]
    monkeypatch.setattr(fs, '_fetch_feed_entries', fetch)
    assert fs._collect_rss_entries(feeds, 20) == [feeds[1]]
    assert calls == [f['url'] for f in feeds]
    assert fs._collect_rss_entries([], 20) == []
