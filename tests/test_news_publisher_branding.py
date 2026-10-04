from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from bot.news_publisher_media import is_publisher_branding, soccernews_article_images
from bot.extract import collect_page_image_candidates
from editorial import classify_media_url, news_image_is_publishable, public_media_items

BAD='https://www.soccernews.com/og/og-image.png'
PHOTO='https://images.performgroup.com/di/library/omnisport/74/78/fernandes.jpg?t=130271473'
URL='https://www.soccernews.com/ronaldo-row-cannot-divide-portugal/405791/'
TITLE='Ronaldo row cannot divide Portugal, says Fernandes'

def page(extra=''):
 return (f'<link rel="canonical" href="{URL}"><meta property="og:title" content="{TITLE}">'
         f'<meta property="og:image" content="{BAD}"><main><img src="https://gravatar.com/avatar/person" alt="Author">'
         f'<img src="{PHOTO}" alt="{TITLE}">{extra}</main>')

@pytest.mark.parametrize('url',[BAD,BAD+'?cache=123',BAD.replace('www.',''),BAD.replace('png','webp'),BAD.replace('og-image','%6fg-image')])
def test_reachable_shared_publisher_card_is_not_an_editorial_photo(url):
 assert is_publisher_branding(url)
 assert classify_media_url(url)=='CREST_OR_LOGO'
 assert not news_image_is_publishable(url)

@pytest.mark.parametrize('url',[PHOTO,'https://soccernews.com.evil.test/og/og-image.png','https://another.test/og/og-image.png','https://www.soccernews.com/uploads/actual-photo.jpg',None,{},[]])
def test_other_photographs_and_invalid_values_are_not_labelled_this_brand(url):
 assert not is_publisher_branding(url)


def test_same_article_headline_photo_replaces_default_metadata_and_ignores_cards():
 images=collect_page_image_candidates(page('<img src="https://images.performgroup.com/other.jpg" alt="Another unrelated news headline">'))
 assert [p['url'] for p in images]==[PHOTO]
 assert images[0]['in_article']


def test_no_matched_visible_photo_means_no_invented_replacement():
 raw=page().replace(f'<img src="{PHOTO}" alt="{TITLE}">','')
 assert collect_page_image_candidates(raw)==[]
 assert collect_page_image_candidates(page().replace(TITLE+'">','Wrong title">',1))==[]


def test_generic_photo_on_another_publisher_is_not_silently_reclassified():
 assert soccernews_article_images('https://other.test/story/123/',TITLE,[{'url':PHOTO,'source':'body','alt':TITLE}]) is None
 assert soccernews_article_images('https://www.soccernews.com/',TITLE,[]) is None


def test_legacy_media_record_cannot_restore_logo_as_hero_after_repair():
 legacy=SimpleNamespace(id=1,url=BAD,is_hero=True,sort_order=0)
 assert public_media_items(PHOTO,[legacy])[0]['url']==PHOTO


def test_existing_public_article_repairs_own_photo_without_changing_story_or_date(monkeypatch):
 import public_index
 from bot import news_image_http as images
 article=SimpleNamespace(id=22943,image_url=BAD,source_url=URL,title=TITLE,published_at='2026-10-03T23:32:58',content='Original unchanged reporting.')
 tax=SimpleNamespace(public_ok=True,hero_media_kind='EDITORIAL_PHOTO')
 db=Mock(); query=db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value
 query.all.side_effect=[[(article,tax)],[]]
 monkeypatch.setattr(images,'probe_news_images',lambda urls,**kw:{})
 monkeypatch.setattr(public_index,'_reachable_source_image',lambda url,**kw:PHOTO if url==URL else None)
 monkeypatch.setattr(public_index,'_image_repair_resolution',lambda *args:object())
 def persist(db,a,resolved,**kwargs):tax.hero_media_kind='EDITORIAL_PHOTO';return tax
 monkeypatch.setattr(public_index,'persist_public_article',persist)
 before=(article.title,article.published_at,article.content,article.id)
 assert public_index.repair_recent_news_images(db,recover_limit=1)==1
 assert article.image_url==PHOTO and tax.public_ok
 assert (article.title,article.published_at,article.content,article.id)==before
 db.commit.assert_called_once()


def test_no_real_source_image_holds_record_instead_of_showing_publisher_logo(monkeypatch):
 import public_index
 from bot import news_image_http as images
 article=SimpleNamespace(id=2,image_url=BAD,source_url=URL)
 tax=SimpleNamespace(public_ok=True,hero_media_kind='EDITORIAL_PHOTO')
 db=Mock();query=db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value
 query.all.side_effect=[[(article,tax)],[]]
 monkeypatch.setattr(images,'probe_news_images',lambda urls,**kw:{})
 monkeypatch.setattr(public_index,'_reachable_source_image',lambda *args,**kw:None)
 assert public_index.repair_recent_news_images(db,recover_limit=1)==1
 assert not tax.public_ok and article.image_url is None and article.id==2
