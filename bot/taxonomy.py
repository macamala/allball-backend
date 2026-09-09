"""Maintainable sports / competition / team knowledge for classification."""

from typing import Dict, List, Optional, TypedDict


class Competition(TypedDict):
    sport: str
    country: str
    label: str
    aliases: List[str]


COMPETITIONS: Dict[str, Competition] = {
    "england-premier-league": {
        "sport": "football",
        "country": "england",
        "label": "Premier League",
        "aliases": [
            "premier league",
            "english premier league",
            "the epl",
            " epl ",
        ],
    },
    "england-championship": {
        "sport": "football",
        "country": "england",
        "label": "Championship",
        "aliases": ["efl championship", "english championship"],
    },
    "spain-la-liga": {
        "sport": "football",
        "country": "spain",
        "label": "La Liga",
        "aliases": ["la liga", "laliga", "primera division", "primera división"],
    },
    "spain-la-liga-2": {
        "sport": "football",
        "country": "spain",
        "label": "La Liga 2",
        "aliases": ["segunda division", "segunda división", "la liga 2"],
    },
    "italy-serie-a": {
        "sport": "football",
        "country": "italy",
        "label": "Serie A",
        "aliases": ["serie a"],
    },
    "italy-serie-b": {
        "sport": "football",
        "country": "italy",
        "label": "Serie B",
        "aliases": ["serie b"],
    },
    "germany-bundesliga": {
        "sport": "football",
        "country": "germany",
        "label": "Bundesliga",
        "aliases": ["bundesliga", "1. bundesliga"],
    },
    "germany-2-bundesliga": {
        "sport": "football",
        "country": "germany",
        "label": "2. Bundesliga",
        "aliases": ["2. bundesliga", "2 bundesliga"],
    },
    "france-ligue-1": {
        "sport": "football",
        "country": "france",
        "label": "Ligue 1",
        "aliases": ["ligue 1"],
    },
    "france-ligue-2": {
        "sport": "football",
        "country": "france",
        "label": "Ligue 2",
        "aliases": ["ligue 2"],
    },
    "netherlands-eredivisie": {
        "sport": "football",
        "country": "netherlands",
        "label": "Eredivisie",
        "aliases": ["eredivisie"],
    },
    "portugal-primeira-liga": {
        "sport": "football",
        "country": "portugal",
        "label": "Primeira Liga",
        "aliases": ["primeira liga", "liga portugal"],
    },
    "belgium-pro-league": {
        "sport": "football",
        "country": "belgium",
        "label": "Belgian Pro League",
        "aliases": ["belgian pro league", "jupiler pro league"],
    },
    "turkey-super-lig": {
        "sport": "football",
        "country": "turkey",
        "label": "Süper Lig",
        "aliases": ["super lig", "süper lig"],
    },
    "greece-super-league": {
        "sport": "football",
        "country": "greece",
        "label": "Super League Greece",
        "aliases": ["super league greece", "greek super league"],
    },
    "scotland-premiership": {
        "sport": "football",
        "country": "scotland",
        "label": "Scottish Premiership",
        "aliases": ["scottish premiership", "cinch premiership"],
    },
    "switzerland-super-league": {
        "sport": "football",
        "country": "switzerland",
        "label": "Swiss Super League",
        "aliases": ["swiss super league"],
    },
    "croatia-hnl": {
        "sport": "football",
        "country": "croatia",
        "label": "HNL",
        "aliases": ["hnl", "super sport hnl", "croatian first league"],
    },
    "serbia-superliga": {
        "sport": "football",
        "country": "serbia",
        "label": "Mozzart Bet SuperLiga",
        "aliases": ["serbian superliga", "super liga srbije", "mozzart bet superliga"],
    },
    "poland-ekstraklasa": {
        "sport": "football",
        "country": "poland",
        "label": "Ekstraklasa",
        "aliases": ["ekstraklasa"],
    },
    "czech-first-league": {
        "sport": "football",
        "country": "czech-republic",
        "label": "Czech First League",
        "aliases": ["czech first league", "fortuna liga"],
    },
    "usa-mls": {
        "sport": "football",
        "country": "usa",
        "label": "MLS",
        "aliases": ["major league soccer", " mls "],
    },
    "brazil-serie-a": {
        "sport": "football",
        "country": "brazil",
        "label": "Brasileirão",
        "aliases": ["brasileirao", "brasileirão", "brazilian serie a"],
    },
    "argentina-liga-profesional": {
        "sport": "football",
        "country": "argentina",
        "label": "Liga Profesional",
        "aliases": ["liga profesional"],
    },
    "uefa-champions-league": {
        "sport": "football",
        "country": "international",
        "label": "Champions League",
        "aliases": [
            "champions league",
            "liga sampiona",
            "lige sampiona",
            "lige šampiona",
            "liga dos campeoes",
            "liga dos campeões",
            "liga mistru",
            "liga mistrů",
            "ucl",
        ],
    },
    "uefa-europa-league": {
        "sport": "football",
        "country": "international",
        "label": "Europa League",
        "aliases": ["europa league"],
    },
    "uefa-conference-league": {
        "sport": "football",
        "country": "international",
        "label": "Conference League",
        "aliases": ["conference league"],
    },
    "fifa-world-cup": {
        "sport": "football",
        "country": "international",
        "label": "World Cup",
        "aliases": [
            "world cup",
            "mundijal",
            "mundial",
            "fifa world cup",
            "svetsko prvenstvo",
        ],
    },
    "uefa-euro": {
        "sport": "football",
        "country": "international",
        "label": "European Championship",
        "aliases": ["uefa euro", "euros 20"],
    },
    "nba": {
        "sport": "basketball",
        "country": "usa",
        "label": "NBA",
        "aliases": [" nba", "nba ", "national basketball association"],
    },
    "euroleague": {
        "sport": "basketball",
        "country": "international",
        "label": "EuroLeague",
        "aliases": ["euroleague", "evroliga", "euro league basketball"],
    },
    "ncaa-basketball": {
        "sport": "basketball",
        "country": "usa",
        "label": "NCAA Basketball",
        "aliases": [
            "ncaa basketball",
            "march madness",
            "college basketball",
            "recruiting class",
        ],
    },
    "liga-acb": {
        "sport": "basketball",
        "country": "spain",
        "label": "Liga ACB",
        "aliases": ["liga acb", "acb liga", " acb "],
    },
    "us-open": {
        "sport": "tennis",
        "country": "international",
        "label": "US Open",
        "aliases": ["us open", "u.s. open", "usopen"],
    },
    "wimbledon": {
        "sport": "tennis",
        "country": "international",
        "label": "Wimbledon",
        "aliases": ["wimbledon"],
    },
    "roland-garros": {
        "sport": "tennis",
        "country": "international",
        "label": "Roland Garros",
        "aliases": ["roland garros", "french open"],
    },
    "atp-tour": {
        "sport": "tennis",
        "country": "international",
        "label": "ATP Tour",
        "aliases": ["atp tour", "atp finals"],
    },
    "formula-1": {
        "sport": "motorsport",
        "country": "international",
        "label": "Formula 1",
        "aliases": ["formula 1", "formula one", " f1 ", "grand prix"],
    },
}

SPORT_ALIASES: Dict[str, List[str]] = {
    "tennis": [
        "tennis",
        "tenis",
        "atp",
        "wta",
        "alcaraz",
        "djokovic",
        "đoković",
        "djoković",
        "swiatek",
        "sinner",
        "wimbledon",
        "roland garros",
        "us open",
        "australian open",
    ],
    "motorsport": [
        "formula 1",
        "formula one",
        " f1 ",
        "grand prix",
        "motogp",
        "formula 1's",
    ],
    "basketball": [
        "basketball",
        "basket",
        "košarka",
        "kosarka",
        "nba",
        "euroleague",
        "evroliga",
        "ncaa",
        "acb",
    ],
    "football": [
        "football",
        "soccer",
        "fudbal",
        "nogomet",
        "fussball",
        "fußball",
        "voetbal",
        "futebol",
        "premier league",
        "bundesliga",
        "la liga",
        "serie a",
        "ligue 1",
        "champions league",
        "world cup",
        "mundijal",
    ],
}

TEAMS: List[Dict[str, object]] = [
    {
        "aliases": ["aston villa", "unai emery"],
        "sport": "football",
        "league": "england-premier-league",
        "country": "england",
    },
    {
        "aliases": [
            "manchester united",
            "manchester city",
            "liverpool",
            "chelsea",
            "arsenal",
            "tottenham",
            "west ham",
            "newcastle",
            "brighton",
            "crystal palace",
            "nottingham forest",
            "brentford",
            "fulham",
            "wolves",
            "bournemouth",
            "everton",
        ],
        "sport": "football",
        "league": "england-premier-league",
        "country": "england",
    },
    {
        "aliases": [
            "bayern",
            "borussia dortmund",
            "dortmund",
            "leverkusen",
            "rb leipzig",
            "eintracht",
            "gladbach",
            "hoffenheim",
            "union berlin",
            "wolfsburg",
            "stuttgart",
            "werder",
            "schalke",
            "fc koln",
            "fc köln",
        ],
        "sport": "football",
        "league": "germany-bundesliga",
        "country": "germany",
    },
    {
        "aliases": ["real madrid", "barcelona", "atletico", "atlético"],
        "sport": "football",
        "league": "spain-la-liga",
        "country": "spain",
        "ambiguous_sport": True,
    },
    {
        "aliases": [
            "real madrid basketball",
            "real madrid baloncesto",
            "rm baloncesto",
            "valencia basket",
            "baskonia",
            "unicaja",
            "joventut",
        ],
        "sport": "basketball",
        "league": "liga-acb",
        "country": "spain",
    },
    {
        "aliases": ["partizan", "crvena zvezda", "red star belgrade", "tsc backa"],
        "sport": "football",
        "league": "serbia-superliga",
        "country": "serbia",
        "ambiguous_sport": True,
    },
    {
        "aliases": [
            "toronto raptors",
            "raptors",
            "los angeles lakers",
            "lakers",
            "clippers",
            "boston celtics",
            "celtics",
            "golden state",
            "warriors",
            "knicks",
            "heat",
            "nuggets",
            "bucks",
            "mavericks",
            "76ers",
            "sixers",
            "grizzlies",
            "timberwolves",
            "kawhi leonard",
            "lebron",
            "stephen curry",
        ],
        "sport": "basketball",
        "league": "nba",
        "country": "usa",
    },
    {
        "aliases": [
            "carlos alcaraz",
            "alcaraz",
            "novak djokovic",
            "djokovic",
            "đoković",
            "jannik sinner",
            "iga swiatek",
        ],
        "sport": "tennis",
        "league": "atp-tour",
        "country": "international",
    },
]

COUNTRY_LABELS: Dict[str, str] = {
    "england": "England",
    "spain": "Spain",
    "italy": "Italy",
    "germany": "Germany",
    "france": "France",
    "netherlands": "Netherlands",
    "portugal": "Portugal",
    "belgium": "Belgium",
    "turkey": "Turkey",
    "greece": "Greece",
    "scotland": "Scotland",
    "switzerland": "Switzerland",
    "croatia": "Croatia",
    "serbia": "Serbia",
    "poland": "Poland",
    "czech-republic": "Czech Republic",
    "usa": "USA",
    "brazil": "Brazil",
    "argentina": "Argentina",
    "international": "International",
    "europe": "Europe",
    "global": "International",
}

SPORT_LABELS: Dict[str, str] = {
    "football": "Football",
    "basketball": "Basketball",
    "tennis": "Tennis",
    "motorsport": "Motorsport",
}

BROAD_LEAGUE = {
    "football": "football-international",
    "basketball": "basketball-international",
    "tennis": "tennis-international",
    "motorsport": "motorsport-international",
}

# Extra competitions used as safe buckets (not all have dedicated RSS).
for _slug, _label, _sport in (
    ("football-international", "Football", "football"),
    ("basketball-international", "Basketball", "basketball"),
    ("tennis-international", "Tennis", "tennis"),
    ("motorsport-international", "Motorsport", "motorsport"),
):
    if _slug not in COMPETITIONS:
        COMPETITIONS[_slug] = {
            "sport": _sport,
            "country": "international",
            "label": _label,
            "aliases": [],
        }


def competition_label(slug: Optional[str]) -> str:
    if not slug:
        return ""
    info = COMPETITIONS.get(slug)
    if info:
        return info["label"]
    return slug.replace("-", " ").title()


def sport_label(slug: Optional[str]) -> str:
    if not slug:
        return ""
    return SPORT_LABELS.get(slug, slug.replace("-", " ").title())


def country_label(slug: Optional[str]) -> str:
    if not slug:
        return ""
    return COUNTRY_LABELS.get(slug, slug.replace("-", " ").title())
