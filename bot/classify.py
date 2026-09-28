"""Classify sport / competition / country from article evidence, not feed buckets."""

from dataclasses import dataclass
import re
from typing import Dict, Optional

from .taxonomy import (
    BROAD_LEAGUE,
    COMPETITIONS,
    SPORT_ALIASES,
    TEAMS,
)
from .textutil import clean_text
from .news_policy import CRICKET_TITLE_RE, VOLLEYBALL_TITLE_RE, RUGBY_LEAGUE_TITLE_RE, RUGBY_UNION_TITLE_RE, unsupported_news_sport


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
    """Score aliases as complete words/phrases, never arbitrary substrings."""
    score = 0
    for alias in aliases:
        needle = clean_text(str(alias or "")).lower().strip()
        if not needle:
            continue
        pattern = re.compile(
            r"(?<!\w)" + r"\s+".join(re.escape(part) for part in needle.split()) + r"(?!\w)",
            re.IGNORECASE,
        )
        if pattern.search(text):
            score += max(1, len(needle.split()))
    return score


def classify_article(
    title: str,
    body: str = "",
    feed_kind: str = "mixed",
    feed_sport: Optional[str] = None,
    feed_league: Optional[str] = None,
    feed_country: Optional[str] = None,
) -> Classification:
    title_text = _norm(title or "")
    body_text = _norm(body or "")
    text = _norm(f"{title or ''} {body or ''}")
    if text.strip() == "":
        return Classification(None, None, None, "low", "empty-text")
    if unsupported_news_sport(title, body):
        return Classification(None, None, None, "low", "unsupported-news-sport")

    sport_scores: Dict[str, int] = {}
    for sport, aliases in SPORT_ALIASES.items():
        title_score = _score_aliases(title_text, aliases)
        body_score = _score_aliases(body_text, aliases)
        sport_scores[sport] = title_score * 3 + max(0, body_score - title_score)

    # Mixed Asian Games reporting commonly uses these precise event terms
    # instead of the sport label. Never classify a generic relay as athletics:
    # medley/freestyle relays belong to swimming.
    if re.search(r"\bshuttlers?\b", title_text):
        sport_scores["badminton"] += 12
    if re.search(r"\boktagon(?:u|e|em)?\b", title_text):
        sport_scores["mma"] += 12
    if re.search(r"\b(?:4\s*[x×]\s*(?:100|400)\s*m(?:etres?|eters?)?|100\s*m|200\s*m|400\s*m)\s+(?:relay|sprint|hurdles)\b", title_text) and not re.search(r"\b(?:swim\w*|freestyle|medley|pool)\b", text):
        sport_scores["athletics"] += 12

    team_hits = []
    for team in TEAMS:
        title_hit = _score_aliases(title_text, team["aliases"])
        hit = title_hit or _score_aliases(text, team["aliases"])
        if title_hit:
            team_hits.append((title_hit, team))
            if team.get("ambiguous_sport"):
                continue
            sport_scores[team["sport"]] = sport_scores.get(team["sport"], 0) + title_hit * 2
        elif hit:
            # Body-only team mentions are often related-link chrome.
            continue

    basketball_context = sport_scores.get("basketball", 0) >= 4 or any(
        token in title_text
        for token in (
            " acb ",
            "euroleague",
            "evroliga",
            "euroliga",
            "košarka",
            "kosarka",
            "nba",
            "liga endesa",
            "baloncesto",
        )
    )
    tennis_context = _score_aliases(title_text, SPORT_ALIASES.get("tennis", [])) >= 2
    cycling_context = _score_aliases(title_text, SPORT_ALIASES.get("cycling", [])) >= 2
    darts_context = _score_aliases(title_text, SPORT_ALIASES.get("darts", [])) >= 1
    snooker_context = _score_aliases(title_text, SPORT_ALIASES.get("snooker", [])) >= 1
    motorsport_context = _score_aliases(title_text, SPORT_ALIASES.get("motorsport", [])) >= 2
    # Explicit sport-name evidence must beat generic football tournament phrases
    # such as "World Cup" or "Champions League" in niche-sport headlines.
    niche_context = next(
        (
            candidate
            for candidate in ("field-hockey", "water-polo", "futsal")
            if _score_aliases(title_text, SPORT_ALIASES.get(candidate, [])) > 0
        ),
        None,
    )

    if basketball_context:
        sport_scores["football"] = max(0, sport_scores.get("football", 0) - 3)
    if re.search(r"\b(?:boxing(?!\s+day)|boxers?)\b", title_text):
        sport_scores["boxing"] = max(sport_scores.get("boxing", 0), 12)
        sport_scores["football"] = 0
    if CRICKET_TITLE_RE.search(title_text):
        # World Cup and national-team names are shared with football. Explicit
        # cricket formats, including Unicode hyphens, resolve that ambiguity.
        sport_scores["cricket"] = max(sport_scores.get("cricket", 0), 12)
        sport_scores["football"] = 0
    if VOLLEYBALL_TITLE_RE.search(title_text):
        sport_scores["volleyball"] = max(sport_scores.get("volleyball", 0), 12)
        sport_scores["boxing"] = 0
        sport_scores["tennis"] = 0
    # A swimmer headline is stronger than an incidental basketball comparison
    # in the story. Do not use this override for a cross-sport headline.
    if (re.search(r"\b(?:swimming|swimmers?)\b", title_text)
            and not re.search(r"\b(?:basketball|football|soccer|nba|nfl|tennis|water polo|triathlon)\b", title_text)):
        sport_scores["swimming"] = max(max(sport_scores.values()) + 4, 12)
    # National teams and World Cup appear in both codes and soccer. Explicit
    # rugby evidence in the title/lead must outrank those shared names.
    explicit_other_title = re.search(
        r"\b(?:soccer|football|basketball|tennis|cricket|volleyball|handball|futsal|hockey|"
        r"baseball|boxing|mma|ufc|golf|cycling|athletics|swimming|netball|lacrosse|"
        r"snooker|darts|afl|nba|nfl|nhl|badminton|esports)\b", title_text,
    )
    rugby_evidence = title_text + (" " + body_text[:900] if not explicit_other_title else "")
    if RUGBY_LEAGUE_TITLE_RE.search(rugby_evidence) and not RUGBY_UNION_TITLE_RE.search(rugby_evidence):
        sport_scores["rugby-league"] = max(sport_scores.get("rugby-league", 0), 12)
        sport_scores["football"] = 0
        sport_scores["rugby"] = 0
    elif RUGBY_UNION_TITLE_RE.search(rugby_evidence) and not RUGBY_LEAGUE_TITLE_RE.search(rugby_evidence):
        sport_scores["rugby"] = max(sport_scores.get("rugby", 0), 12)
        sport_scores["football"] = 0
        sport_scores["rugby-league"] = 0
    if tennis_context:
        sport_scores["football"] = min(sport_scores.get("football", 0), sport_scores.get("football", 0))
        sport_scores["basketball"] = min(sport_scores.get("basketball", 0), 1)
    if cycling_context:
        # Cycling headlines can legitimately contain "Grand Prix". Strong road/
        # UCI/peloton evidence must beat that generic motorsport phrase.
        sport_scores["cycling"] = max(sport_scores.get("cycling", 0), 8)
        sport_scores["motorsport"] = 0
    if darts_context:
        # "World Grand Prix" is also a major darts event.
        sport_scores["darts"] = max(sport_scores.get("darts", 0), 8)
        sport_scores["motorsport"] = 0
    if snooker_context:
        # Snooker also uses "World Grand Prix"; the sport word wins.
        sport_scores["snooker"] = max(sport_scores.get("snooker", 0), 8)
        sport_scores["motorsport"] = 0
    if motorsport_context and not basketball_context and not cycling_context and not darts_context and not snooker_context:
        pass
    if niche_context:
        sport_scores["football"] = 0
        if niche_context == "field-hockey":
            sport_scores["ice-hockey"] = 0
    # Handball shares World Cup / Champions League with soccer. A clear sport
    # word or its federations in clean article text beats those generic names.
    football_exclusive = [a for a in SPORT_ALIASES['football']
        if a.strip() not in {'world cup', 'champions league', 'premier league', 'bundesliga'}]
    if (re.search(r'\b(?:handball|ehf|ihf|rukomet)\b', text)
            and not _score_aliases(title_text, football_exclusive)
            and not any(team['sport']=='football' and not team.get('ambiguous_sport') for _,team in team_hits)):
        sport_scores['handball'] = max(sport_scores['handball'], sport_scores['football'] + 4)
        sport_scores['football'] = 0
    if any(token in text for token in (" golf ", " pga ", "birdie", "bogey", "fairway")) and "us open" in text:
        sport_scores["tennis"] = 0

    sport = None
    best_sport = max(sport_scores.values()) if sport_scores else 0
    if best_sport > 0:
        ranked = sorted(sport_scores.items(), key=lambda kv: kv[1], reverse=True)
        sport = ranked[0][0]
        if len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
            non_fb = [s for s, sc in ranked if sc == ranked[0][1] and s != "football"]
            if non_fb:
                sport = non_fb[0]
        if len(ranked) > 1 and ranked[1][1] > 0 and ranked[0][1] < ranked[1][1] * 1.15:
            sport = None

    if not sport:
        # A curated sport-specific feed may break a weak/ambiguous tie, but may
        # never override strong contradictory article evidence.
        feed_score = sport_scores.get(feed_sport, 0) if feed_sport else 0
        if (
            feed_kind == "league"
            and feed_sport
            and (
                best_sport == 0
                or feed_score > 0 and feed_score >= best_sport * 0.75
            )
        ):
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
        if "us open" in title_text or "u.s. open" in title_text:
            league_scores["us-open"] = league_scores.get("us-open", 0) + 12
        elif "wimbledon" in title_text:
            league_scores["wimbledon"] = league_scores.get("wimbledon", 0) + 12
        elif "roland garros" in title_text or "french open" in title_text:
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
