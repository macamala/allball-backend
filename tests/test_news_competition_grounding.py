from types import SimpleNamespace

import pytest

from bot import news_fact_guard as guard
from bot import fetch_sources as ingest
from public_index import _correct_confirmed_mccabe_copy
from taxonomy_resolver import TaxonomyResolution


def test_shared_football_club_names_cannot_create_a_league_fact(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    source = "Source article category: Women's Team. Chelsea defeated Arsenal."
    assert guard.fact_lock_reason({'body': 'Chelsea won in the Premier League.'},
        'Club news', source, expected_sport='football') == 'unsupported_competition:england-premier-league'
    assert guard.competition_in_source('england-premier-league', source) is False
    assert guard.competition_in_source('england-premier-league', 'The English Premier League confirmed the decision.')


@pytest.mark.parametrize('source,retained', [('Chelsea met Arsenal.', False), ('Chelsea played in the Premier League.', True)])
def test_public_competition_requires_source_evidence(source, retained):
    resolution = TaxonomyResolution('football', 'england-premier-league', .98, .97, ['club-name'])
    result = ingest._source_grounded_resolution(resolution, 'Team news', source)
    assert result.sport == 'football' and result.sport_confidence == .98
    assert result.public_competition == ('england-premier-league' if retained else None)
    assert resolution.public_competition == 'england-premier-league'


def test_writer_never_receives_inferred_league_as_verified_fact(monkeypatch):
    captured = []
    monkeypatch.setattr(ingest, 'write_ninkosports_story', lambda **kwargs: captured.append(kwargs) or '')
    ingest._ai_story('Chelsea women news', 'Chelsea defeated Arsenal in London.', 'football',
                     'england-premier-league', 6000)
    assert captured[0]['league'] == ''


def test_audited_womens_copy_repair_preserves_identity_and_is_idempotent():
    row = SimpleNamespace(id=22166, ai_generated=True,
        source_url='https://www.chelseafc.com/en/news/article/katie-mccabe-on-playing-smart-and-riding-the-storms-against-former-club',
        title='Katie McCabe helps Chelsea defeat former club Arsenal in Premier League match',
        content='The win mattered most.', ai_content='The win mattered most.',
        league='england-premier-league', country='england', slug='stable-original-url')
    tax = SimpleNamespace(resolved_competition='england-premier-league', competition_confidence=.98, public_ok=True)
    assert _correct_confirmed_mccabe_copy(row, tax)
    assert "Chelsea Women's" in row.title and 'Premier League' not in row.title
    assert row.league is None and tax.resolved_competition is None
    assert row.slug == 'stable-original-url' and tax.public_ok is True
    assert _correct_confirmed_mccabe_copy(row, tax) == {}
    row.id = 999
    assert _correct_confirmed_mccabe_copy(row, tax) == {}
