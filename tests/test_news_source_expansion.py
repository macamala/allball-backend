"""Public CMS admission, source trust and current article discovery."""
import html
import json
from datetime import datetime, timezone
from collections import Counter

from bot import news_official_indexes as idx
from bot.news_components import public_components
from bot.news_policy import non_article_news_reason, candidate_readiness_score


def component(name, props):
    return '<div data-component="'+name+'" data-props="'+html.escape(json.dumps(props),quote=True)+'"></div>'


def cfg(name):
    return next(x for x in idx.HTML_INDEXES if x['id'] == name)


def test_chelsea_only_discovers_public_articles_from_scoped_component(monkeypatch):
    normal = dict(type='Article', requiresLogin=False, isPremiumContent=False,
                  title='Club confirms coaching appointment', url='/en/news/article/coach-confirmed')
    rows = [normal, {**normal,'type':'Gallery','url':'/en/news/article/gallery'},
            {**normal,'requiresLogin':True,'url':'/en/news/article/locked'},
            {**normal,'isPremiumContent':True,'url':'/en/news/article/premium'},
            {**normal,'url':'https://other.example/en/news/article/cross-host'}]
    page=component('NewsListModule', {'initialContent':{'items':rows}})
    page+=component('AppDownloadModule', {'url':'/en/news/article/app-promotion'})
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    assert idx._anchor_candidates(cfg('chelsea-football-news')) == [
        ('https://www.chelseafc.com/en/news/article/coach-confirmed',normal['title'])]


def test_component_missing_or_invalid_does_not_use_promotional_fallback(monkeypatch):
    page='<div data-component="NewsListModule" data-props="broken"></div>'
    page+='<a href="/en/news/article/app-promotion">App promotion</a>'
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    assert idx._anchor_candidates(cfg('chelsea-football-news')) == []
    assert public_components(page,('NewsListModule',)) == {}


def test_chelsea_article_header_uses_exact_offset_and_rejects_restricted(monkeypatch):
    stamp=datetime.now(timezone.utc).isoformat()
    page=component('ArticleHeader',{'articleHeaderDetails':{'date':stamp}})
    page+=component('ArticleLoginOverlay',{'requiresLogin':False})
    page+='<meta property="og:title" content="Chelsea confirms coaching appointment">'
    page+='<meta property="og:image" content="https://media.example/coach.jpg">'
    page+='<main><p>'+'Chelsea announced a coaching appointment and confirmed the contract terms. '*20+'</p></main>'
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    item=idx._hydrate(cfg('chelsea-football-news'),'https://www.chelseafc.com/en/news/article/coach-confirmed','')
    assert item['published_at'].isoformat() == stamp
    assert item['feed']['verified_official'] is True
    page=page.replace('&quot;requiresLogin&quot;: false','&quot;requiresLogin&quot;: true')
    reasons=Counter()
    assert idx._hydrate(cfg('chelsea-football-news'),'https://www.chelseafc.com/en/news/article/coach-confirmed','',diagnostics=reasons) is None
    assert reasons == {'restricted_article':1}


def test_nba_top_stories_scope_skips_navigation_and_uses_current_cards(monkeypatch):
    page='''<a href="/news/key-dates">Key dates</a>
        <a href="/news/category/starting-5-daily-newsletter">Newsletter</a>
        <a href="/news/player-injury-confirmed">Player ruled out after injury</a>'''
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    assert idx._anchor_candidates(cfg('nba-basketball-news')) == [
        ('https://www.nba.com/news/player-injury-confirmed','Player ruled out after injury')]


def test_cricket_article_cards_exclude_navigation_and_other_sports(monkeypatch):
    page='''<a href="/news/123/old-pinned" class="nav">Old item</a>
        <a href="/news/124/contract-confirmed" class="o-media-pod__link">Contract confirmed</a>
        <a href="https://other.example/news/125/fake" class="o-media-pod__link">Another site</a>'''
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    assert idx._anchor_candidates(cfg('cricket-australia-news')) == [
        ('https://www.cricket.com.au/news/124/contract-confirmed','Contract confirmed')]


def test_new_source_media_products_stay_out_of_news():
    for title in ['NBL Overtime: September 28, 2026','Top 10: Round 2, NBL27',
                  'Moments That Mattered: Round 2','WNCL 2026-27: All you need to know',
                  'Cheapies for Round 3: SuperCoach NBL Classic',
                  'NBL27 roster tracker: Every signing, extension and departure']:
        assert non_article_news_reason({'title':title})
    assert non_article_news_reason({'title':'Hurricanes sign Shai Hope for BBL return'}) is None
    assert non_article_news_reason({'title':'Fans celebrate','url':'https://www.liverpoolfc.com/news/gallery-anfield-derby'}) == 'non_article_photo_gallery'


def test_verified_official_is_priority_hint_without_bypassing_admission():
    base={'title':'A coaching appointment confirmed','feed':{'sport':'football','kind':'league'}}
    trusted={**base,'feed':{**base['feed'],'verified_official':True}}
    assert candidate_readiness_score(trusted) > candidate_readiness_score(base)
    assert non_article_news_reason({**trusted,'title':'NBL Overtime: September 28, 2026'}) == 'non_article_podcast'


def test_serbian_mixed_feed_uses_bounded_publisher_paths():
    from bot.news_policy import source_path_sport_hint
    from bot.feeds import FEEDS
    assert source_path_sport_hint('https://www.b92.net/sport/fudbal/vesti/123/report/vest') == 'football'
    assert source_path_sport_hint('https://www.b92.net/sport/kosarka/vesti/123/report/vest') == 'basketball'
    assert source_path_sport_hint('https://www.b92.net/sport/fudbalsomething/') is None
    assert source_path_sport_hint('https://other.example/sport/fudbal/') is None
    assert next(f for f in FEEDS if f['url']=='https://www.b92.net/rss/sport')['kind'] == 'mixed'
    for url in ['https://www.crvenazvezdafk.com/vesti/rss.xml','https://fss.rs/feed/']:
        f=next(f for f in FEEDS if f['url']==url)
        assert f['sport']=='football' and not f.get('league')


def test_serbian_products_and_rumours_are_not_new_reports():
    from bot.news_policy import gossip_news_reason
    for title in ['Звездаши бирамо најлепши гол у септембру', 'На данашњи дан - историјска победа',
                  'Na današnji dan - evropska noć', 'PREDLOZZI I TIPOVANJA (ponedeljak)',
                  'UŽIVO: Srbija - Holandija', 'ONLINE: Sparta hostí Energii']:
        assert non_article_news_reason({'title':title})
    assert gossip_news_reason({'title':'Mimović na izlaznim vratima – moguć transfer na zimu'}) == 'gossip_unconfirmed_rumour'
    assert non_article_news_reason({'title':'Zvezda potvrdila novog trenera'}) is None


def test_scoped_article_handles_optional_paragraph_end_tags_without_spilling():
    from bot.extract import article_text_from_html
    page='<p>Unrelated tennis recommendation and more unrelated news.</p>'
    page+='<div class="single-news-content"><p>Serbia confirmed the squad for the next international fixture.'
    page+='<p>The coach announced changes and explained the preparations for the match.</div>'
    page+='<div><p>Unrelated transfer speculation from another article.</p></div>'
    text=article_text_from_html(page)
    assert 'Serbia confirmed' in text
    assert 'Unrelated' not in text
    assert article_text_from_html('<div class="single-news-content"><p>Never closed') == ''


def test_mozzart_body_scope_ignores_betting_and_headline_grids():
    from bot.extract import article_text_from_html
    page='<meta property="og:url" content="https://www.mozzartsport.com/fudbal/vesti/squad/123">'
    page+='<p>PREDLOZZI I TIPOVANJA. Different club signs another player.</p>'
    page+='<div class="news-content"><p>Serbia confirmed the squad for the match against Germany.</p></div>'
    page+='<p>Recommended story about basketball.</p>'
    text=article_text_from_html(page)
    assert 'Serbia confirmed' in text and 'PREDLOZZI' not in text and 'basketball' not in text


def test_content_encoded_images_are_candidates_only():
    from bot.media_url import collect_feed_image_candidates
    entry={'summary':'Real report','content':[{'value':'<p>Report</p><img src="https://fss.rs/team.jpg" width="1200">'}]}
    assert ('https://fss.rs/team.jpg',1200) in collect_feed_image_candidates(entry)


def test_foreign_prose_with_roster_is_not_a_navigation_page():
    from bot.site_chrome import is_site_chrome_text
    prose=('Selektor je objavio sastav reprezentacije za utakmicu protiv Srbije i objasnio plan priprema. '*12)
    roster='Golmani: Noa Atubolu Fin Damen Jonas Urbig Bajern Minhen Valdemar Anton Borusija Dortmund Ridle Baku Lajpzig Fin Jelč Štutgart David Raum Lajpcig'
    assert not is_site_chrome_text(prose+'\n\n'+roster)
    assert is_site_chrome_text('Home Football Basketball Tennis Cricket Rugby Golf Racing Results Fixtures Tables Teams Players Video Photos Podcasts Scores Transfers Clubs News')


def test_global_sources_do_not_stamp_one_country_league_or_mixed_sport():
    from bot.feeds import FEEDS
    from bot.news_policy import source_path_sport_hint
    for url in ['https://www.theguardian.com/football/rss', 'https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/portada']:
        f=next(f for f in FEEDS if f['url']==url)
        assert f['sport']=='football' and not f.get('league') and not f.get('country')
    assert next(f for f in FEEDS if f['url']=='https://www.sportschau.de/index~rss2.xml')['kind']=='mixed'
    assert source_path_sport_hint('https://www.sportschau.de/handball/bundesliga/club-signs-player.html')=='handball'
    assert source_path_sport_hint('https://www.sportschau.de/fussball/nationalmannschaft/report.html')=='football'
    assert source_path_sport_hint('https://www.sportschau.de/fussball-other/') is None
    assert non_article_news_reason({'title':'An opinion | A Reporter','url':'https://www.theguardian.com/football/2026/sep/28/opinion'})=='non_article_analysis'
    assert non_article_news_reason({'title':'Club confirms appointment','url':'https://www.theguardian.com/football/2026/sep/28/appointment'}) is None


def test_uefa_sitemap_exact_publication_time_hydrates_same_article(monkeypatch):
    source=next(x for x in idx.SITEMAPS if x['id']=='uefa-football-competitions')
    url='https://www.uefa.com/uefanationsleague/news/123-greece-win/'
    stamp=datetime.now(timezone.utc).isoformat()
    sitemap=f'<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url><loc>{url}</loc><news:news><news:title>Greece win in Germany</news:title><news:publication_date>{stamp}</news:publication_date></news:news></url></urlset>'
    article='<meta property="og:title" content="Greece win in Germany"><meta property="og:image" content="https://editorial.uefa.com/match.jpg"><article><p>'+'Greece secured a victory against Germany in the Nations League. '*20+'</p></article>'
    monkeypatch.setattr(idx,'read_news_feed',lambda u:(sitemap if u==source['url'] else article).encode())
    rows=idx._hydrate_source(source,1,sitemap=True)
    assert len(rows)==1 and rows[0]['published_at'].isoformat()==stamp
    assert rows[0]['url']==url and rows[0]['feed']['sport']=='football'
    sitemap=sitemap.replace(f'<news:publication_date>{stamp}</news:publication_date>', f'<lastmod>{stamp}</lastmod>')
    assert idx._hydrate_source(source,1,sitemap=True)==[]


def test_uefa_discovery_keeps_futsal_separate_and_does_not_use_naive_dates(monkeypatch):
    source=next(x for x in idx.SITEMAPS if x['id']=='uefa-football-competitions')
    page='<urlset><url><loc>https://www.uefa.com/uefafutsalchampionsleague/news/123-report/</loc><title>Futsal report</title></url><url><loc>https://www.uefa.com/uefanationsleague/news/124-report/</loc><title>Team announcement</title><publication_date>2026-09-28</publication_date></url></urlset>'
    monkeypatch.setattr(idx,'read_news_feed',lambda u:page.encode())
    dates={}; rows=idx._sitemap_candidates(source,publication_times=dates)
    assert len(rows)==1 and '124-report' in rows[0][0] and dates=={}


def test_ihf_rss_keeps_exact_date_and_only_upgrades_verified_same_host(monkeypatch):
    from bot import fetch_sources as fetch
    from bot.feeds import FEEDS
    from email.utils import format_datetime
    source=next(x for x in FEEDS if x['url']=='https://www.ihf.info/news/rss.xml')
    now=datetime.now(timezone.utc).replace(microsecond=0)
    page=f'<rss version="2.0"><channel><title>IHF News</title><link>https://www.ihf.info/</link><description>News</description><item><title>USA qualify for Pan American Games</title><link>http://www.ihf.info/media-center/news/usa-qualify</link><pubDate>{format_datetime(now)}</pubDate></item><item><title>Untrusted cross-host link</title><link>http://other.example/article</link><pubDate>{format_datetime(now)}</pubDate></item></channel></rss>'
    monkeypatch.setattr(fetch,'read_news_feed',lambda u:page.encode())
    rows=fetch._fetch_feed_entries(source,20)
    assert len(rows)==1 and rows[0]['url']=='https://www.ihf.info/media-center/news/usa-qualify'
    assert rows[0]['published_at']==now and not rows[0]['feed'].get('league')
