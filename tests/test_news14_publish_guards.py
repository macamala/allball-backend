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


def test_cross_source_near_duplicate_headlines_are_detected():
    from bot.dedupe import titles_are_near_duplicate
    assert titles_are_near_duplicate(
        "Arsenal confirm Bukayo Saka will miss Liverpool clash after injury",
        "Arsenal confirms Saka will miss Liverpool game following injury",
    )
    assert not titles_are_near_duplicate(
        "Arsenal confirm Bukayo Saka will miss Liverpool clash after injury",
        "Arsenal announce new academy partnership for next season",
    )


def test_road_cycling_world_title_beats_generic_grand_prix():
    from bot.classify import classify_article
    import public_index

    title=(
        "Brandon McNulty wins Montreal Grand Prix, ends 33-year drought "
        "for American road race world title"
    )
    classified=classify_article(title, title, feed_kind="mixed")
    assert classified.sport == "cycling"
    assert public_index._explicit_title_sport_override(title) == "cycling"


def test_plain_formula_one_grand_prix_is_not_forced_to_cycling():
    import public_index
    assert public_index._explicit_title_sport_override(
        "Formula 1 Singapore Grand Prix qualifying report"
    ) is None


def test_darts_world_grand_prix_stays_darts():
    from bot.classify import classify_article
    import public_index

    title="Darts World Grand Prix to Begin with Unique Format"
    classified=classify_article(title,title,feed_kind="mixed")
    assert classified.sport == "darts"
    assert public_index._explicit_title_sport_override(title) == "darts"


def test_football_feed_about_text_cannot_trigger_boxing_bout():
    from bot.classify import classify_article
    import public_index

    title="Napoli agree new deal with defender Amir Rrahmani"
    body=(
        "Napoli announced a new contract with defender Amir Rrahmani and spoke "
        "about the agreement in a club update."
    )
    classified=classify_article(
        title,
        body,
        feed_kind="league",
        feed_sport="football",
        feed_league="italy-serie-a",
        feed_country="italy",
    )
    assert classified.sport == "football"
    assert public_index._explicit_title_sport_override(title) == "football"


def test_short_mma_alias_is_word_bounded():
    from bot.classify import classify_article
    cricket=classify_article(
        "South Africa seal series win over Australia",
        "A commanding performance helped South Africa win the cricket series.",
        feed_kind="mixed",
    )
    assert cricket.sport == "cricket"

    cycling=classify_article(
        "World road race title decided in Canada",
        "A commanding ride in the peloton decided the road cycling championship.",
        feed_kind="mixed",
    )
    assert cycling.sport == "cycling"


def test_fact_guard_allows_sport_implicit_draft_when_source_sport_is_known():
    from bot.news_fact_guard import fact_lock_reason
    draft={
        "title":"South Africa seal the series",
        "summary":"South Africa completed the series win over Australia.",
        "body":"South Africa secured the series against Australia with a victory in the final contest. The visitors completed their campaign ahead of the home side after the deciding match.",
    }
    source_title="Superb South Africa seal series win over Australia"
    source_body="South Africa, the visiting cricket team, beat Australia in the final match to win the series. The result decided the series and ended the campaign."
    assert fact_lock_reason(draft,source_title,source_body,expected_sport="cricket") is None
