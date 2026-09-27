from types import SimpleNamespace

from bot.fetch_sources import _reconcile_public_taxonomy
from taxonomy_resolver import TaxonomyResolution


def resolution(sport=None, competition=None):
    return TaxonomyResolution(
        sport=sport,
        competition=competition,
        sport_confidence=0.0,
        competition_confidence=0.0,
        evidence=[],
    )


def tags(sport='winter-sports', league=None, confidence='high'):
    return SimpleNamespace(
        sport=sport,
        league=league,
        confidence=confidence,
        reason='sport-alias',
    )


def test_rewrite_cannot_erase_source_proven_sport():
    reconciled, reason=_reconcile_public_taxonomy(tags(), resolution(), {'kind':'mixed'})
    assert reason is None
    assert reconciled.sport == 'winter-sports'
    assert reconciled.public_competition is None
    assert reconciled.sport_confidence == 0.92
    assert reconciled.evidence == ['source-classifier-sport:sport-alias']


def test_rewrite_sport_conflict_stays_fail_closed():
    reconciled, reason=_reconcile_public_taxonomy(
        tags('football'),
        resolution('basketball'),
        {'kind':'mixed'},
    )
    assert reconciled is None
    assert reason == 'taxonomy-conflict'


def test_unresolved_source_and_rewrite_never_publish():
    reconciled, reason=_reconcile_public_taxonomy(
        tags(None, confidence='low'),
        resolution(),
        {'kind':'mixed'},
    )
    assert reconciled is None
    assert reason == 'taxonomy-unresolved-after-rewrite'


def test_dedicated_feed_can_preserve_exact_competition_with_source_sport():
    reconciled, reason=_reconcile_public_taxonomy(
        tags('football', 'england-premier-league'),
        resolution(),
        {'kind':'league','sport':'football','league':'england-premier-league'},
    )
    assert reason is None
    assert reconciled.sport == 'football'
    assert reconciled.public_competition == 'england-premier-league'
    assert 'trusted-dedicated-feed-competition' in reconciled.evidence
