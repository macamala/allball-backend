import pytest

from bot import news_image_http as images


class Response:
    def __init__(self, status=200, content_type="image/jpeg", body=b"\xff\xd8\xff\xc0\x00\x11\x08\x03\x20\x04\xb0\x03"+b"x"*32, location=""):
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
        Response(status=200,content_type="image/jpeg",body=b"\xff\xd8\xff\xc0\x00\x11\x08\x03\x20\x04\xb0\x03"+b"x"*32),
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


def _png(width, height):
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + int(width).to_bytes(4, "big")
        + int(height).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"fixture"
    )


def test_image_probe_rejects_extreme_text_banner_geometry():
    client=Client([Response(content_type="image/png",body=_png(1200,180))])
    ok,reason=images.probe_news_image("https://cdn.example/wide-photo.png",client=client)
    assert ok is False and reason=="bad_aspect_ratio"


def test_image_probe_accepts_normal_photo_geometry():
    client=Client([Response(content_type="image/png",body=_png(1200,800))])
    ok,reason=images.probe_news_image("https://cdn.example/photo.png",client=client)
    assert ok is True and reason=="ok"


def test_image_probe_rejects_small_bbc_photo_until_actual_hero_is_checked():
    client=Client([Response(content_type="image/jpeg",body=b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x87\x00\xf0\x03"+b"x"*32)])
    ok,reason=images.probe_news_image(
        "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/example.jpg",
        client=client,
    )
    assert ok is False and reason=="image_too_small"


def test_composited_publisher_overlay_is_held_without_rewriting_or_fetching_url():
    for query in ['overlay-base64=brand','overlay=logo.png','mark64=brand','txt=headline']:
        assert images.probe_news_image('https://cdn.example/photo.jpg?'+query,client=object()) == (False,'composited_overlay')


def test_publisher_banner_filename_is_held_before_http():
    assert images.probe_news_image('https://editorial.uefa.com/resources/wpshot_paris_-_banner.jpeg?imwidth=158',client=object()) == (False,'promotional_banner')


@pytest.mark.parametrize('kind', ['VP8 ', 'VP8L', 'VP8X'])
@pytest.mark.parametrize('width,height,ok', [(158,89,False),(480,356,False),(988,556,True)])
def test_cdn_webp_dimensions_are_checked_even_under_jpeg_url(kind,width,height,ok):
    if kind == 'VP8 ':
        payload = b'\x00\x00\x00\x9d\x01\x2a' + width.to_bytes(2,'little') + height.to_bytes(2,'little')
    elif kind == 'VP8L':
        payload = b'\x2f' + ((width-1) | ((height-1)<<14)).to_bytes(4,'little') + b'\x00'*5
    else:
        payload = b'\x00'*4 + (width-1).to_bytes(3,'little') + (height-1).to_bytes(3,'little')
    body = b'RIFF' + (12+len(payload)).to_bytes(4,'little') + b'WEBP' + kind.encode() + len(payload).to_bytes(4,'little') + payload
    result=images.probe_news_image('https://cdn.example/photo.jpeg',client=Client([Response(body=body,content_type='image/webp')]))
    assert result == (ok, 'ok' if ok else 'image_too_small')


def test_mime_and_magic_without_verified_dimensions_do_not_approve_a_hero():
    result=images.probe_news_image('https://cdn.example/broken.jpeg',client=Client([Response(body=b'\xff\xd8\xffincomplete')]))
    assert result == (False,'image_dimensions_unverified')
    assert images.probe_news_image('https://cdn.example/fake.jpeg',client=Client([Response(body=b'<html>error</html>')])) == (False,'not_image_content')


def test_uefa_size_upgrade_keeps_same_photo_and_signed_urls_are_untouched():
    small='https://editorial.uefa.com/resources/same-photo.jpeg?imwidth=158'
    assert images.news_hero_url(small) == small.replace('158','1600')
    assert images.news_hero_url(small+'&sig=abc') == small+'&sig=abc'


def test_uefa_ingest_and_repair_both_probe_and_return_the_actual_hero(monkeypatch):
    from bot import fetch_sources
    import public_index
    small='https://editorial.uefa.com/resources/same-photo.jpeg?imwidth=158'
    large=small.replace('158','1600')
    seen=[]
    def probe(url):
        seen.append(url)
        return url == large
    monkeypatch.setattr(fetch_sources,'news_image_is_reachable',probe)
    monkeypatch.setattr(images,'news_image_is_reachable',probe)
    assert fetch_sources._pick_reachable_article_image([{'url':small,'source':'og'}]) == large
    assert public_index._reachable_source_image('https://www.uefa.com/news/story',current_url=small) == large
    assert seen == [large,large]
