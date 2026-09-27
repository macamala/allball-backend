"""Conservative news aliases for sports that were not previously classified.

Existing SPORT_ALIASES lists are not replaced. These keys are added only when
the slug is absent, so tennis/football/golf behaviour stays intact.
"""

from __future__ import annotations

from typing import Dict, List

# Distinctive phrases only. Shared words like "hockey" or "open" are avoided.
EXTRA_SPORT_ALIASES: Dict[str, List[str]] = {
    "football": [
        "kv kortrijk",
        "lommel",
        "strafschoppen",
        "wereldkampioen spanje",
        "francisco moura",
        "gabri martínez",
        "gabri martinez",
        "sp. braga",
        "hugo gambor",
        "hložek",
        "hlozek",
        "coufal",
        "karabec",
        "paunović",
        "paunovic",
        "zvezdin biser",
        "nati-noten",
        "nordmazedonien",
        "mitrovic ganha confiança",
        "bazunu",
        "coundoul",
        "elimbi",
        "buatu",
        "lucao",
        "lucão",
        "gil vicente",
        "ana nogueira",
        "racing power",
        "santiago gimenez",
        "santiago giménez",
        "fc arouca",
        "do arouca",
    ],
    "basketball": ["nba rank", "aba liga", "aba lige", "aba league"],
    "boxing": ["radivoje kalajdžić", "radivoje kalajdzic", "srbin u londonu prebio britanca"],
    "handball": ["rukometašice", "rukometasice", "trifej makedonije", "ohridu"],
    "rugby-league": [
        "rugby league",
        " nrl ",
        "super league rugby",
        "super league grand final",
        "wigan warriors",
        "wakefield trinity",
    ],
    "futsal": ["futsal", "joão matos", "joao matos"],
    "water-polo": ["water polo", "vaterpolo", "vaterpolisti", "partizan na primorac", "primorac kotor", "kotoranima"],
    "field-hockey": ["field hockey"],
    "australian-rules": ["australian rules", " afl ", "aussie rules"],
    "netball": ["netball"],
    "lacrosse": ["lacrosse"],
    "table-tennis": ["table tennis", "ping pong", " wtt ", "ittf"],
    "badminton": ["badminton", "bwf world"],
    "darts": [" darts ", "pdc world", "ally pally"],
    "horse-racing": ["horse racing", "thoroughbred racing"],
    "greyhound-racing": ["greyhound racing", "greyhound race"],
    "harness-racing": ["harness racing", "trotting race"],
    "athletics": [" athletics ", "track and field", "world athletics"],
    "cycling": [
        "road world championship",
        "road world championships",
        "road worlds",
        "cycling world championship",
        "cycling world championships",
        "rad-wm",
        "rad wm",
        "uci road",
    ],
    "swimming": [" swimming ", "world aquatics"],
    "winter-sports": ["winter sports", "alpine skiing", "figure skating", "ski-weltmeister", "ski-weltmeisterin"],
    "mma": ["vémola", "vemola"],
    "ice-hockey": [
        "ice hockey",
        "ambri",
        "ambrì",
        "tipsport extraliga",
        "extraliga",
        "cardiff devils",
        "sheffield steelers",
        "nottingham panthers",
    ],
    "volleyball": ["volleyball", "eurovolley"],
    "esports": ["esports", "e-sports"],
    "ea-sports-fc": ["ea sports fc", "efootball"],
    "counter-strike": ["counter-strike", "counter strike"],
    "league-of-legends": ["league of legends"],
    "dota-2": ["dota 2", "dota2"],
    "valorant": ["valorant"],
    "call-of-duty": ["call of duty"],
    "overwatch": ["overwatch"],
    "rocket-league": ["rocket league"],
}


def extra_sport_aliases() -> Dict[str, List[str]]:
    return dict(EXTRA_SPORT_ALIASES)
