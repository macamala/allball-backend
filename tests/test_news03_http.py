import socket
import httpx
import pytest
from bot import news_feed_http as net


def setup(monkeypatch, handler):
    monkeypatch.setattr(net.socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34',443))])
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr(net.httpx, 'Client', lambda **kw: client)


def test_reads_allowed_feed_bytes(monkeypatch):
    seen=[]
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200,content=b'User-agent: *\nAllow: /' if request.url.path=='/robots.txt' else b'<rss/>')
    setup(monkeypatch,handler)
    assert net.read_news_feed('https://example.test/feed')==b'<rss/>'
    assert seen==['/robots.txt','/feed']


@pytest.mark.parametrize('robots_status',[401,403,429,500,503])
def test_unverified_robots_never_fetches_feed(monkeypatch,robots_status):
    seen=[]
    def handler(request): seen.append(request.url.path); return httpx.Response(robots_status)
    setup(monkeypatch,handler)
    with pytest.raises(ValueError,match='robots_unverified'): net.read_news_feed('https://example.test/feed')
    assert seen==['/robots.txt']


def test_disallowed_redirect_not_requested(monkeypatch):
    seen=[]
    def handler(request):
        seen.append(request.url.path)
        if request.url.path=='/robots.txt': return httpx.Response(200,text='User-agent: *\nDisallow: /private')
        return httpx.Response(302,headers={'location':'/private'})
    setup(monkeypatch,handler)
    with pytest.raises(ValueError,match='robots_disallowed'): net.read_news_feed('https://example.test/feed')
    assert '/private' not in seen


@pytest.mark.parametrize('target',['http://example.test/feed','https://127.0.0.1/a','https://other.test/a','https://user:pass@example.test/feed'])
def test_unsafe_redirect_fails_closed(monkeypatch,target):
    def handler(request):
        if request.url.path=='/robots.txt': return httpx.Response(404)
        return httpx.Response(302,headers={'location':target})
    setup(monkeypatch,handler)
    with pytest.raises(ValueError): net.read_news_feed('https://example.test/feed')


def test_response_body_limit(monkeypatch):
    monkeypatch.setattr(net,'MAX_BYTES',25)
    setup(monkeypatch,lambda request: httpx.Response(404) if request.url.path=='/robots.txt' else httpx.Response(200,content=b'x'*26))
    with pytest.raises(ValueError,match='response_limit'): net.read_news_feed('https://example.test/feed')


def test_private_dns_fails_before_client(monkeypatch):
    monkeypatch.setattr(net.socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))])
    monkeypatch.setattr(net.httpx,'Client',lambda **k: pytest.fail('network attempted'))
    with pytest.raises(ValueError,match='nonpublic'): net.read_news_feed('https://example.test/feed')


@pytest.mark.parametrize('status',[202,403,429,500])
def test_feed_non200_is_not_accepted(monkeypatch,status):
    setup(monkeypatch,lambda request:httpx.Response(404) if request.url.path=='/robots.txt' else httpx.Response(status,text='<rss/>'))
    with pytest.raises(ValueError,match='feed_http'):net.read_news_feed('https://example.test/feed')
