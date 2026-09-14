"""Related-story relevance. Same resolved sport is required, not sufficient."""

from __future__ import annotations

from typing import List, Optional, Sequence

from entities import extract_entities, shared_count
from homepage_compose import _hours_old

MIN_RELATED_SCORE = 18.0


def related_score(source_article, source_resolution, candidate_article, candidate_resolution) -> float:
    if not source_resolution or not candidate_resolution:
        return 0.0
    if source_resolution.sport != candidate_resolution.sport:
        return 0.0
    if not source_resolution.sport:
        return 0.0
    source = extract_entities(source_article.title, getattr(source_article, "summary", None))
    other = extract_entities(candidate_article.title, getattr(candidate_article, "summary", None))
    score = 0.0
    if (
        source_resolution.public_competition
        and source_resolution.public_competition == candidate_resolution.public_competition
    ):
        score += 40.0
    teams = shared_count(source.teams, other.teams)
    people = shared_count(source.people, other.people)
    score += min(36.0, teams * 28.0)
    score += min(16.0, people * 12.0)
    tokens = shared_count(source.tokens, other.tokens)
    score += min(14.0, tokens * 3.0)
    hours = _hours_old(candidate_article)
    if hours < 24:
        score += 6.0
    elif hours < 72:
        score += 3.0
    return score


def rank_related(
    source_article,
    source_resolution,
    candidates: Sequence,
    resolutions: dict,
    quality_ok,
    isolation_ok,
    limit: int,
) -> List:
    scored = []
    for row in candidates:
        if row.id == source_article.id:
            continue
        other = resolutions.get(row.id)
        if not other or other.sport != source_resolution.sport:
            continue
        if not quality_ok(row):
            continue
        if not isolation_ok(row, source_resolution.sport, strict=True):
            continue
        value = related_score(source_article, source_resolution, row, other)
        if value < MIN_RELATED_SCORE:
            continue
        scored.append((value, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:limit]]
