"""Presentation-layer sport isolation. Never rewrites stored Article.sport."""

from __future__ import annotations

from typing import Optional

from bot.taxonomy import COMPETITIONS
from editorial import sanitize_title

MAIN_SPORTS = ("football", "basketball", "tennis", "motorsport")

EXCLUSIVE_KEYWORDS = {
    "football": (
        "premier league",
        "champions league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "europa league",
        "arsenal",
        "liverpool",
        "manchester united",
        "manchester city",
        "chelsea",
        "tottenham",
        "real madrid",
        "barcelona",
        "nottingham forest",
        "premiership",
        "transfer window",
        "goalkeeper",
        "striker",
        "midfielder",
        "premier-league",
        "football",
        "soccer",
        "haaland",
        "overmars",
        "mourinho",
        "benfica",
        "juventus",
        "liga dos campeoes",
        "liga dos campeões",
    ),
    "tennis": (
        " atp ",
        " wta ",
        "us open",
        "us-open",
        "wimbledon",
        "roland garros",
        "australian open",
        "grand slam",
        "alcaraz",
        "djokovic",
        "sinner",
        "swiatek",
        "gauff",
        "khachanov",
        "sabalenka",
        "tennis",
    ),
    "motorsport": (
        "formula 1",
        "formula one",
        " f1 ",
        "motogp",
        "grand prix",
        "qualifying",
        "pit stop",
        "formula-1",
        "motorsport",
        "verstappen",
        "leclerc",
    ),
    "basketball": (
        " nba ",
        "euroleague",
        "ncaa",
        "lakers",
        "76ers",
        "sixers",
        "celtics",
        "knicks",
        "raptors",
        "basketball",
        "kawhi",
        "lebron",
        "grizzlies",
        "clippers",
        "olympiacos",
    ),
}

# Related-story chrome in summaries/bodies often names another sport.
# Never use that chrome as positive evidence for the requested sport.
OTHER_SPORT_MARKERS = (
    " hockey",
    " hokej",
    " ice hockey",
    " nhl ",
    " rugby",
    " cricket",
    " golf ",
)


def _norm(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return f" {cleaned} "


def exclusive_score(text: str, sport: str) -> int:
    blob = _norm(text)
    score = 0
    for alias in EXCLUSIVE_KEYWORDS.get(sport, ()):
        if alias in blob:
            score += max(2, len(alias.strip().split()))
    return score


def league_sport(league: Optional[str]) -> Optional[str]:
    if not league:
        return None
    meta = COMPETITIONS.get(league)
    if meta:
        return meta.get("sport")
    return None


def article_title_blob(article) -> str:
    """Score titles only. Summaries often contain related-link chrome from other sports."""
    return sanitize_title(getattr(article, "title", "") or "")


def article_text_blob(article) -> str:
    return article_title_blob(article)


def belongs_to_sport(article, sport: str, *, strict: bool = True) -> bool:
    """True when the article may appear on a public sport/league page."""
    if not sport:
        return True
    if sport == "other":
        stored = getattr(article, "sport", None)
        return stored not in MAIN_SPORTS
    title = article_title_blob(article)
    stored = getattr(article, "sport", None)
    league = getattr(article, "league", None)
    mapped = league_sport(league)

    own = exclusive_score(title, sport)
    foreign = {key: exclusive_score(title, key) for key in EXCLUSIVE_KEYWORDS if key != sport}
    best_foreign = max(foreign.values()) if foreign else 0
    other_marker = any(marker in _norm(title) for marker in OTHER_SPORT_MARKERS)

    if mapped and mapped != sport:
        return False
    if best_foreign >= 2 and best_foreign >= own:
        return False
    if other_marker and own < 2:
        return False
    if own >= 2 and own > best_foreign:
        return True
    if not strict and stored == sport and best_foreign == 0 and not other_marker:
        return True
    if strict:
        return False
    return stored == sport and best_foreign == 0


def isolation_ok(article, sport: Optional[str] = None, *, strict: bool = True) -> bool:
    target = sport or getattr(article, "sport", None)
    if not target:
        return True
    return belongs_to_sport(article, target, strict=strict)
