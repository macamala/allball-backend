from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot.extract import article_text_from_html
from bot.rewrite_ai import parse_ai_output
from bot.news_policy import non_article_news_reason
from bot import news_fact_guard as guard
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_football_prose, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION


@pytest.mark.parametrize('separator', ['Blank line', '[Blank Line]', 'blank line', ''])
def test_literal_format_instruction_never_becomes_summary(separator):
    value = parse_ai_output(f'Independent headline\n{separator}\nAn English summary.\n{separator}\nFirst factual paragraph.\n\nSecond factual paragraph.')
    assert value == {'title':'Independent headline', 'summary':'An English summary.',
                     'body':'First factual paragraph.\n\nSecond factual paragraph.'}


def test_remaining_placeholder_and_author_bio_fail_admission():
    assert non_article_news_reason({'title':'Football report', 'summary':'Blank line'}) == 'draft_placeholder'
    assert non_article_news_reason({'title':'Football report', 'body':'Lorenzo Bettoni serves as the Editor of Football Italia.'}) == 'source_author_biography'
    assert non_article_news_reason({'title':'Club appoints coach', 'body':'The club said its coach would meet reporters.'}) is None


def test_football_italia_scope_excludes_author_bio_and_video_promotion():
    html = ('<meta property="og:url" content="https://football-italia.net/report/">'
            '<article class="small single"><p>The defender scored on his first appearance for the national team. '
            'The coach praised his work with the squad after the final whistle.</p>'
            '<p>Find out more about his career in the video below.</p></article>'
            '<div class="mg-info-author-block"><p>Lorenzo Bettoni is the Editor of Football Italia.</p></div>')
    text = article_text_from_html(html)
    assert 'defender scored' in text and 'Lorenzo' not in text and 'video below' not in text
    assert article_text_from_html(html.replace('class="small single"', 'class="missing"')) == ''


def test_stadium_debut_and_rebound_cannot_be_expanded(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    source = 'Станковић је први пут на стадиону Рајко Митић истрчао у дресу А репрезентације.'
    assert guard.fact_lock_reason({'summary':'Stanković made his debut against the Netherlands.'}, '', source) == 'expanded_debut_scope'
    assert guard.fact_lock_reason({'summary':'Stanković made his debut at Rajko Mitić Stadium.'}, '', source) is None
    source = 'The goalkeeper saved his initial effort and his teammate scored from the rebound.'
    assert guard.fact_lock_reason({'summary':'He scored and assisted.'}, '', source) == 'unsupported_credited_assist'
    assert guard.fact_lock_reason({'summary':'His shot was saved before the rebound goal.'}, '', source) is None


def test_exact_stankovic_repair_preserves_dates_images_and_public_archive():
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        bad = "Young Serbian international made his debut against Netherlands and praised his team's character despite a 1:2 defeat.\nBlank line\nStanković spoke about his first appearance at Rajko Mitić Stadium."
        a = Article(id=22204, title='Stanković speaks about Serbia stadium appearance', slug='stable',
            summary='Blank line', content=bad, ai_content=bad, sport='football',ai_generated=True,
            source_url='https://fss.rs/aleksandar-stankovic-prva-utakmica-na-marakani-u-dresu-a-tima-ostvarenje-jednog-od-mojih-snova/',
            image_url='https://photo.test/stankovic.jpg',published_at=stamp)
        tax = ArticleTaxonomyResolution(article_id=22204,resolved_sport='football',resolver_version=RESOLVER_VERSION,public_ok=True)
        db.add_all([a,tax]);db.commit()
        assert repair_recent_gossip_news(db) == 1
        assert tax.public_ok and a.published_at == stamp and a.slug == 'stable' and a.image_url.endswith('stankovic.jpg')
        assert 'first senior Serbia appearance at Rajko Mitić Stadium' in a.summary
        assert 'Blank line' not in a.content and 'made his debut' not in a.content
        assert a.ai_content == a.content
        assert db.query(NewsIncident).filter_by(reason_code='confirmed_football_prose_scope',status='auto_corrected').count() == 1
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


def test_football_copy_repair_is_source_and_id_scoped():
    a = SimpleNamespace(id=22210,ai_generated=True,source_url='https://unrelated.test/story',
        summary='Original summary',content='Lorenzo Bettoni serves as the Editor of Football Italia.',ai_content=None)
    before = vars(a).copy()
    assert _correct_confirmed_football_prose(a) == {} and before == vars(a)


def test_kayode_repair_removes_uncredited_assist_ratings_and_author_only():
    a = SimpleNamespace(id=22210,ai_generated=True,
        source_url='https://football-italia.net/kayode-impresses-italy-debut-palestra-duel/',
        summary='Brentford defender Michael Kayode earned Man of the Match honors from multiple Italian newspapers after scoring and assisting in a victory.',
        content='The 22-year-old right-back marked his senior international debut. Gazzetta and Corriere della Sera both assigned him a rating of 7/10 for the display. Lorenzo Bettoni serves as the Editor of Football Italia.', ai_content=None)
    assert _correct_confirmed_football_prose(a)
    assert 'assisting' not in a.summary and '4-1 in Bursa' in a.summary
    assert a.content == 'The 22-year-old Brentford defender marked his senior international debut.'
    assert _correct_confirmed_football_prose(a) == {}
