import pytest

from bot import news_image_http as images


class Response:
    def __init__(self, status=200, content_type="image/jpeg", body=b"\xff\xd8\xfffixture", location=""):
        self.status_code=status
        self.headers={"content-type":content_type}
        if location:
            self.headers["location"]=location
        self._body=body

    def __enter__(self):
        return self

    def __exit__(self,*args):
        return False

    def iter_bytes(self):
        yield self._body


class Client:
    def __init__(self, responses):
        self.responses=list(responses)
        self.calls=[]

    def stream(self, method, url):
        self.calls.append((method,url))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    images.clear_image_probe_cache()
    monkeypatch.setattr(images,"validate_public_url",lambda url:None)


def test_image_probe_accepts_real_image_bytes():
    client=Client([Response()])
    ok,reason=images.probe_news_image("https://cdn.example/photo",client=client)
    assert ok is True and reason=="ok"
    assert client.calls==[("GET","https://cdn.example/photo")]


def test_image_probe_rejects_html_even_with_200():
    client=Client([Response(content_type="text/html",body=b"<html>blocked</html>")])
    ok,reason=images.probe_news_image("https://cdn.example/photo",client=client)
    assert ok is False and reason=="not_image_content"


def test_image_probe_rejects_hotlink_http_failure():
    client=Client([Response(status=403,content_type="text/html",body=b"forbidden")])
    ok,reason=images.probe_news_image("https://cdn.example/photo",client=client)
    assert ok is False and reason=="http_403"


def test_image_probe_follows_bounded_public_redirect():
    client=Client([
        Response(status=302,content_type="",body=b"",location="https://media.example/final.jpg"),
        Response(status=200,content_type="image/jpeg",body=b"\xff\xd8\xffimage"),
    ])
    ok,reason=images.probe_news_image("https://cdn.example/photo",client=client)
    assert ok is True and reason=="ok"
    assert client.calls[-1]==("GET","https://media.example/final.jpg")


def test_image_probe_cache_avoids_repeat_request():
    client=Client([Response()])
    assert images.probe_news_image("https://cdn.example/photo",client=client)[0] is True
    assert images.probe_news_image("https://cdn.example/photo",client=Client([]))[0] is True


def test_image_probe_rejects_empty_image_mime_response():
    client=Client([Response(status=200,content_type="image/jpeg",body=b"")])
    ok,reason=images.probe_news_image("https://cdn.example/empty.jpg",client=client)
    assert ok is False and reason=="empty_image_response"
