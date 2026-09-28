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


@pytest.mark.parametrize('body', [
    'No specific teams or scenarios were detailed in the reported context about the MLB playoffs.',
    'The statement about heightened pressure does not specify which teams or factors contribute.',
    'No additional details about scheduling or competitive balance were provided in the verified facts.',
])
def test_generic_teaser_padding_never_passes_original_draft_or_public_admission(body):
    assert non_article_news_reason({'title': 'MLB playoffs bring pressure', 'body': body}) == 'non_news_source_meta_filler'


def test_actual_team_declining_to_give_injury_details_remains_news():
    assert non_article_news_reason({'title': 'Club confirms injury absence',
        'body': 'The club did not specify a return date for its injured captain.'}) is None


def test_confirmed_cuesta_gilardino_role_swap_cannot_remain_public():
    item = {'title': 'Alberto Gilardino agrees to return as Parma football coach',
        'url': 'https://football-italia.net/parma-agreement-gilardino-italy-return-coach/',
        'body': 'Gilardino previously served as an assistant coach at Arsenal.'}
    assert non_article_news_reason(item) == 'known_entity_role_misattribution'
    item['body'] = 'Carlos Cuesta, the former Arsenal assistant, departed Parma. Gilardino agreed to join the club.'
    assert non_article_news_reason(item) is None


@pytest.mark.parametrize('title,reason', [
    ('MLB playoffs: Ranking teams by World Series pressure', 'non_article_analysis'),
    ("51 reasons to fear the Kings' bench", 'non_article_analysis'),
    ('Compilation: 11 brilliant acrobatic goals scored for Liverpool', 'non_article_video_highlights'),
])
def test_subjective_lists_and_compilations_stop_before_writer(title, reason):
    assert non_article_news_reason({'title': title}) == reason


@pytest.mark.parametrize('title', [
    'The Big Red Sale continues: Get 20% off everything now',
    'Club shirts: shop now', 'Final tickets now on sale',
])
def test_official_shop_and_ticket_promotions_never_spend_writer_budget(title):
    assert non_article_news_reason({'title': title}) == 'non_article_commercial_promotion'


def test_transfer_sale_and_playoff_qualification_remain_sporting_news():
    assert non_article_news_reason({'title': 'Lazio confirm permanent sale of Patric'}) is None
    assert non_article_news_reason({'title': 'Cubs clinch playoff berth with victory'}) is None
    assert non_article_news_reason({'title': 'The playoff field is set! See the final bracket'}) == 'non_article_service_guide'


def test_rugby_world_cup_cannot_become_soccer_through_wales_or_world_cup_names():
    from public_index import _explicit_title_sport_override
    headline='Tayla Preston selected in Wales squad for 2026 Rugby League World Cup'
    assert classify_article(headline, 'Wales named its squad.').sport == 'rugby-league'
    assert _explicit_title_sport_override(headline) == 'rugby-league'
    assert classify_article('Preston named in Wales squad for World Cup',
        'Tayla Preston has been selected for the Wales rugby league squad.').sport == 'rugby-league'
    assert classify_article('Wales rugby union squad named for World Cup', '').sport == 'rugby'


def test_incidental_rugby_background_does_not_override_explicit_soccer_headline():
    assert classify_article('Wales football squad announced',
        'The coach watched a rugby league match during his break.').sport == 'football'


def test_mixed_source_liveblog_and_medal_tables_never_reach_writer():
    assert non_article_news_reason({'title':'Asian Games latest',
        'url':'https://timesofindia.indiatimes.com/sports/liveblog/123.cms'}) == 'non_article_live_program'
    assert non_article_news_reason({'title':'Asian Games India medal winners: Full list of athletes'}) == 'non_article_service_guide'


def test_boxers_plural_is_sport_evidence_but_boxing_day_is_not():
    assert classify_article('Priya, Lovlina storm into semis as India’s boxers continue to assure medals',
        'India’s boxing campaign continued at the Asian Games.').sport == 'boxing'
    assert classify_article('Arsenal beat Chelsea on Boxing Day in Premier League', '').sport == 'football'


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


def test_wrong_public_sport_against_trusted_source_is_held_durably():
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from public_index import repair_recent_gossip_news
    from taxonomy_resolver import RESOLVER_VERSION
    db = SessionLocal()
    try:
        article = Article(title='Cornish Pirates concede club-record 73 points at Coventry',
            summary='The Pirates suffered a Championship defeat.', slug='recovery-coventry-source-sport',
            source_url='https://www.bbc.co.uk/sport/rugby-union/articles/cmzxzj8n9wwwo',
            published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(article); db.flush()
        tax = ArticleTaxonomyResolution(article_id=article.id, resolver_version=RESOLVER_VERSION,
            resolved_sport='football', public_ok=True)
        db.add(tax); db.commit()
        assert repair_recent_gossip_news(db) >= 1
        db.refresh(tax)
        assert tax.public_ok is False
        assert db.query(NewsIncident).filter_by(article_id=article.id, status='open',
            reason_code='taxonomy_source_path_conflict').count() == 1
        assert repair_recent_gossip_news(db) == 0
    finally:
        db.close()


def test_source_section_guard_preserves_explicit_sport_corrections():
    from bot.news_policy import source_path_conflict_reason
    assert source_path_conflict_reason({'title': 'UFC star wins MMA bout',
        'url': 'https://www.bbc.co.uk/sport/football/articles/misplaced'}, 'mma') is None
    assert source_path_conflict_reason({'title': 'Cornish Pirates defeated at Coventry',
        'url': 'https://www.bbc.co.uk/sport/rugby-union/articles/report'}, 'football') == 'taxonomy_source_path_conflict'
    assert source_path_conflict_reason({'title': 'Coventry win',
        'url': 'https://other.example/rugby-union/report'}, 'football') is None


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


def test_confirmed_legacy_editorial_incidents_are_held_without_blocking_real_final_report():
    assert non_article_news_reason({'title':'Linda Nosková’s Ambitious Path Toward Tennis Supremacy'}) == 'non_news_retrospective_commentary'
    assert non_article_news_reason({'title':'Premier League possession football faces questions as tactics evolve'}) == 'non_article_analysis'
    assert non_article_news_reason({'title':'Grand Final Week Opens with a Harbour Bridge March'}) == 'non_article_event_promotion'
    assert non_article_news_reason({'title':'Knights fans fill Sydney Harbour Bridge ahead of Grand Final'}) is None


def test_membership_panel_inside_main_cannot_supply_article_images_or_prose():
    h='<main><div id="authProfile"><img src="https://cdn.example/membership.jpg"><p>Membership product promotion.</p></div><img src="https://cdn.example/player.jpg"><p>The basketball club announced its new signing.</p></main>'
    assert [r['url'] for r in collect_page_image_candidates(h)] == ['https://cdn.example/player.jpg']
    assert 'Membership' not in article_text_from_html(h)


def test_yonhap_recommendation_articles_cannot_supply_hero_or_body():
    import json
    story='The volleyball team canceled practice after its bus arrived at the wrong venue. '
    h='<meta property="og:url" content="https://en.yna.co.kr/view/AEN20260928010600320"><meta property="og:image" content="https://img.example/volleyball.jpg">'
    h+='<main><article><img src="https://img.example/unrelated.jpg"><p>Unrelated recommendation.</p></article><article class="story-news"><img src="//img.example/volleyball.jpg"><p>'+story*8+'</p></article></main>'
    assert all('unrelated' not in r['url'] for r in collect_page_image_candidates(h))
    assert 'Unrelated' not in article_text_from_html(h)
    assert 'volleyball' in article_text_from_html(h)


def test_swimmer_headline_outweighs_incidental_basketball_comparison():
    assert classify_article('Swimmers lament decision not to award medals to relay heat participants',
        'The swimming team questioned the relay medal policy. NBA basketball player Michael Jordan had a similar complaint.').sport == 'swimming'
    assert classify_article('NBA basketball players take swimming lessons','Basketball players practiced in a pool.').sport == 'basketball'


def test_historical_tennis_feature_is_not_today_news_but_new_death_is():
    assert non_article_news_reason({'title':'How a 1986 Fed Cup final helped shape Czechia’s tennis legacy'}) == 'non_news_retrospective_commentary'
    assert non_article_news_reason({'title':'1966 World Cup winner dies aged 90'}) is None


def test_dedicated_indonesian_federation_feed_resolves_sport_without_guessing_league():
    from bot.fetch_sources import _classify_candidate
    c=_classify_candidate({'title':'Asian Games 2026: Alwi Melesat ke Semifinal, Jonatan Kandas',
        'summary':'MS-QF: Alwi Farhan vs Chou Tien Chen.',
        'feed':{'kind':'league','sport':'badminton','verified_official':True},'url':'https://pbsi.id/news/example/'})
    assert c.sport == 'badminton' and c.league == 'badminton-international'


def test_ufc_drupal_column_layout_is_not_discarded_as_a_sidebar():
    h='<meta property="og:url" content="https://www.ufc.com/news/week-8-preview"><main><div class="l-two-col--right-sidebar"><div class="field--name-body-structured"><p>The fighters will compete in the next round of the series.</p></div><aside><p>Unrelated fight promotion.</p></aside></div></main>'
    body=article_text_from_html(h)
    assert 'fighters will compete' in body and 'Unrelated' not in body


def test_modal_may_is_not_a_month_but_real_may_dates_stay_locked():
    from bot.news_fact_guard import _calendar_terms
    assert 'may' not in _calendar_terms('The player may improve and may seek another route.')
    for value in ['in May','May 12','late may','12 May','next may']:
        assert 'may' in _calendar_terms(value)


def test_non_catalog_sport_cannot_become_football_from_world_cup_background():
    from bot.fetch_sources import _classify_candidate
    title='Bhaker returns empty-handed as India’s shooting campaign falls short of Hangzhou'
    body='The 10m air pistol finalist had previously won World Cup medals.'
    assert classify_article(title, body).sport is None
    assert non_article_news_reason({'title':title,'body':body}) == 'unsupported_news_sport'
    assert _classify_candidate({'title':title,'summary':body,'url':'https://www.bbc.co.uk/sport/football/example','feed':{}}).sport is None
    # Published copy also stays held after the writer removes the sport label
    # from its headline. The factual lead still identifies the discipline.
    assert non_article_news_reason({'title':'Manu Bhaker finishes Asian Games 2026 without medal after four events','body':body}) == 'unsupported_news_sport'


def test_shooting_terminology_in_supported_sports_is_not_rejected():
    for title,body,sport in [
        ('NBA shooting guard signs new contract','The basketball player joined the team.','basketball'),
        ('Arsenal improve shooting ahead of World Cup break','The football club trained on Monday.','football'),
    ]:
        assert non_article_news_reason({'title':title,'body':body}) is None
        assert classify_article(title,body).sport == sport


def test_distinctive_asian_games_events_resolve_without_cross_sport_leakage():
    assert classify_article('Top-ranked shuttler An Se-young cruises into women’s singles final','The player reached the Asian Games final.').sport == 'badminton'
    assert classify_article('S. Korea advances to men’s 4x100m relay final after disqualification overturned','The quartet reached the Asian Games final.').sport == 'athletics'
    assert classify_article('China wins 4x100m relay final','The swimming team won the freestyle relay in the pool.').sport == 'swimming'


def test_entertainment_appearance_is_not_a_basketball_development():
    assert non_article_news_reason({'title':"Jalen Brunson Hosts 'SNL' with Knicks Teammates in Attendance"}) == 'non_sports_entertainment'


def test_snooker_federation_feed_does_not_stamp_billiards_or_promotional_products():
    from bot.feeds import FEEDS
    feed=next(f for f in FEEDS if f['url']=='https://www.wpbsa.com/feed/')
    assert feed['sport']=='snooker' and feed['verified_official'] and not feed.get('league')
    assert classify_article('Gilchrist Secures Canadian Double', 'The World Billiards tour continued in Canada.', feed_kind='league',feed_sport='snooker').sport is None
    assert classify_article('Day Wins Maiden Seniors Title', 'Ryan Day defeated Andy Lavin to win his first World Seniors Snooker title.', feed_kind='league',feed_sport='snooker').sport == 'snooker'
    assert non_article_news_reason({'title':'Stars Arrive In Shenzhen'}) == 'non_article_event_promotion'


@pytest.mark.parametrize('title', ['WSL talking points: Chelsea punish Arsenal', 'Silver linings for MLB’s non-playoff teams', 'NBA preview: The most intriguing newcomers', '(Asiad) medal standings', 'Trainer of the Year standings – up to and including Sunday'])
def test_rankings_tables_and_opinion_products_do_not_spend_writer_budget(title):
    assert non_article_news_reason({'title':title})


def test_editorial_inventory_excludes_yesterday_inside_rolling_24h_and_future():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Article, ArticleTaxonomyResolution
    from public_index import recent_public_sport_inventory
    from taxonomy_resolver import RESOLVER_VERSION
    engine=create_engine('sqlite:///:memory:')
    Article.__table__.create(engine)
    ArticleTaxonomyResolution.__table__.create(engine)
    with Session(engine) as db:
        for i,stamp in enumerate([datetime(2026,9,27,13,59),datetime(2026,9,27,14),datetime(2026,9,28,6),datetime(2026,9,28,12)]):
            a=Article(title='News',slug=f'inventory-{i}',external_id=f'inventory-{i}',sport='football',image_url='https://example.test/photo.jpg',published_at=stamp)
            db.add(a);db.flush()
            db.add(ArticleTaxonomyResolution(article_id=a.id,resolved_sport='football',resolver_version=RESOLVER_VERSION,public_ok=True,hero_media_kind='EDITORIAL_PHOTO'))
        db.commit()
        now=datetime(2026,9,28,11,tzinfo=timezone.utc)
        assert recent_public_sport_inventory(db,max_age_hours=24,now=now)=={'football':3}
        assert recent_public_sport_inventory(db,editorial_timezone='Australia/Sydney',now=now)=={'football':2}
    engine.dispose()


def test_handball_federation_evidence_beats_shared_champions_league_name():
    assert classify_article('Nielsen targets another title with Veszprém','The handball goalkeeper won the Champions League and now targets the Club World Cup.').sport == 'handball'
    assert classify_article('Nielsen targets another title with Veszprém','The EHF Champions League winner returns to the Club World Cup.').sport == 'handball'
    assert classify_article('Liverpool prepare for Champions League','The football team visited a handball club during training.').sport == 'football'


def test_ncaa_is_not_basketball_and_primary_lead_beats_biographical_polo():
    body='Former USA Swimming National Team Director and university swimming coach Frank Busch has died.\n\nEarlier in his life he played water polo and entered an athletics hall of fame.'
    assert classify_article('Frank Busch, NCAA Title Winning Coach, Dies',body,feed_kind='league',feed_sport='swimming').sport == 'swimming'
    assert classify_article('NCAA basketball coach named','The basketball program appointed a coach.').sport == 'basketball'
    assert classify_article('The outcome remains unknown','No sporting evidence available.').sport is None


def test_shared_competition_in_water_polo_cannot_stamp_soccer_but_real_soccer_still_wins():
    assert classify_article('Novi Beograd keeps perfect record beating Budva','The Champions League qualifiers returned to domestic competition.',feed_kind='league',feed_sport='water-polo').sport == 'water-polo'
    assert classify_article('Liverpool football squad confirmed','The soccer club prepared for the Champions League.',feed_kind='league',feed_sport='water-polo').sport == 'football'


def test_swimswam_wordpress_category_news_class_is_article_not_recommendations():
    h='<meta property="og:url" content="https://swimswam.com/report/"><aside><p>Unrelated story.</p></aside><article class="post type-post category-news"><p>The university swimming team won its season opener against a visiting conference opponent on Saturday.</p></article><p>Other unrelated news.</p>'
    text=article_text_from_html(h)
    assert 'university swimming team won' in text and 'Unrelated' not in text and 'Other' not in text


def test_lazy_article_photo_and_jsonld_reference_resolve_to_real_urls_only():
    h='<script type="application/ld+json">'+json.dumps({'@graph':[
        {'@type':'Article','image':{'@id':'https://publisher.test/story/#primaryimage'}},
        {'@type':'ImageObject','@id':'https://publisher.test/story/#primaryimage','contentUrl':'https://publisher.test/athlete.jpg','width':1200,'height':800},
        {'@type':'Article','image':{'@id':'https://publisher.test/unresolved/#image'}},
    ]})+'</script><article><img src="data:image/svg+xml;base64,placeholder" data-src="https://publisher.test/athlete-alt.jpg" width="853" height="480"></article>'
    candidates=collect_page_image_candidates(h)
    assert {r['url'] for r in candidates} == {'https://publisher.test/athlete.jpg','https://publisher.test/athlete-alt.jpg'}
    assert candidates[0]['width']==1200 and candidates[1]['in_article']


def test_rewritten_club_fan_ranking_is_still_a_poll():
    for title in ["What is Liverpool's best Premier League win over Manchester City? - Liverpool FC",'Liverpool invite fans to rank top Premier League clashes with Manchester City']:
        assert non_article_news_reason({'title':title}) == 'non_article_fan_poll'
