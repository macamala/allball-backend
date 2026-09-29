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
            '<body class="post-template-default single single-post">'
            '<article class="small single"><p>The defender scored on his first appearance for the national team. '
            'The coach praised his work with the squad after the final whistle.</p>'
            '<p>Find out more about his career in the video below.</p></article>'
            '<div class="mg-info-author-block"><p>Lorenzo Bettoni is the Editor of Football Italia.</p></div></body>')
    text = article_text_from_html(html)
    assert 'defender scored' in text and 'Lorenzo' not in text and 'video below' not in text
    assert article_text_from_html(html.replace('class="small single"', 'class="missing"')) == ''


def test_video_document_cannot_fall_back_to_rss_description(monkeypatch):
    from bot import extract
    from bot.fetch_sources import source_article_facts
    url = 'https://www.sportschau.de/fussball/dfb-sammelueberspielung-112.html'
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return SimpleNamespace(status_code=200,
            text='<meta property="og:type" content="video.other"><p>A video description with football names.</p>')
    monkeypatch.setattr(extract.httpx, 'Client', Client)
    monkeypatch.setattr(extract, '_NON_ARTICLE_DOCUMENTS', {})
    assert extract.extract_from_url(url) == ('', None)
    assert source_article_facts('', 'A long video caption. '*15, url) == ('', 'non-article-source')
    assert article_text_from_html('<meta property="og:type" content="video.other"><p>Football news caption</p>') == ''
    assert non_article_news_reason({'title':'German squad news','url':'https://www.sportschau.de/fussball/news,dfb-sammelueberspielung-112.html'}) == 'non_article_video_feature'


def test_taranto_archived_summary_marker_is_corrected_and_restored(monkeypatch):
    monkeypatch.setattr('bot.news_image_http.news_image_is_reachable', lambda url: True)
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        body = ("Adelaide United have appointed Adriana Taranto as their captain for the coming women's football season. "
                "The midfielder will lead the team in the 2026/27 Ninja A-League Women's campaign. "
                "The club announced the appointment as the squad continued its preparations for the season.")
        a = Article(id=22195,title="Adelaide United name Adriana Taranto captain for 2026/27 Ninja A-League women's season",
            slug='stable-taranto',summary='[Blank Line]',content=body,ai_content=body,ai_generated=True,sport='football',
            image_url='https://photo.test/taranto.jpg',published_at=stamp,
            source_url='https://aleagues.com.au/news/news-adriana-taranto-named-new-adelaide-united-captain/')
        tax=ArticleTaxonomyResolution(article_id=22195,resolved_sport='football',sport_confidence=.98,
            public_ok=False,resolver_version=RESOLVER_VERSION,hero_media_kind='EDITORIAL_PHOTO')
        incident=NewsIncident(article_id=22195,reason_code='draft_placeholder',phase='postpublish',
            status='open',severity='block',writer_provider='news-audit',writer_model='deterministic',confirmed=False)
        db.add_all([a,tax,incident]);db.commit()
        assert repair_recent_gossip_news(db) == 1 and tax.public_ok
        assert incident.status == 'auto_corrected' and 'Taranto' in a.summary and '[' not in a.summary
        assert a.content==body and a.published_at==stamp and a.slug=='stable-taranto'
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


def test_stadium_debut_and_rebound_cannot_be_expanded(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    source = 'Станковић је први пут на стадиону Рајко Митић истрчао у дресу А репрезентације.'
    assert guard.fact_lock_reason({'summary':'Stanković made his debut against the Netherlands.'}, '', source) == 'expanded_debut_scope'
    assert guard.fact_lock_reason({'summary':'Stanković made his debut at Rajko Mitić Stadium.'}, '', source) is None
    source = 'The goalkeeper saved his initial effort and his teammate scored from the rebound.'
    assert guard.fact_lock_reason({'summary':'He scored and assisted.'}, '', source) == 'unsupported_credited_assist'
    assert guard.fact_lock_reason({'summary':'His shot was saved before the rebound goal.'}, '', source) is None


@pytest.mark.parametrize('source,allowed', [
    ('Искусни репрезентативац Душан Тадић говорио је после утакмице.', False),
    ('Капитен Душан Тадић говорио је после утакмице.', True),
    ('Le capitaine a parlé après le match.', True),
    ('Der Kapitän sprach nach dem Spiel.', True),
    ('O capitão falou depois do jogo.', True),
    ('The player spoke after the match.', False),
])
def test_player_role_needs_source_evidence(monkeypatch, source, allowed):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    result=guard.fact_lock_reason({'summary':'The captain discussed the match.'}, '', source, expected_sport='football')
    assert (result != 'unsupported_player_role:captain') is allowed


def test_tadic_correction_preserves_player_identity_and_statement_scope():
    a=SimpleNamespace(id=22207,ai_generated=True,
        source_url='https://fss.rs/dusan-tadic-pokazali-smo-zajednistvo-i-borbenost-to-je-put-kojim-treba-da-idemo/',
        title='Serbia football captain Dušan Tadić highlights unity', summary='His view of the game.',
        content='The captain explained the defensive effort. He stated that many of these players grew up alongside him and share mutual respect and affection.',ai_content=None)
    assert _correct_confirmed_football_prose(a)
    assert a.title == 'Serbia’s Dušan Tadić highlights unity'
    assert 'captain' not in a.content and 'played alongside' in a.content
    assert _correct_confirmed_football_prose(a) == {}


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


PLAYER_SOURCE = ('La présence de Pierre Kalulu, seulement 3 sélections au compteur avant cette rencontre. '
    'Sur le couloir gauche de la défense, c’était une double première presque pour Andy Diouf. '
    'Lucas Da Cunha a débuté au milieu.')


@pytest.mark.parametrize('body,reason', [
    ('Lucas Da Cunha, a Côme player with only three caps, started in midfield.', 'misattributed_player_caps'),
    ('Pierre Kalulu, making his third appearance for the national team, played on the right flank.', 'changed_appearance_time_scope'),
    ('Andy Diouf debuted in a central defensive role.', 'changed_defensive_side'),
    ('Andy Diouf played as a right-back.', 'changed_defensive_side'),
    ('Pierre Kalulu, who had three caps before the match, played on the right flank.', None),
    ('Andy Diouf played on the left side of defence. Lucas Da Cunha started in midfield.', None),
])
def test_player_statistics_keep_their_owner_time_and_defensive_side(body, reason):
    assert guard._football_player_binding_reason(PLAYER_SOURCE, body) == reason


def test_matching_cap_counts_for_two_named_players_are_not_a_misattribution():
    source = PLAYER_SOURCE + ' Lucas Da Cunha, seulement 3 sélections au compteur avant cette rencontre.'
    assert guard._football_player_binding_reason(source, 'Lucas Da Cunha, with three caps, played in midfield.') is None
    assert guard._football_player_binding_reason('Andy Diouf played in central defence.', 'Andy Diouf played as a centre-back.') is None


@pytest.mark.parametrize('public', [True, False])
def test_source_compared_france_correction_preserves_public_archive_and_never_resurrects(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        bad = ('Pierre Kalulu, making his third appearance for the national team, played on the right flank, while '
               'Andy Diouf debuted in a central defensive role despite limited prior experience in that position. '
               'Lucas Da Cunha, a Côme player with only three caps, started in midfield.')
        a = Article(id=22213,title='France prepares for Nations League match',slug='stable-france',
            content=bad,ai_content=bad,ai_generated=True,sport='football',published_at=stamp,image_url='https://photo.test/france.jpg',
            source_url='https://rmcsport.bfmtv.com/football/equipe-de-france/belgique-france-le-coach-m-a-donne-toute-sa-confiance-les-conseils-de-zinedine-zidane-avant-les-debuts-des-petits-nouveaux_AV-202609290379.html')
        tax=ArticleTaxonomyResolution(article_id=a.id,resolved_sport='football',public_ok=public,resolver_version=RESOLVER_VERSION)
        db.add_all([a,tax]);db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert a.published_at==stamp and a.slug=='stable-france' and a.image_url=='https://photo.test/france.jpg'
        assert tax.public_ok is public and db.get(Article,22213) is not None
        if public:
            assert 'three national-team appearances before the match' in a.content
            assert 'left side of defence' in a.content and 'with only three caps' not in a.content
            assert a.content==a.ai_content and guard._football_player_binding_reason(PLAYER_SOURCE,a.content) is None
            assert db.query(NewsIncident).filter_by(reason_code='confirmed_football_prose_scope',status='auto_corrected').count()==1
        else:
            assert a.content==bad
        assert repair_recent_gossip_news(db)==0
    engine.dispose()
