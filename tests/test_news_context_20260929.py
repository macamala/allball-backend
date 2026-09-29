import pytest

from bot.classify import classify_article
from bot import news_fact_guard as guard
from bot.news_policy import non_article_news_reason


@pytest.mark.parametrize("sport,title,body", [
    ("darts", "Littler stunned by Waterhouse at World Grand Prix", "Waterhouse advanced after defeating Littler."),
    ("water-polo", "Novi Beograd keeps perfect record beating Budva", "The Champions League qualifiers returned to domestic competition."),
    ("rugby", "Newcastle agree delay to Fineanganofo arrival", "Fineanganofo will join Newcastle later than planned."),
])
def test_verified_source_context_disambiguates_shared_names_without_rewriting_facts(monkeypatch, sport, title, body):
    # Isolate taxonomy: other original-writing gates have their own tests.
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    draft = {"title": title, "summary": "", "body": body}
    assert guard.fact_lock_reason(draft, title, body, expected_sport=sport) is None


@pytest.mark.parametrize("expected,title,body,actual", [
    ("water-polo", "Liverpool football squad confirmed", "The soccer team returned to training.", "football"),
    ("darts", "Formula 1 driver wins Grand Prix", "The Formula 1 race ended.", "motorsport"),
    ("football", "UFC champion prepares for MMA title fight", "The MMA champion trained.", "mma"),
    ("rugby", "Newcastle United confirm Premier League transfer", "Newcastle United signed a football player.", "football"),
])
def test_verified_context_never_overrides_real_contradictory_sport(monkeypatch, expected, title, body, actual):
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    assert guard.fact_lock_reason({"title": title, "body": body}, title, body, expected_sport=expected) == "draft_sport_mismatch:" + actual


def test_home_debut_qualifier_is_mandatory(monkeypatch):
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    source = "The coach lost on his debut in the home dugout after an away draw."
    assert guard.fact_lock_reason({"title": "Coach loses on debut"}, "Visitors win", source) == "lost_debut_qualifier"
    assert guard.fact_lock_reason({"title": "Coach loses on home debut"}, "Visitors win", source) is None
    assert guard.fact_lock_reason({"title": "Visitors beat hosts"}, "Visitors win", source) is None


def test_confirmed_public_errors_remain_held_during_repairs():
    assert non_article_news_reason({"title": "Greece defeat Germany in Klopp debut as Gakpo suffers ankle injury"}) == "lost_debut_qualifier"
    assert non_article_news_reason({"title": "Germany's unexpected defeat to Greece in Nations League matches sparks surprise"}) == "confirmed_duplicate_with_unsupported_reaction"


def test_unreliable_image_host_does_not_crowd_out_ready_official_source():
    from bot.news_policy import candidate_readiness_score
    base = {'title': 'Basketball team confirms signing', '_extracted': 'Verified report', '_extracted_image': 'https://example.test/player.jpg'}
    reliable = {**base, 'feed': {'kind': 'league', 'sport': 'basketball', 'verified_official': True}}
    unstable = {**base, 'feed': {'kind': 'league', 'sport': 'basketball', 'readiness_penalty': 15}}
    assert candidate_readiness_score(reliable) > candidate_readiness_score(unstable) + 10
    from bot.feeds import FEEDS
    source = next(f for f in FEEDS if f['url'] == 'https://football-italia.net/feed/')
    assert source['sport'] == 'football' and not source.get('league')


def test_nations_league_repair_clears_domestic_stamp_without_restoring_held_rows():
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from taxonomy_resolver import RESOLVER_VERSION
    from public_index import repair_recent_gossip_news
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):
        model.__table__.create(engine)
    with Session(engine) as db:
        rows = []
        for i, (title, public) in enumerate([
            ('Italy make eight changes for Nations League clash against Turkiye', True),
            ('Napoli name squad for Serie A match', True),
            ('Italy announce Nations League squad', False),
        ]):
            a = Article(title=title, slug=f'league-repair-{i}', external_id=f'league-repair-{i}',
                sport='football', league='italy-serie-a', country='italy',
                published_at=datetime.utcnow(), source_url=f'https://example.test/report-{i}')
            db.add(a); db.flush()
            tax = ArticleTaxonomyResolution(article_id=a.id, resolved_sport='football',
                resolved_competition='italy-serie-a', resolver_version=RESOLVER_VERSION, public_ok=public)
            db.add(tax); rows.append((a, tax))
        db.commit()
        assert repair_recent_gossip_news(db) == 1
        assert rows[0][0].league is None and rows[0][1].resolved_competition is None
        assert rows[0][1].public_ok and rows[1][1].resolved_competition == 'italy-serie-a'
        assert not rows[2][1].public_ok
        assert db.query(NewsIncident).filter_by(reason_code='taxonomy_competition_mismatch', status='auto_corrected').count() == 1
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


def test_lnf_scopes_prose_and_keeps_exact_rss_calendar_day():
    from datetime import datetime, timezone
    from bot.extract import article_text_from_html
    from bot.feeds import FEEDS
    from bot.news_policy import editorial_day_reason, source_path_sport_hint
    from bot.classify import classify_article
    prose = ('Campo Mourão conquistou a Copa Sul de futsal após vencer a final. '
             'A equipe levantou o troféu diante de seus torcedores. '
             'O técnico destacou o trabalho dos jogadores durante a competição.')
    page = ('<meta property="og:url" content="https://lnfoficial.com.br/noticias/campo-mourao/">'
            '<div class="report-news-container"><div class="post-content"><p>' + prose +
            '</p></div><aside><p>Unrelated recommendation</p></aside></div>')
    assert article_text_from_html(page).rstrip('.') == prose.rstrip('.')
    assert source_path_sport_hint('https://lnfoficial.com.br/noticias/corinthians/') == 'futsal'
    feed = next(f for f in FEEDS if f['url'] == 'https://lnfoficial.com.br/noticias/feed/')
    assert feed['verified_official'] and feed['sport'] == 'futsal' and not feed.get('league')
    classified = classify_article('Corinthians e Pato se enfrentam', prose, feed_kind='league', feed_sport='futsal')
    assert classified.sport == 'futsal'
    now = datetime(2026, 9, 29, 0, 40, tzinfo=timezone.utc)
    # The real 13:57 UTC LNF match report is yesterday in Sydney. Do not
    # turn a freshly discovered page into a freshly published story.
    assert editorial_day_reason(datetime(2026, 9, 28, 13, 57, 49, tzinfo=timezone.utc), now) == 'not_editorial_today'
    assert editorial_day_reason(datetime(2026, 9, 28, 16, 42, 11, tzinfo=timezone.utc), now) is None
    assert non_article_news_reason({'title': 'LNF reforça convite para a COB Expo 2026'}) == 'non_article_event_promotion'
    assert non_article_news_reason({'title': 'Jogador recebe convite para a seleção nacional'}) is None


@pytest.mark.parametrize('title,reason', [
    ('Clive Churchill Medal winner: Peter Sterling - 1986', 'non_news_retrospective_commentary'),
    ('Counter-Strike 2 Update', 'non_article_product_patch'),
    ('Counter-Strike team confirms new tournament roster', None),
])
def test_confirmed_nonnews_products_stop_before_image_and_writer_requests(title, reason):
    assert non_article_news_reason({'title': title}) == reason


def test_nba_image_fallback_excludes_recommendations_and_brandon_is_not_branding():
    from bot.extract import collect_page_image_candidates
    from bot.news_image_http import score_news_image_candidate
    from editorial import classify_media_url
    html = ('<link rel="canonical" href="https://www.nba.com/news/player-update">'
            '<meta property="og:image" content="https://cdn.nba.com/manage/hero.jpg">'
            '<main><div class="ArticleContent_article__fixture"><p>Verified article.</p>'
            '<img src="https://cdn.nba.com/manage/ingram.jpg" alt="Brandon Ingram injury"></div>'
            '<article><img src="https://cdn.nba.com/manage/unrelated.jpg" alt="Other story"></article></main>')
    images = collect_page_image_candidates(html)
    assert {i['url'] for i in images} == {'https://cdn.nba.com/manage/hero.jpg', 'https://cdn.nba.com/manage/ingram.jpg'}
    assert score_news_image_candidate(next(i for i in images if i['source'] == 'body')) >= 0
    for url in ['https://example.test/brand/photo.jpg', 'https://example.test/branding.jpg', 'https://example.test/team_brand_tile.jpg']:
        assert classify_media_url(url) == 'GRAPHIC'


def test_image_dns_failure_stays_closed_and_reports_cause_without_url_secrets(monkeypatch, caplog):
    import logging
    import socket
    from bot import news_image_http as images
    images.clear_image_probe_cache()
    def unavailable(url):
        raise socket.gaierror('fixture')
    monkeypatch.setattr(images, 'validate_public_url', unavailable)
    with caplog.at_level(logging.INFO):
        assert images.probe_news_image('https://cdn.example.test/photo.jpg?secret=never-log') == (False, 'dns_resolution_failed')
    assert 'host=cdn.example.test reason=dns_resolution_failed' in caplog.text
    assert 'never-log' not in caplog.text


def test_mixed_grand_prix_uses_explicit_sport_in_factual_lead():
    title = 'Luke Littler suffers shock defeat to Luke Woodhouse in World Grand Prix opener'
    lead = 'Littler returned to the oche after a quarter-final exit in the World Series of Darts.'
    assert classify_article(title, lead).sport == 'darts'
    assert classify_article('Formula 1 driver wins Grand Prix', 'He also follows the World Series of Darts.').sport == 'motorsport'
    assert non_article_news_reason({'title': 'All Red competition: Win a VIP visit to Anfield for Liverpool v Arsenal - Liverpool FC'}) == 'non_article_commercial_promotion'
    assert non_article_news_reason({'title': 'Liverpool win league title after victory at Anfield'}) is None


@pytest.mark.parametrize('title,held', [
    ('Betting on EuroLeague Teams That Might Lose Their Stars to the NBA Mid-Contract', True),
    ('Besiktas Are Back in the EuroLeague – What the Odds Say About Promoted Clubs', True),
    ('NBA player suspended after betting investigation', False),
])
def test_betting_advice_is_not_current_sports_reporting(title, held):
    assert (non_article_news_reason({'title': title}) == 'non_article_betting_product') is held
