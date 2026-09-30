"""Production incidents: online conspiracy copy and repeated match reporting."""
from datetime import datetime, timedelta, timezone

import pytest

from bot.dedupe import confirmed_football_report_key, existing_near_duplicate, same_report_window
from bot.news_policy import gossip_news_reason, numeric_tokens
from database import SessionLocal
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import repair_recent_duplicate_news, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION


TITLES = (
    'England Secure Nations League Victory Over 10-Man Czechia',
    'England earns first Nations League win with 2:0 victory over ten-man Czechia',
    'England beats Czechia 2:0 in Nations League football match',
)
BODY = ('Pavel Šulc received a red card following a challenge on Elliot Anderson. '
        'Trent Alexander-Arnold crossed to Anthony Gordon, who scored. '
        'Harry Kane added the second goal after the break.')


@pytest.mark.parametrize('title,summary', [
    ('Une théorie sur un enlèvement extraterrestre de Vinicius Jr déchaîne les réseaux', ''),
    ("Vinicius Jr remplacé par un sosie? L'improbable théorie des réseaux sociaux", ''),
    ('Vinicius Jr faces social media conspiracy theories regarding his recent football performances',
     'An unverified theory claims that he was replaced by a double.'),
    ('Social media users speculate on changes to Vinicius Jr following the 2026 World Cup',
     'Online theories suggest that the forward has been replaced by a body double.'),
])
def test_original_and_rewritten_conspiracy_leads_are_rejected(title, summary):
    assert gossip_news_reason({'title': title, 'summary': summary}) == 'non_news_social_media_conspiracy'


@pytest.mark.parametrize('title,summary', [
    ('Manchester City chief calls commission ruling a conspiracy theory', 'The club confirms its appeal.'),
    ('League suspends player for spreading online conspiracy theories', 'The claim concerned an alien body double.'),
    ('Vinicius returns from injury for Real Madrid', 'His return was announced on social media.'),
    ('Actor doubles as football coach for charity match', 'The event was announced online.'),
    ('Vinicius scores twice in Brazil victory', 'Fans celebrate his form on social media.'),
])
def test_formal_sporting_developments_and_normal_online_announcements_remain(title, summary):
    assert gossip_news_reason({'title': title, 'summary': summary}) is None


def test_only_explicit_german_score_grammar_gets_formatting_equivalents():
    text = ('Der 2:0 (0:0)-Erfolg war verdient. Nach dem 2:3 zum Auftakt gegen Spanien '
            'folgte die Reaktion. Zuvor hatten sie mit 1:2 gegen Kroatien verloren.')
    assert {'2-0', '2-3', '1-2'} <= numeric_tokens(text, include_spelled=True)
    assert not {'0-2', '3-2', '2-1', '0-0'} & numeric_tokens(text, include_spelled=True)
    assert '2-0' not in numeric_tokens(text)
    for unrelated in ('Der Zug fährt um 2:03 Uhr.', 'Das Verhältnis ist 2:3.',
                      'Die Mischung mit 1:2 gegen Verunreinigungen hilft.',
                      'Die Sitzung begann nach dem 2:3 Signal.'):
        assert not {'2-3', '1-2', '2-03'} & numeric_tokens(unrelated, include_spelled=True)


def test_match_report_identity_uses_the_audited_full_event_and_not_shared_clubs():
    keys = {confirmed_football_report_key(title, BODY) for title in TITLES}
    assert len(keys) == 1 and None not in keys
    assert confirmed_football_report_key(
        'England defeats Czechia 2:0 in Nations League match after red card',
        BODY.replace('Trent Alexander-Arnold', 'Alexander-Arnold')) in keys
    for name in ('Pavel Šulc', 'Elliot Anderson', 'Trent Alexander-Arnold', 'Anthony Gordon', 'Harry Kane', 'red card'):
        assert confirmed_football_report_key(TITLES[0], BODY.replace(name, 'other')) is None


@pytest.mark.parametrize('title', [
    'Czech Republic loses to England after early red card as coach assesses injuries',
    'England coach reacts to Nations League victory over Czechia',
    'England wins Nations League match against Czechia but Kane suffers injury',
    'England women secure Nations League victory over Czechia',
    'England Under-21 wins Nations League match against Czechia',
    'England beats Czechia 3:0 in Nations League football match',
    'England beats Czechia 0:2 in Nations League football match',
    'England could secure Nations League victory over Czechia',
    'England beats Czechia in a World Cup match',
])
def test_distinct_angles_categories_scores_and_previews_cannot_be_collapsed(title):
    assert confirmed_football_report_key(title, BODY) is None


def test_report_comparisons_require_close_source_publication_times():
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    assert same_report_window(now, now.replace(tzinfo=None))
    assert same_report_window(now, now + timedelta(hours=24))
    assert not same_report_window(now, now + timedelta(hours=24, seconds=1))
    assert not same_report_window(None, now)


def test_ingest_and_repairs_hold_bad_cards_but_keep_archive_and_distinct_reaction():
    db, ids = SessionLocal(), []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        for index, title in enumerate((*TITLES, 'Czech coach assesses injuries after England match',
                                       'Social media users discuss an unverified theory about a body double')):
            body = BODY if index < 4 else 'Online theories suggest an alien replaced the player.'
            article = Article(title=title, content=body, summary=body,
                slug=f'admission30-{index}', external_id=f'https://fixture.test/admission30/{index}',
                published_at=now + timedelta(minutes=index), created_at=now,
                ai_generated=True, sport='football', image_url='https://fixture.test/photo.jpg')
            db.add(article); db.flush(); ids.append(article.id)
            db.add(ArticleTaxonomyResolution(article_id=article.id, resolver_version=RESOLVER_VERSION,
                resolved_sport='football', public_ok=True))
            if index == 0:
                assert existing_near_duplicate(db, TITLES[2], now, body=BODY).id == article.id
        db.commit()
        assert repair_recent_duplicate_news(db) == 2
        assert repair_recent_gossip_news(db) == 1
        visible = {row.article_id for row in db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id.in_(ids), ArticleTaxonomyResolution.public_ok.is_(True))}
        assert visible == {ids[2], ids[3]}
        assert db.query(Article).filter(Article.id.in_(ids)).count() == 5
        assert db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids), NewsIncident.status == 'open').count() == 3
        assert repair_recent_duplicate_news(db) == 0
        assert repair_recent_gossip_news(db) == 0
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit(); db.close()


def test_same_headline_cannot_bypass_source_date_boundary_in_ingest_or_repair():
    db, ids = SessionLocal(), []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        for index, stamp in enumerate((now - timedelta(hours=25), now)):
            if index:
                assert existing_near_duplicate(db, TITLES[0], stamp, body=BODY) is None
            article = Article(title=TITLES[0], content=BODY, slug=f'report-window30-{index}',
                external_id=f'https://fixture.test/window30/{index}', published_at=stamp,
                created_at=now, sport='football', ai_generated=True)
            db.add(article); db.flush(); ids.append(article.id)
            db.add(ArticleTaxonomyResolution(article_id=article.id, resolver_version=RESOLVER_VERSION,
                resolved_sport='football', public_ok=True))
        db.commit()
        assert repair_recent_duplicate_news(db) == 0
    finally:
        db.query(NewsIncident).filter(NewsIncident.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(ArticleTaxonomyResolution).filter(ArticleTaxonomyResolution.article_id.in_(ids)).delete(synchronize_session=False)
        db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.commit(); db.close()
