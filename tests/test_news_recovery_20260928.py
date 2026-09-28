from datetime import datetime, timezone
import json

import pytest

from bot.classify import _score_aliases, classify_article
from bot.extract import article_text_from_html, collect_page_image_candidates, page_published_at_from_html
from bot import news_official_indexes as idx
from bot.news_policy import non_article_news_reason, original_draft_reason, publisher_branding_reason


@pytest.mark.parametrize('title', [
    'Chelsea’s Ultimate Goal of the Season Group C results confirm two goals advanced to quarter-final voting',
    'NBL27 Champion Fans MVP Voting Opens Weekly with $4000 Prize',
    'Vote for your Player of the Month',
])
def test_official_fan_products_cannot_be_rewritten_as_sports_news(title):
    assert non_article_news_reason({'title':title}) == 'non_article_fan_poll'


def test_actual_sporting_award_is_not_a_fan_engagement_product():
    assert non_article_news_reason({'title':'Guard wins league MVP award after record season'}) is None


def test_unconfirmed_citizenship_prediction_is_held_but_actual_change_is_allowed():
    from bot.news_policy import gossip_news_reason
    assert gossip_news_reason({'title':'Tennis World in Turmoil as Top Russian Player Considers Citizenship Change',
        'summary':'A top Russian tennis player may soon renounce her citizenship.'}) == 'gossip_unconfirmed_rumour'
    assert gossip_news_reason({'title':'Tennis player confirms citizenship change'}) is None


def test_absent_source_details_are_not_news_content():
    assert non_article_news_reason({'title':'Basketball update','body':
        'No specific player names or additional details about the nomination criteria were provided in the source material.'}) == 'non_news_source_meta_filler'


@pytest.mark.parametrize("word", ["command", "summary", "summarize", "commander", "grammar", "summation"])
def test_short_mma_alias_is_never_a_substring(word):
    assert _score_aliases(word, ["mma"]) == 0


def test_alias_boundaries_allow_punctuation_and_multispace_phrases():
    assert _score_aliases("(MMA): UFC", ["mma", "ufc"]) == 2
    assert _score_aliases("mixed  martial\narts", ["mixed martial arts"]) == 3
    assert classify_article("Cricket match summary", "Cricket teams prepare.").sport == "cricket"
    assert classify_article("Cycling command performance", "Road cycling in the peloton.").sport == "cycling"


def test_minified_jsonld_preserves_real_publication_and_article_body():
    body = " ".join(["Poland defended the European volleyball championship with a controlled display."] * 12)
    doc = "<script type=application/ld+json>" + json.dumps({
        "@type": "NewsArticle", "datePublished": "2026-09-27T01:37:00Z", "articleBody": body,
    }) + "</script>"
    assert page_published_at_from_html(doc) == datetime(2026, 9, 27, 1, 37, tzinfo=timezone.utc)
    assert "Poland defended" in article_text_from_html(doc)


@pytest.mark.parametrize("mime", ["application/ld&#x2B;json", "application/ld&#43;json", "APPLICATION/LD+JSON"])
def test_encoded_jsonld_mime_preserves_publication_body_and_image(mime):
    body = "The club confirmed its new captain after consulting the playing group. " * 15
    doc = f'<script type="{mime}">' + json.dumps({
        "@type": "NewsArticle", "datePublished": "2026-09-27T17:13:00Z",
        "articleBody": body, "image": "https://example.test/captain.jpg",
    }) + '</script>'
    assert page_published_at_from_html(doc) == datetime(2026, 9, 27, 17, 13, tzinfo=timezone.utc)
    assert "club confirmed its new captain" in article_text_from_html(doc)
    assert any(row["url"] == "https://example.test/captain.jpg" for row in collect_page_image_candidates(doc))


def test_non_jsonld_script_is_never_treated_as_publication_metadata():
    doc = '<script type="application/json">{"datePublished":"2026-09-28T01:00:00Z"}</script>'
    assert page_published_at_from_html(doc) is None


def test_void_tags_in_navigation_cannot_hide_article_or_image():
    doc = '''<nav><input><img src=/logo.png><img src=/other.png/><p>Navigation text.</p></nav>
      <main><p>Barcelona prepared for the handball final with their complete first team.
      <p>Zamalek confirmed the squad would travel to the competition on Monday.
      <img src=/photo.jpg width=1200 height=800></main>'''
    body = article_text_from_html(doc)
    assert "Barcelona prepared" in body and "Zamalek confirmed" in body
    assert "Navigation" not in body
    assert any(x["url"] == "/photo.jpg" and x["in_article"] for x in collect_page_image_candidates(doc))


def test_missing_time_is_not_invented_and_script_dates_are_not_visible():
    assert idx._visible_published_date("<div>27 Sep. 2026</div>") is None
    assert idx._visible_published_date("<script>2026-09-28 09:25</script>", "Asia/Shanghai") is None
    assert idx._visible_published_date("<div>2026-09-28 09:25</div>", "Asia/Shanghai") == datetime(2026, 9, 28, 1, 25, tzinfo=timezone.utc)


def test_official_navigation_never_consumes_article_limit(monkeypatch):
    cfg = next(c for c in idx.HTML_INDEXES if c["id"] == "nba-basketball-news")
    html = '<a href=/news>News</a><a href=/news/key-dates>Key dates</a>'
    html += ''.join(f'<a href=/news/category/group-{n}>Group {n}</a>' for n in range(15))
    html += '<a href=/news/team-announces-coach>Team announces coach</a>'
    monkeypatch.setattr(idx, "read_news_feed", lambda u: html.encode())
    assert idx._anchor_candidates(cfg) == [("https://www.nba.com/news/team-announces-coach", "Team announces coach")]


def test_netball_discovers_only_news_cards_and_does_not_reenter_navigation(monkeypatch):
    cfg = next(c for c in idx.HTML_INDEXES if c["id"] == "world-netball-news")
    html = ''.join(f'<a href="https://netball.sport/game/netball-{n}/">Netball guide</a>' for n in range(15))
    html += '<a href="https://netball.sport/netball-announces-officials/" class="card stretched-link"></a>'
    html += '<script>{"url":"https://netball.sport/world-netball-foundation/"}</script>'
    monkeypatch.setattr(idx, "read_news_feed", lambda u: html.encode())
    assert idx._anchor_candidates(cfg) == [("https://netball.sport/netball-announces-officials/", "")]


@pytest.mark.parametrize("title,reason", [
    ("NinkoSports Daily Football Quizzes Test Knowledge and Instinct", "non_article_quiz"),
    ("Los Angeles Angels vs Seattle Mariners: Game Highlights", "non_article_video_highlights"),
    ("Samoa-eligible players tries of the week", "non_article_video_highlights"),
    ("NRL Finals Week 3 Moments", "non_article_video_highlights"),
    ("Bahrain Grand Prix race times and weather forecast", "non_article_service_guide"),
])
def test_non_news_is_rejected_before_writer(title, reason):
    assert non_article_news_reason({"title": title}) == reason


def test_provider_copy_is_held_not_rebranded():
    draft = {"title": "Fresh football challenges", "summary": "BBC Sport has published daily challenges.", "body": "Football supporters can try the questions."}
    assert publisher_branding_reason(draft) == "publisher_branding"
    assert original_draft_reason(draft, "Source", "Facts") == "publisher_branding"


def test_rewritten_retrospective_is_held_before_semantic_request():
    draft = {"title": "Roosters Legends Reflect on 2002-2004 Era",
             "summary": "Former players remember their previous seasons.",
             "body": "The players described their memories of the old side."}
    assert original_draft_reason(draft, "A new interview", "Source facts") == "non_news_retrospective_commentary"


def test_real_news_is_not_rejected_as_a_media_product():
    assert non_article_news_reason({"title": "Club confirms new head coach after review", "url": "https://example.test/news/coach"}) is None


def test_rewritten_highlight_title_cannot_hide_its_source_product():
    assert non_article_news_reason({"title": "Standout performances", "url": "https://www.nrl.com/news/2026/09/28/best-moments-finals-week-3/"}) == "non_article_video_highlights"


def test_current_day_hydration_reports_missing_body(monkeypatch):
    cfg = {"id": "fixture", "url": "https://example.test/news", "sport": "football", "publisher": "Club"}
    stamp = datetime.now(timezone.utc).isoformat()
    html = f'<meta property=article:published_time content="{stamp}"><meta property=og:title content="Club appoints coach">'
    monkeypatch.setattr(idx, "read_news_feed", lambda u: html.encode())
    from collections import Counter
    counts = Counter()
    assert idx._hydrate(cfg, "https://example.test/news/coach", "", diagnostics=counts) is None
    assert counts == {"missing_article_body": 1}


def test_world_athletics_time_must_belong_to_the_current_article(monkeypatch):
    cfg = next(c for c in idx.HTML_INDEXES if c["id"] == "world-athletics-news")
    timestamp = datetime.now(timezone.utc).isoformat()
    state = {"props": {"pageProps": {"article": {"urlSlug": "asian-games-report", "liveFrom": timestamp}}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(state) + '</script>'
    html += '<meta property=og:title content="Athletics Asian Games report"><meta property=og:image content="https://worldathletics.org/photo.jpg">'
    html += '<main><p>The athletics championship continued with a complete programme of competition and confirmed entrants.</p></main>'
    monkeypatch.setattr(idx, "read_news_feed", lambda u: html.encode())
    item = idx._hydrate(cfg, 'https://worldathletics.org/news/report/asian-games-report', '')
    assert item and item['published_at'].isoformat() == timestamp
    assert idx._hydrate(cfg, 'https://worldathletics.org/news/report/another-story', '') is None


@pytest.mark.parametrize('headline,reason,slug', [
    ('NinkoSports Daily Football Quizzes Test Knowledge and Instinct', 'non_article_quiz', 'quiz'),
    ('NHL fantasy hockey previews roll out for all 32 teams', 'non_article_fantasy_product', 'fantasy'),
    ('Grand Final week in pictures', 'non_article_photo_gallery', 'gallery'),
    ('EuroLeague Injury Report Offers Daily Updates for Fans and Fantasy Players', 'non_article_rolling_tracker', 'injury-tracker'),
    ('Chelsea Ultimate Goal of the Season Group C results', 'non_article_fan_poll', 'goal-voting'),
    ('NBL27 Champion Fans MVP Voting Opens Weekly with $4000 Prize', 'non_article_fan_poll', 'mvp-voting'),
    ('Top Russian Player Considers Citizenship Change', 'gossip_unconfirmed_rumour', 'citizenship'),
])
def test_public_quiz_cleanup_is_durable_and_does_not_delete_article(headline, reason, slug):
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from public_index import repair_recent_gossip_news
    from taxonomy_resolver import RESOLVER_VERSION
    db = SessionLocal()
    try:
        a = Article(title=headline,
            summary="A media product announcement.", slug=f"recovery-{slug}-test",
            source_url=f"https://example.test/{slug}", published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(a); db.flush()
        tax = ArticleTaxonomyResolution(article_id=a.id, resolver_version=RESOLVER_VERSION, public_ok=True)
        db.add(tax); db.commit()
        assert repair_recent_gossip_news(db) >= 1
        db.refresh(tax)
        assert tax.public_ok is False
        assert db.get(Article, a.id) is not None
        assert db.query(NewsIncident).filter_by(article_id=a.id, status="open", reason_code=reason).count() == 1
        assert repair_recent_gossip_news(db) == 0
    finally:
        db.close()


def test_confirmed_gallery_stays_held_after_ai_headline_changes():
    assert non_article_news_reason({
        'title': 'Fans gathered in Sydney to celebrate Grand Final Week',
        'url': 'https://www.nrl.com/news/2026/09/28/fans-march-across-harbour-bridge-to-launch-grand-final-week/'
    }) == 'non_article_photo_gallery'


def test_nrl_gallery_cms_fails_before_facts_or_writer(monkeypatch):
    from collections import Counter
    from bot import news_official_indexes as idx
    cfg = next(c for c in idx.HTML_INDEXES if c['id'] == 'nrl-rugby-league-news')
    monkeypatch.setattr(idx, 'read_news_feed', lambda u: b'<div id="vue-gallery-list"><p>Photo caption</p></div>')
    reasons = Counter()
    assert idx._hydrate(cfg, 'https://www.nrl.com/news/2026/09/28/another-gallery/', 'Fans celebrate', diagnostics=reasons) is None
    assert reasons == {'non_article_photo_gallery': 1}


def test_site_acknowledgement_is_excluded_without_removing_real_sports_prose():
    from bot.extract import article_text_from_html
    prose = 'The league announced a new programme for Indigenous players and coaches across the country.'
    html = ('<main><p>' + prose + '</p></main>'
            '<div class="acknowledgement-of-country"><p>National Rugby League respects and honours '
            'the Traditional Custodians of the land and their Elders past, present and future.</p></div>')
    body = article_text_from_html(html)
    assert prose.rstrip('.') in body
    assert 'Traditional Custodians' not in body


def test_rolling_tracker_and_publisher_promotion_do_not_replace_real_injury_news():
    assert non_article_news_reason({'title': 'EuroLeague Injury Report (updated daily)'}) == 'non_article_rolling_tracker'
    assert non_article_news_reason({'title': 'Lakers confirm Davis will miss opener with ankle injury'}) is None
    assert publisher_branding_reason({'body': 'BasketNews tracks every injury for fantasy players.'}) == 'publisher_branding'
    assert publisher_branding_reason({'body': 'The National Basketball League confirmed a new coaching appointment.'}) is None


def test_confirmed_non_authoritative_sanction_prediction_remains_held():
    assert non_article_news_reason({
        'title': 'Manchester City disciplinary outcome discussed',
        'url': 'https://www.record.pt/internacional/paises/inglaterra/detalhe/liam-gallagher-revela-possivel-castigo-do-man-city-e-explode-calem-se-idiotas-neuroticos-desesperados'
    }) == 'non_news_fan_speculation'
    assert non_article_news_reason({'title': 'Premier League confirms disciplinary sanction', 'url': 'https://www.premierleague.com/en/news/sanction'}) is None
