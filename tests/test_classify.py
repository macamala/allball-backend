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


def test_league_feed_hints_sport_when_article_is_silent():
    result = classify_article(
        "Alabama jump-starts 2027 recruiting class with No. 28 Lumpkin",
        "The Crimson Tide added a five-star prospect from the 2027 cycle.",
        feed_kind="league",
        feed_sport="basketball",
        feed_league="ncaa-basketball",
        feed_country="usa",
    )
    assert result.sport == "basketball"
    assert result.league == "ncaa-basketball"


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

def test_portuguese_joao_matos_story_is_futsal():
    result = classify_article(
        "Varandas sobre João Matos: Ambição de vencer, respeito pelo adversário",
        "João Matos foi destacado numa história sobre a equipa.",
        feed_kind="mixed",
    )
    assert result.sport == "futsal"


def test_aba_liga_story_is_basketball():
    result = classify_article(
        "Klub iz ABA lige poražen 85 razlike, ovo se ne pamti",
        "Vest govori o klubu i utakmici u regionalnom takmičenju.",
        feed_kind="mixed",
    )
    assert result.sport == "basketball"


def test_muay_thai_stays_unclassified_without_registry_sport():
    result = classify_article(
        "Muay-Thai-Spektakel in Bern: Rodriguez begeistert nicht nur FCZ-Spieler",
        "Ein Kampfsport-Abend in Bern.",
        feed_kind="mixed",
    )
    assert result.sport is None

def test_santiago_gimenez_porto_story_is_football():
    result = classify_article(
        "Santiago Gimenez corre por fora no México",
        "O avançado continua ligado ao mercado do FC Porto.",
        feed_kind="mixed",
    )
    assert result.sport == "football"


def test_arouca_story_is_football():
    result = classify_article(
        "Base bem cimentada do Arouca sustenta arranque de alto nível",
        "O clube português começou a época com uma base estável.",
        feed_kind="mixed",
    )
    assert result.sport == "football"


def test_ski_weltmeisterin_story_is_winter_sports():
    result = classify_article(
        "Neue Chefin in der Stadt: Ex-Ski-Weltmeisterin ist kurz nach Hochzeit Mama geworden",
        "Die frühere Ski-Weltmeisterin spricht über ihr neues Familienleben.",
        feed_kind="mixed",
    )
    assert result.sport == "winter-sports"



def test_road_world_championships_beats_bad_american_football_feed_hint():
    result = classify_article(
        "Caroline Andersson conscious after heavy crash at Road World Championships",
        (
            "The Swedish rider crashed heavily during the road world championships. "
            "Medical staff treated the cyclist before she was taken for further checks."
        ),
        feed_kind="league",
        feed_sport="american-football",
        feed_league=None,
        feed_country="usa",
    )
    assert result.sport == "cycling"



def test_cambridgeshire_is_horse_racing_not_ambri_hockey():
    result = classify_article(
        "Pierre Royal becomes first Irish-trained Cambridgeshire winner this century",
        "The jockey guided the horse home in the Cambridgeshire after a strong run.",
        feed_kind="mixed",
    )
    assert result.sport == "horse-racing"


def test_gbgb_calendar_is_greyhound_not_mma():
    result = classify_article(
        "GBGB Calendar Vol 18 No.19 Now Available Online",
        "The GBGB published the latest greyhound racing calendar for licensed tracks.",
        feed_kind="mixed",
    )
    assert result.sport == "greyhound-racing"
