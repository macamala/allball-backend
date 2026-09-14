"""Homepage editorial ranking, diversity and exact-ID deduplication.

Quality first, then diversity, then recency. Never fabricates importance.
Internal scores stay private — serialize only public article payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from math import log
from typing import Dict, Iterable, List, Optional, Sequence, Set

from bot.taxonomy import competition_label
from entities import ArticleEntities, extract_entities
from sport_match import MAIN_SPORTS

# Generic competition weight, not club importance.
COMPETITION_WEIGHT = {
    "uefa-champions-league": 12,
    "fifa-world-cup": 12,
    "uefa-euro": 11,
    "nba": 10,
    "england-premier-league": 10,
    "uefa-europa-league": 8,
    "italy-serie-a": 8,
    "spain-la-liga": 8,
    "euroleague": 8,
    "formula-1": 8,
    "germany-bundesliga": 7,
    "france-ligue-1": 6,
    "uefa-conference-league": 5,
    "ncaa-basketball": 5,
}

HOMEPAGE_COMPETITIONS = (
    "uefa-champions-league",
    "england-premier-league",
    "italy-serie-a",
    "spain-la-liga",
    "nba",
    "euroleague",
)


@dataclass
class RankedStory:
    article: object
    resolution: object
    quality: dict
    entities: ArticleEntities
    score: float
    reasons: List[str] = field(default_factory=list)

    @property
    def id(self) -> int:
        return self.article.id

    @property
    def sport(self) -> Optional[str]:
        return getattr(self.resolution, "sport", None)

    @property
    def competition(self) -> Optional[str]:
        return getattr(self.resolution, "public_competition", None)

    @property
    def team_key(self) -> Optional[str]:
        teams = sorted(self.entities.teams)
        return teams[0] if teams else None


def _aware(stamp) -> datetime:
    """Normalize date/datetime/naive/aware values for ranking and recency."""
    if stamp is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if isinstance(stamp, datetime):
        if stamp.tzinfo is None:
            return stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    if isinstance(stamp, date):
        return datetime(stamp.year, stamp.month, stamp.day, tzinfo=timezone.utc)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _article_stamp(article) -> datetime:
    return _aware(getattr(article, "published_at", None) or getattr(article, "created_at", None))


def _hours_old(article) -> float:
    now = datetime.now(timezone.utc)
    return max(0.0, (now - _article_stamp(article)).total_seconds() / 3600.0)


def editorial_score(article, resolution, quality: dict, entities: ArticleEntities) -> RankedStory:
    reasons: List[str] = []
    score = 0.0
    hours = _hours_old(article)
    if hours < 6:
        score += 20
        reasons.append("fresh")
    elif hours < 24:
        score += 14
    elif hours < 72:
        score += 8
    elif hours < 168:
        score += 4
    else:
        score += 1

    words = int(quality.get("word_count") or 0)
    if words >= 120:
        score += 8
    elif words >= 60:
        score += 5
    elif words >= 40:
        score += 2

    if getattr(article, "image_url", None):
        score += 8
        reasons.append("image")
    if getattr(article, "is_breaking", False):
        score += 10
        reasons.append("breaking")
    views = int(getattr(article, "view_count", 0) or 0)
    if views > 0:
        score += min(12.0, log(views + 1) * 3.0)
    sport_conf = float(getattr(resolution, "sport_confidence", 0) or 0)
    comp_conf = float(getattr(resolution, "competition_confidence", 0) or 0)
    score += sport_conf * 4.0
    score += comp_conf * 3.0
    key = getattr(resolution, "public_competition", None)
    if key:
        score += COMPETITION_WEIGHT.get(key, 3)
    ranked = RankedStory(
        article=article,
        resolution=resolution,
        quality=quality,
        entities=entities,
        score=score,
        reasons=reasons,
    )
    return ranked


def _count_map(items: Iterable[RankedStory], attr: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        value = getattr(item, attr)
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def select_diverse(
    candidates: Sequence[RankedStory],
    limit: int,
    used: Set[int],
    *,
    max_per_team: int = 2,
    max_per_competition: int = 3,
    prefer_sport_mix: bool = True,
    require_image: bool = False,
) -> List[RankedStory]:
    """QUALITY > DIVERSITY > RECENCY. Never fills with weak stories."""
    ordered = sorted(candidates, key=lambda item: item.score, reverse=True)
    picked: List[RankedStory] = []
    remaining = [item for item in ordered if item.id not in used]
    if require_image:
        remaining = [
            item for item in remaining if getattr(item.article, "image_url", None)
        ]

    def try_take(item: RankedStory, relax: bool) -> bool:
        if item.id in used:
            return False
        teams = item.entities.teams
        team_counts = {}
        for chosen in picked:
            for team in chosen.entities.teams:
                team_counts[team] = team_counts.get(team, 0) + 1
        if not relax and teams:
            if any(team_counts.get(team, 0) >= max_per_team for team in teams):
                return False
        comp_counts = _count_map(picked, "competition")
        if (
            not relax
            and item.competition
            and comp_counts.get(item.competition, 0) >= max_per_competition
        ):
            return False
        if prefer_sport_mix and not relax and picked and limit >= 4:
            sport_counts = _count_map(picked, "sport")
            dominant = max(sport_counts.values()) if sport_counts else 0
            if item.sport and sport_counts.get(item.sport, 0) >= max(2, int(limit * 0.6)):
                # Leave room for another sport if one exists in remaining.
                others = [
                    row
                    for row in remaining
                    if row.id not in used
                    and row.sport
                    and row.sport != item.sport
                    and row.id != item.id
                ]
                if others:
                    return False
        picked.append(item)
        used.add(item.id)
        return True

    for item in remaining:
        if len(picked) >= limit:
            break
        try_take(item, relax=False)
    if len(picked) < limit:
        for item in remaining:
            if len(picked) >= limit:
                break
            try_take(item, relax=True)
    return picked


def take_unused(candidates: Sequence[RankedStory], limit: int, used: Set[int]) -> List[RankedStory]:
    out: List[RankedStory] = []
    for item in candidates:
        if item.id in used:
            continue
        out.append(item)
        used.add(item.id)
        if len(out) >= limit:
            break
    return out


def chronological(candidates: Sequence[RankedStory]) -> List[RankedStory]:
    return sorted(
        candidates,
        key=lambda item: _article_stamp(item.article),
        reverse=True,
    )


def most_read_truthful(
    candidates: Sequence[RankedStory],
    limit: int,
    hero_id: Optional[int],
) -> List[RankedStory]:
    ranked = [
        item
        for item in candidates
        if int(getattr(item.article, "view_count", 0) or 0) > 0
    ]
    ranked.sort(
        key=lambda item: (
            int(getattr(item.article, "view_count", 0) or 0),
            _article_stamp(item.article),
        ),
        reverse=True,
    )
    if hero_id is not None and any(item.id != hero_id for item in ranked):
        ranked = [item for item in ranked if item.id != hero_id]
    return ranked[:limit]


def sport_sections(
    candidates: Sequence[RankedStory],
    used_prominent: Set[int],
    limit: int,
) -> Dict[str, List[RankedStory]]:
    by_sport: Dict[str, List[RankedStory]] = {}
    for sport in MAIN_SPORTS:
        pool = chronological([item for item in candidates if item.sport == sport])
        unused = [item for item in pool if item.id not in used_prominent]
        chosen = unused[:limit]
        if not chosen:
            chosen = pool[:limit]
        if chosen:
            by_sport[sport] = chosen
    return by_sport


def competition_modules(
    candidates: Sequence[RankedStory],
    used_prominent: Set[int],
    min_count: int,
    limit_per: int = 4,
    max_modules: int = 4,
) -> List[dict]:
    modules = []
    for key in HOMEPAGE_COMPETITIONS:
        pool = [
            item
            for item in chronological(candidates)
            if item.competition == key and item.id not in used_prominent
        ]
        if len(pool) < min_count:
            continue
        rows = pool[:limit_per]
        sport = rows[0].sport
        modules.append(
            {
                "league": key,
                "label": competition_label(key),
                "sport": sport,
                "count": len(pool),
                "stories": rows,
            }
        )
        if len(modules) >= max_modules:
            break
    return modules
