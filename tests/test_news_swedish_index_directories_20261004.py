import pytest
from bot import news_official_indexes as index
from bot.news_index_selection import discovery_config

CFG=next(c for c in index.HTML_INDEXES if c['id']=='sweden-allsvenskan-category')
ROOT='https://fotbolldirekt.se/allsvenskan/'
DIRECTORIES=('alla-lag','spelschema','tabell')


@pytest.mark.parametrize('slug',DIRECTORIES)
def test_navigation_directory_is_not_an_article_even_with_article_like_link_text(slug):
    assert index._same_host_url(CFG['url'],ROOT+slug+'/',CFG['host'],CFG) is None
    assert index._same_host_url(CFG['url'],ROOT+slug+'/#news',CFG['host'],CFG) is None


def test_eight_genuine_links_remain_available_after_directory_prefix(monkeypatch):
    names=list(DIRECTORIES)+['confirmed-report-'+str(i) for i in range(12)]
    html=''.join('<a href="'+ROOT+slug+'/">Football report '+slug+'</a>' for slug in names)
    monkeypatch.setattr(index,'read_news_feed',lambda url:html.encode())
    selected=index._anchor_candidates(CFG)
    assert [u for u,_ in selected]==[ROOT+'confirmed-report-'+str(i)+'/' for i in range(8)]
    next_batch=index._anchor_candidates(discovery_config(CFG,[u for u,_ in selected[:4]]))
    assert [u for u,_ in next_batch]==[ROOT+'confirmed-report-'+str(i)+'/' for i in range(4,12)]


def test_reporting_about_a_schedule_or_table_is_not_a_directory():
    for slug in ('tabell-laget-gar-upp-i-topp','spelschema-andras-efter-beslut','alla-lag-bekraftar-nytt-avtal'):
        assert index._same_host_url(CFG['url'],ROOT+slug+'/',CFG['host'],CFG)==ROOT+slug+'/'
