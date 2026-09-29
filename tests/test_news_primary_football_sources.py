from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import re
import pytest

from bot import fetch_sources, news_fact_guard, news_source_holds
from bot.feeds import FEEDS
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_policy import non_article_news_reason


@pytest.mark.parametrize('host,container', [('rmcsport.bfmtv.com','content_body_wrapper'),
                                         ('www.footmercato.net','wysiwygContent')])
def test_french_article_scope_excludes_unrelated_sports_and_images(host, container):
    prose = 'Le club de football a confirmé la signature du nouveau contrat de son joueur international. '
    html = f'<link rel="canonical" href="https://{host}/football/story"><meta property="og:image" content="https://photo.test/player.jpg">'
    html += f'<div class="{container}"><p>{prose*4}</p><img src="https://photo.test/story.jpg"></div>'
    html += '<article><p>Unrelated UFC fighter wins. Cycling race starts tomorrow.</p><img src="https://photo.test/unrelated.jpg"></article>'
    body = article_text_from_html(html)
    assert prose.strip() in body and 'UFC' not in body and 'Cycling' not in body
    assert all('unrelated' not in row['url'] for row in collect_page_image_candidates(html))
    assert article_text_from_html(html.replace(container,'missing-body')) == ''


def test_rmc_rss_profiles_and_old_dossiers_never_become_fresh_news(monkeypatch):
    cfg = next(x for x in FEEDS if x.get('publisher')=='RMC Sport')
    stamp = format_datetime(datetime.now(timezone.utc)-timedelta(hours=1))
    paths = ['/football/equipe-france/confirmed-news_AV-202609290156.html',
             '/football/lamine-yamal_DN-202407110349.html',
             '/tennis/confirmed-news_AV-202609290155.html']
    items = ''.join(f'<item><title>Confirmed football squad news {i}</title><link>https://rmcsport.bfmtv.com{p}</link><pubDate>{stamp}</pubDate></item>' for i,p in enumerate(paths))
    monkeypatch.setattr(fetch_sources,'read_news_feed',lambda _:f'<rss><channel>{items}</channel></rss>'.encode())
    rows = fetch_sources._fetch_feed_entries(cfg, 30)
    assert len(rows)==1 and rows[0]['url'].endswith(paths[0])
    fm = next(x for x in FEEDS if x.get('publisher')=='Foot Mercato')
    assert re.search(fm['article_path_re'],'/a2329688015966429517-player-training')
    assert not re.search(fm['article_path_re'],'/joueur/player-profile')
    assert not cfg.get('league') and not fm.get('league')


@pytest.mark.parametrize('local,canonical', [('ЦИЕС','CIES'),('ФИФА','FIFA'),('УЕФА','UEFA')])
def test_same_organisation_in_cyrillic_is_source_grounded_but_not_fabricated(monkeypatch, local, canonical):
    monkeypatch.setattr(news_fact_guard,'original_draft_reason',lambda *a:None)
    draft = {'body':f'{canonical} issued a report.'}
    assert news_fact_guard.fact_lock_reason(draft,'Report',f'{local} је објавила извештај.') is None
    assert news_fact_guard.fact_lock_reason(draft,'Report','Објављен је извештај.') == 'unsupported_acronym:'+canonical
    assert news_fact_guard.fact_lock_reason(draft,'Report','ПСЕВДО'+local) == 'unsupported_acronym:'+canonical


def test_primary_queue_filters_clearly_nonnews_formats():
    for title, reason in [
        ('Neeru Dhanda: From tin cans and a borrowed gun to World Cup history and Asian Games gold','unsupported_news_sport'),
        ("2026/27 UEFA European Women's Under-17 Championship round 1 guide",'non_article_service_guide'),
        ('The Nations League is a welcome example of soccer done well','non_article_analysis'),
        ('La conspiración de que Vinicius no es Vinicius y fue reemplazado tras el Mundial','non_news_conspiracy')]:
        assert non_article_news_reason({'title':title}) == reason
    assert non_article_news_reason({'title':'Training gallery: Back to work!'}) == 'non_article_photo_gallery'
    assert non_article_news_reason({'title':'Equipe de France: comment prononce-t-on vraiment le nom de Lucas Da Cunha?'}) == 'non_article_service_guide'


@pytest.mark.parametrize('audited',[True,False])
def test_only_exact_prefixed_cies_false_hold_can_be_retried(monkeypatch,audited):
    holds = news_source_holds
    url = holds._ZVEZDA_CIES_REPAIR_URL if audited else 'https://other.test/cies-report'
    statements = []
    class Cursor:
        rowcount = 1
        def execute(self,query,params=None):statements.append((query,params))
        def fetchall(self):return [(holds._fingerprint(url),'validator-unsupported-claim')]
        def close(self):pass
    class Connection:
        def cursor(self):return Cursor()
        def commit(self):pass
        def close(self):pass
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:'fixture')
    monkeypatch.setattr(holds,'_connect',lambda _:Connection())
    monkeypatch.setattr(holds,'_ensure_schema',lambda _:None)
    assert holds.held_source_urls([url]) == {url}  # Other semantic reasons stay held.
    writes = [(q,p) for q,p in statements if q.startswith('UPDATE')]
    assert len(writes)==2*int(audited)
    if audited:
        q,p=writes[0]
        assert "reason='unsupported_acronym:CIES'" in q and 'updated_at < %s::timestamptz' in q
        assert p==(holds._fingerprint(url),'2026-09-29T07:35:00Z')
        q,p=writes[1]
        assert "reason='validator-changed-name'" in q and 'updated_at < %s::timestamptz' in q
        assert p==(holds._fingerprint(url),'2026-09-29T07:53:00Z')
