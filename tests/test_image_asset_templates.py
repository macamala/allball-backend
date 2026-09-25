import pytest
from collector.image_assets import image_asset_url
from collector.display import sanitize_side
from collector.adapters_feeds import _asset_url

@pytest.mark.parametrize('kind,eid',[('flags','MYA'),('flags','TLS'),('teams','1894031'),('teams','1885981')])
def test_official_verified_artwork_template_uses_real_rendering_route(kind,eid):
    raw=f'https://api.fifa.com/api/v3/picture/{kind}-{{format}}-{{size}}/{eid}'
    expected=f'https://api.fifa.com/api/v3/picture/{kind}-sq-2/{eid}'
    assert image_asset_url(raw)==expected
    assert image_asset_url(raw.replace('{','%7B').replace('}','%7D'))==expected
    assert _asset_url({'PictureUrl':raw})==expected
    assert _asset_url({'image':{'url':raw}})==expected
    original={'name':'Myanmar','logo':raw};got=sanitize_side(original,sport='football')
    assert got['logo']==expected and original['logo']==raw

@pytest.mark.parametrize('url',[
    '',None,'https://official.example/club.png',
    'https://api.fifa.com.evil.invalid/api/v3/picture/flags-{format}-{size}/MYA',
    'https://user@api.fifa.com/api/v3/picture/flags-{format}-{size}/MYA',
    'https://api.fifa.com/api/v3/picture/flags-sq-2/MYA',
    'https://api.fifa.com/api/v3/picture/flags-{other}-{size}/MYA',
    'https://api.fifa.com/api/v3/picture/flags-{format}-{size}/../MYA',
    'https://api.fifa.com/api/v3/picture/other-{format}-{size}/123',
    'http://api.fifa.com/api/v3/picture/flags-{format}-{size}/MYA',
])
def test_unrelated_invalid_or_completed_urls_are_not_rewritten(url):
    assert image_asset_url(url)==url
