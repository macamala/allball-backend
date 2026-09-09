"""Classify sport / competition / country from article evidence, not feed buckets."""

from dataclasses import dataclass
from typing import Dict, Optional

from .taxonomy import (
    BROAD_LEAGUE,
    COMPETITIONS,
    SPORT_ALIASES,
    TEAMS,
)
from .textutil import clean_text


@dataclass
class Classification:
    sport: Optional[str]
    league: Optional[str]
    country: Optional[str]
    confidence: str  # high | medium | low
    reason: str


def _norm(text: str) -> str:
    return f" {clean_text(text).lower()} "


def _score_aliases(text: str, aliases) -> int:
    score = 0
    for alias in aliases:
        needle = alias.lower()
        if needle in text:
            score += max(1, len(needle.split()) )
    return score


def classify_article(
    title: str,
    body: str = "",
    feed_kind: str = "mixed",
    feed_sport: Optional[str] = None,
    feed_league: Optional[str] = None,
    feed_country: Optional[str] = None,
) -> Classification:
    text = _norm(f"{title or ''} {body or ''}")
    if text.strip() == "":
        return Classification(None, None, None, "low", "empty-text")

    sport_scores: Dict[str, int] = {}
    for sport, aliases in SPORT_ALIASES.items():
        sport_scores[sport] = _score_aliases(text, aliases)

    team_hits = []
    for team in TEAMS:
        hit = _score_aliases(text, team["aliases"])
        if hit:
            team_hits.append((hit, team))
            sport_scores[team["sport"]] = sport_scores.get(team["sport"], 0) + hit * 2

    # Ambiguous clubs: Real Madrid / Barcelona / Partizan can be basketball.
    basketball_context = sport_scores.get("basketball", 0) >= 2 or any(
        token in text for token in (" acb ", "euroleague", "evroliga", "košarka", "kosarka", "nba")
    )
    tennis_context = sport_scores.get("tennis", 0) >= 2
    motorsport_context = sport_scores.get("motorsport", 0) >= 2

    if basketball_context:
        sport_scores["football"] = max(0, sport_scores.get("football", 0) - 3)
    if tennis_context:
        sport_scores["football"] = 0
        sport_scores["basketball"] = min(sport_scores.get("basketball", 0), 1)
    if motorsport_context:
        sport_scores["football"] = 0

    sport = None
    best_sport = max(sport_scores.values()) if sport_scores else 0
    if best_sport > 0:
        ranked = sorted(sport_scores.items(), key=lambda kv: kv[1], reverse=True)
        sport = ranked[0][0]
        if len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
            # Prefer non-football on ties when mixed context exists.
            non_fb = [s for s, sc in ranked if sc == ranked[0][1] and s != "football"]
            if non_fb:
                sport = non_fb[0]

    if not sport:
        # Genuine league feeds may hint sport only when the article itself is silent.
        # Mixed/national firehoses must not inherit a bucket.
        if feed_kind == "league" and feed_sport:
            sport = feed_sport
        else:
            return Classification(None, None, None, "low", "unknown-sport")

    league_scores: Dict[str, int] = {}
    for slug, meta in COMPETITIONS.items():
        if meta["sport"] != sport:
            continue
        league_scores[slug] = _score_aliases(text, meta["aliases"])

    for hit, team in team_hits:
        if team["sport"] != sport:
            continue
        if team.get("ambiguous_sport") and sport != team["sport"]:
            continue
        slug = team["league"]
        league_scores[slug] = league_scores.get(slug, 0) + hit * 3

    # National-team / World Cup cues (do not inherit publisher country).
    if sport == "football":
        world_cup_hit = any(
            token in text
            for token in (
                "world cup",
                "mundijal",
                "mundial",
                "svetsko prvenstvo",
                "fifa world cup",
            )
        )
        national_hit = any(
            token in text
            for token in (
                "national team",
                "die mannschaft",
                "panceri",
                "germany national",
                "german national",
            )
        )
        if world_cup_hit:
            league_scores["fifa-world-cup"] = league_scores.get("fifa-world-cup", 0) + 8
            if national_hit:
                league_scores["fifa-world-cup"] += 4
        elif national_hit:
            league_scores["football-international"] = (
                league_scores.get("football-international", 0) + 4
            )

    if sport == "tennis":
        if "us open" in text or "u.s. open" in text:
            league_scores["us-open"] = league_scores.get("us-open", 0) + 12
        elif "wimbledon" in text:
            league_scores["wimbledon"] = league_scores.get("wimbledon", 0) + 12
        elif "roland garros" in text or "french open" in text:
            league_scores["roland-garros"] = league_scores.get("roland-garros", 0) + 12

    best_league = None
    best_score = 0
    second = 0
    if league_scores:
        ordered = sorted(league_scores.items(), key=lambda kv: kv[1], reverse=True)
        best_league, best_score = ordered[0]
        second = ordered[1][1] if len(ordered) > 1 else 0

    country = None
    confidence = "low"
    reason = "broad"

    if best_league and best_score >= 3 and best_score > second:
        league = best_league
        country = COMPETITIONS[league]["country"]
        confidence = "high"
        reason = "competition-or-team-evidence"
    elif best_league and best_score >= 1 and second == 0:
        league = best_league
        country = COMPETITIONS[league]["country"]
        confidence = "medium"
        reason = "single-competition-signal"
    else:
        league = BROAD_LEAGUE.get(sport, f"{sport}-international")
        country = "international"
        confidence = "low"
        reason = "insufficient-precision"

    # League-specific feed is a HINT only when evidence does not conflict.
    if (
        feed_kind == "league"
        and feed_sport == sport
        and feed_league
        and confidence != "high"
    ):
        feed_meta = COMPETITIONS.get(feed_league)
        conflicting_team = any(
            team["sport"] == sport
            and team["league"] != feed_league
            and _score_aliases(text, team["aliases"]) > 0
            for team in TEAMS
            if not team.get("ambiguous_sport")
        )
        if feed_meta and feed_meta["sport"] == sport and not conflicting_team:
            league = feed_league
            country = feed_country or feed_meta["country"]
            confidence = "medium"
            reason = "league-feed-hint-no-conflict"

    return Classification(
        sport=sport,
        league=league,
        country=country,
        confidence=confidence,
        reason=reason,
    )
