"""Presentation-layer sport isolation. Never rewrites stored Article.sport."""

from __future__ import annotations

from typing import Optional

from bot.taxonomy import COMPETITIONS, competition_label

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
        "transfer window",
        "goalkeeper",
        "striker",
        "midfielder",
        "premier-league",
        "football",
        "soccer",
    ),
    "tennis": (
        " atp ",
        " wta ",
        "us open",
        "wimbledon",
        "roland garros",
        "australian open",
        "grand slam",
        "alcaraz",
        "djokovic",
        "sinner",
        "swiatek",
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
    ),
}


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


def article_text_blob(article) -> str:
    title = getattr(article, "title", "") or ""
    summary = getattr(article, "summary", "") or ""
    league = getattr(article, "league", "") or ""
    return f"{title} {summary} {league} {competition_label(league)}"


def belongs_to_sport(article, sport: str, *, strict: bool = True) -> bool:
    """True when the article may appear on a public sport/league page."""
    if not sport:
        return True
    if sport == "other":
        stored = getattr(article, "sport", None)
        return stored not in MAIN_SPORTS
    blob = article_text_blob(article)
    stored = getattr(article, "sport", None)
    league = getattr(article, "league", None)
    mapped = league_sport(league)

    own = exclusive_score(blob, sport)
    foreign = {key: exclusive_score(blob, key) for key in EXCLUSIVE_KEYWORDS if key != sport}
    best_foreign = max(foreign.values()) if foreign else 0

    if mapped and mapped != sport:
        return False
    if best_foreign >= 3 and best_foreign > own:
        return False
    if mapped == sport:
        return True
    if own >= 2 and own > best_foreign:
        return True
    if stored == sport and best_foreign == 0:
        return True
    if strict:
        return False
    return stored == sport


def isolation_ok(article, sport: Optional[str] = None, *, strict: bool = True) -> bool:
    target = sport or getattr(article, "sport", None)
    if not target:
        return True
    return belongs_to_sport(article, target, strict=strict)
