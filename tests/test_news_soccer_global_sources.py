from bot.extract import article_text_from_html, collect_page_image_candidates, page_published_at_from_html
from bot.news_fact_guard import _unsupported_known_entities
from bot.news_policy import numeric_tokens, non_article_news_reason
from bot.news_official_indexes import HTML_INDEXES, _same_host_url
from bot.feeds import FEEDS
import pytest


def test_compact_money_cannot_escape_number_guard_and_is_not_multiplied():
    source = 'Clubs share $250m (£185m). Europe receives $125m. The request was 60%.'
    allowed = numeric_tokens(source, include_spelled=True)
    assert {'250', '185', '125', '60', '60%'} <= allowed
    assert numeric_tokens('The £999m package') - allowed == {'999'}
    assert numeric_tokens('185 million pounds and 60 percent') <= allowed
    assert '250000000' not in allowed
    assert numeric_tokens('A 50-50 split; a 4-1 win.', include_spelled=True) == {'50-50', '4-1'}
    assert '50' not in numeric_tokens('A 50-50 split', include_spelled=True)


@pytest.mark.parametrize('source,output', [
    ('Barselona je saopštila odluku.', 'Barcelona announced the decision.'),
    ('Iz Barselone je stigla potvrda.', 'Barcelona confirmed it.'),
    ('Totenhem i Mančester siti', 'Tottenham and Manchester City'),
    ('Челси и Реал Мадрид', 'Chelsea and Real Madrid'),
])
def test_source_club_spellings_do_not_create_a_false_changed_entity(source, output):
    assert _unsupported_known_entities(source, output) == []


def test_club_equivalences_remain_word_bounded_and_do_not_approve_other_clubs():
    assert _unsupported_known_entities('Pseudobarselona is not a club name', 'Barcelona') == ['barcelona']
    assert _unsupported_known_entities('Barselona je saopštila odluku.', 'Chelsea announced it.') == ['chelsea']
    assert _unsupported_known_entities('He is an architect.', 'Inter Milan') == ['inter']
    assert _unsupported_known_entities('Inter Milan confirmed it.', 'AC Milan confirmed it.') == ['ac-milan']
    assert _unsupported_known_entities('Inter Milan confirmed it.', 'Internazionale confirmed it.') == []


def test_a_leagues_body_excludes_signup_modal_sidebar_and_commercial_paragraphs():
    prose = 'The club confirmed that the midfielder will captain its women’s team in the coming football season. '
    html = '<link rel="canonical" href="https://aleagues.com.au/news/captain/">'
    html += '<meta property="og:image" content="https://aleagues.com.au/wp-content/uploads/captain-photo.jpg">'
    html += '<article class="main-article category-news"><div class="entry-content">'
    html += '<p>' + prose * 3 + '</p><p>CLICK HERE TO GET YOUR TICKETS TO THE NINJA A-LEAGUE</p>'
    html += '<p>TRANSFER CENTRE: Your club moves and the latest signing tracker</p></div></article>'
    html += '<div class="hidden"><p>Sign up today to unlock exclusive content and read more.</p></div>'
    html += '<article><p>Unrelated football story about a different club.</p><img src="https://example.test/other-club.jpg"></article>'
    body = article_text_from_html(html)
    assert prose.strip() in body
    assert not any(x in body for x in ('Sign up', 'CLICK HERE', 'TRANSFER CENTRE', 'Unrelated'))
    assert all('other-club' not in x['url'] for x in collect_page_image_candidates(html))
    assert article_text_from_html(html.replace('entry-content', 'absent-body')) == ''
    assert "Women's Team" not in body
    assert article_text_from_html(html.replace('main-article category-news',
        'main-article category-news competition-a-league-women')).startswith("Source article category: Women's Team.")
    assert "Women's Team" not in article_text_from_html(html.replace('<article><p>Unrelated',
        '<article class="competition-a-league-women"><p>Unrelated'))
    cfg = next(x for x in FEEDS if x.get('publisher') == 'A-Leagues')
    assert cfg['sport'] == 'football' and not cfg.get('league')


def test_ge_exact_story_paragraphs_exclude_embedded_video_and_recommendations():
    first = 'O clube confirmou a contratação de um novo treinador para a equipe principal de futebol.'
    second = 'A apresentação do técnico está marcada para a próxima semana no centro de treinamento.'
    html = '<link rel="canonical" href="https://ge.globo.com/futebol/noticia/2026/09/29/coach.ghtml">'
    html += '<meta property="article:published_time" content="2026-09-29T03:00:00-03:00">'
    html += '<div class="mc-article-body"><article><p class="video-caption">Another player scored in an unrelated fixture.</p>'
    html += '<p class="content-text__container">' + first + '</p><p class="content-text__container">' + second + '</p>'
    html += '<p class="content-text__container">+ ✅Clique aqui para seguir o canal ge Vasco no WhatsApp</p></article></div>'
    html += '<p class="content-text__container">A different article about unrelated players and a different club.</p>'
    body = article_text_from_html(html)
    assert first.rstrip('.') in body and second.rstrip('.') in body
    assert not any(x in body for x in ('unrelated', 'WhatsApp'))
    assert str(page_published_at_from_html(html)) == '2026-09-29 06:00:00+00:00'
    assert article_text_from_html(html.replace('mc-article-body', 'missing-body')) == ''
    cfg = next(x for x in HTML_INDEXES if x['id'] == 'ge-brazil-football-news')
    assert _same_host_url(cfg['url'], '/futebol/noticia/2026/09/29/coach.ghtml', cfg['host'], cfg)
    assert _same_host_url(cfg['url'], '/futebol/tabelas/', cfg['host'], cfg) is None
    assert _same_host_url(cfg['url'], 'https://other.test/futebol/noticia/2026/09/29/coach.ghtml', cfg['host'], cfg) is None


def test_new_sources_do_not_turn_calculators_and_transfer_trackers_into_news():
    assert non_article_news_reason({'title': 'Libertadores via Brasileiro? Veja contas'}) == 'non_article_analysis'
    assert non_article_news_reason({'title': 'Ninja A-League 2026/27 Transfer Centre: Your club moves'}) == 'non_article_rolling_tracker'
    assert non_article_news_reason({'title': 'Adriana Taranto named new Adelaide United captain'}) is None
