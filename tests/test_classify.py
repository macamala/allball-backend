from bot.classify import classify_article


def test_aston_villa_premier_league():
    result = classify_article(
        "Aston Villa hold Arsenal in Premier League clash",
        "Unai Emery's Aston Villa earned a point against Arsenal at Villa Park.",
        feed_kind="mixed",
        feed_league="germany-bundesliga",
        feed_country="germany",
    )
    assert result.sport == "football"
    assert result.league == "england-premier-league"
    assert result.country == "england"


def test_bayern_bundesliga():
    result = classify_article(
        "Bayern Munich beat Schalke in the Bundesliga",
        "Bayern scored twice in the second half to defeat Schalke.",
        feed_kind="mixed",
        feed_league="england-premier-league",
        feed_country="england",
    )
    assert result.sport == "football"
    assert result.league == "germany-bundesliga"
    assert result.country == "germany"


def test_real_madrid_basketball_liga_acb():
    result = classify_article(
        "Real Madrid basketball beat Valencia in Liga ACB",
        "Real Madrid Baloncesto won their ACB league game in Madrid.",
        feed_kind="league",
        feed_sport="football",
        feed_league="serbia-superliga",
        feed_country="serbia",
    )
    assert result.sport == "basketball"
    assert result.league == "liga-acb"
    assert result.country == "spain"


def test_alcaraz_us_open_not_superliga():
    result = classify_article(
        "Carlos Alcaraz wins US Open quarter-final",
        "Alcaraz reached the US Open semi-finals after a four-set win.",
        feed_kind="mixed",
        feed_league="serbia-superliga",
        feed_country="serbia",
    )
    assert result.sport == "tennis"
    assert result.league == "us-open"
    assert result.country != "serbia"


def test_germany_national_team_world_cup():
    result = classify_article(
        "Germany national team names World Cup squad",
        "Die Mannschaft announced the preliminary World Cup roster.",
        feed_kind="mixed",
        feed_league="serbia-superliga",
        feed_country="serbia",
    )
    assert result.sport == "football"
    assert result.league == "fifa-world-cup"
    assert result.country == "international"


def test_kawhi_raptors_nba_not_euroleague():
    result = classify_article(
        "Kawhi Leonard leads Toronto Raptors past Celtics",
        "The Raptors beat the Boston Celtics in an NBA regular-season game.",
        feed_kind="mixed",
        feed_league="euroleague",
        feed_country="international",
    )
    assert result.sport == "basketball"
    assert result.league == "nba"


def test_mixed_feed_does_not_stamp_league():
    result = classify_article(
        "Formula 1: Verstappen wins the Grand Prix",
        "Max Verstappen took victory in the latest Formula 1 race.",
        feed_kind="mixed",
        feed_sport="football",
        feed_league="serbia-superliga",
        feed_country="serbia",
    )
    assert result.sport == "motorsport"
    assert result.league != "serbia-superliga"
    assert result.country != "serbia"
