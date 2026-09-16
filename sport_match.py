"""Presentation-layer sport isolation. Never rewrites stored Article.sport."""

from __future__ import annotations

from typing import Optional

from bot.taxonomy import COMPETITIONS, MAIN_SPORT_SLUGS
from editorial import sanitize_title

MAIN_SPORTS = MAIN_SPORT_SLUGS

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
        "f1 qualifying",
        "qualifying session",
        "qualifying lap",
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
        "pistons",
        "qualifying offer",
        "exhibit 10",
        "rebounds",
        "field goal",
        "three-pointer",
        "liga acb",
        "liga endesa",
        "wnba",
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
    blocked = {"barcelona", "barca", "real madrid"}
    for alias in EXCLUSIVE_KEYWORDS.get(sport, ()):
        if alias.strip() in blocked:
            continue
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


def belongs_to_sport(article, sport: str, *, strict: bool = True, resolution=None) -> bool:
    """True when the article may appear on a public sport/league page."""
    if not sport:
        return True
    from taxonomy_resolver import MIN_SPORT_CONFIDENCE, resolve_article_competition

    resolved = resolution if resolution is not None else resolve_article_competition(article)
    if sport == "other":
        return bool(resolved.sport) and resolved.sport not in MAIN_SPORTS
    if not resolved.sport:
        return False
    if resolved.sport != sport:
        return False
    if strict and resolved.sport_confidence < MIN_SPORT_CONFIDENCE:
        return False
    return True


def isolation_ok(article, sport: Optional[str] = None, *, strict: bool = True, resolution=None) -> bool:
    from taxonomy_resolver import resolve_article_competition

    resolved = resolution if resolution is not None else resolve_article_competition(article)
    target = sport or resolved.sport
    if not target:
        return not strict
    return belongs_to_sport(article, target, strict=strict, resolution=resolved)
