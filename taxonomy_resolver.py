"""Deterministic public taxonomy resolver.

Stored article.sport / article.league are weak signals, never proof.
Does not write source article rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bot.taxonomy import COMPETITIONS, SPORT_ALIASES, canonical_competition_key
from editorial import sanitize_body, sanitize_summary, sanitize_title
from sport_match import EXCLUSIVE_KEYWORDS, MAIN_SPORTS, exclusive_score

RESOLVER_VERSION = "4.1.2"
MIN_COMPETITION_CONFIDENCE = 0.72
BODY_EXCERPT_CHARS = 1400
SUMMARY_CHARS = 600

CONTINENTAL = {
    "uefa-champions-league",
    "uefa-europa-league",
    "uefa-conference-league",
    "fifa-world-cup",
    "uefa-euro",
}

BROAD_BUCKETS = {
    "football-international",
    "basketball-international",
    "tennis-international",
    "motorsport-international",
}

NBA_FRANCHISE = (
    "lakers",
    "76ers",
    "sixers",
    "celtics",
    "knicks",
    "raptors",
    "grizzlies",
    "clippers",
    "warriors",
    "nuggets",
    "bucks",
    "mavericks",
    "heat",
    "thunder",
    "pelicans",
    "timberwolves",
    "kawhi",
    "lebron",
)

DISCOUNT_PATTERNS = (
    "regardless of {alias}",
    "not the {alias}",
    "outside the {alias}",
)


@dataclass
class TaxonomyResolution:
    sport: Optional[str]
    competition: Optional[str]
    sport_confidence: float
    competition_confidence: float
    evidence: List[str] = field(default_factory=list)
    resolver_version: str = RESOLVER_VERSION

    @property
    def public_competition(self) -> Optional[str]:
        if not self.competition or self.competition_confidence < MIN_COMPETITION_CONFIDENCE:
            return None
        if self.competition in BROAD_BUCKETS:
            return None
        return self.competition


def _norm(text: str) -> str:
    lowered = (text or "").lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return f" {' '.join(cleaned.split())} "


def _blob_parts(article) -> Tuple[str, str, str]:
    title = sanitize_title(getattr(article, "title", "") or "")
    summary = sanitize_summary(getattr(article, "summary", "") or "", title=title)[:SUMMARY_CHARS]
    raw_body = getattr(article, "ai_content", None) or getattr(article, "content", None) or ""
    body = sanitize_body(raw_body, title=title)[:BODY_EXCERPT_CHARS]
    return title, summary, body


def _alias_hits(blob: str, aliases: Sequence[str]) -> int:
    score = 0
    for alias in aliases:
        needle = _norm(alias).strip()
        if not needle or len(needle) < 2:
            continue
        padded = f" {needle} "
        if padded not in blob:
            continue
        discounted = any(
            _norm(pattern.format(alias=needle)).strip() in blob
            for pattern in DISCOUNT_PATTERNS
        )
        if discounted:
            continue
        score += max(2, len(needle.split()))
    return score


def _competition_scores(title_blob: str, summary_blob: str, body_blob: str, sport: Optional[str]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for slug, meta in COMPETITIONS.items():
        if slug in BROAD_BUCKETS:
            continue
        if sport and meta.get("sport") != sport:
            continue
        aliases = meta.get("aliases") or []
        title_hits = _alias_hits(title_blob, aliases)
        summary_hits = _alias_hits(summary_blob, aliases)
        body_hits = _alias_hits(body_blob, aliases)
        value = title_hits * 4.0 + summary_hits * 2.0 + body_hits * 0.8
        if value:
            scores[slug] = value
            if slug in CONTINENTAL and title_hits:
                scores[slug] += 6.0
    return scores


def _pick_competition(scores: Dict[str, float]) -> Tuple[Optional[str], float, List[str]]:
    if not scores:
        return None, 0.0, []
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_slug, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    evidence = [f"competition:{best_slug}:{best:.1f}"]
    if best_slug in CONTINENTAL:
        domestic = [slug for slug, _ in ordered[1:4] if slug not in CONTINENTAL]
        if domestic:
            evidence.append("continental-outranks-domestic")
    if second > 0 and best < second * 1.15 and best_slug not in CONTINENTAL:
        return None, 0.0, ["ambiguous-competition"]
    if best >= 8:
        return best_slug, min(0.97, 0.72 + best / 40.0), evidence
    if best >= 4:
        return best_slug, min(0.88, 0.72 + best / 50.0), evidence
    return None, 0.0, ["weak-competition"]


def _resolve_sport(title: str, stored: Optional[str]) -> Tuple[Optional[str], float, List[str]]:
    title_blob = title
    own_scores = {sport: exclusive_score(title_blob, sport) for sport in EXCLUSIVE_KEYWORDS}
    best_sport = max(own_scores, key=own_scores.get)
    best = own_scores[best_sport]
    ranked = sorted(own_scores.values(), reverse=True)
    second = ranked[1] if len(ranked) > 1 else 0
    if best >= 2 and best > second:
        return best_sport, 0.94, [f"title-sport:{best_sport}"]
    alias_scores = {}
    blob = _norm(title_blob)
    for sport, aliases in SPORT_ALIASES.items():
        alias_scores[sport] = _alias_hits(blob, aliases)
    if alias_scores:
        alias_best = max(alias_scores, key=alias_scores.get)
        if alias_scores[alias_best] >= 2:
            others = [score for key, score in alias_scores.items() if key != alias_best]
            if alias_scores[alias_best] > (max(others) if others else 0):
                return alias_best, 0.86, [f"alias-sport:{alias_best}"]
    if stored in MAIN_SPORTS and best == 0 and second == 0:
        return stored, 0.55, ["stored-sport-signal"]
    if stored and stored not in MAIN_SPORTS:
        return stored, 0.5, ["stored-other-sport"]
    return None, 0.0, ["unknown-sport"]


def resolve_article_competition(article) -> TaxonomyResolution:
    title, summary, body = _blob_parts(article)
    stored_sport = getattr(article, "sport", None)
    stored_league = canonical_competition_key(getattr(article, "league", None))
    sport, sport_conf, sport_evidence = _resolve_sport(title, stored_sport)
    title_blob = _norm(title)
    summary_blob = _norm(summary)
    body_blob = _norm(body)
    title_scores = _competition_scores(title_blob, "", "", sport)
    if title_scores:
        scores = title_scores
        source = "title"
    else:
        summary_scores = _competition_scores(title_blob, summary_blob, "", sport)
        if summary_scores:
            scores = summary_scores
            source = "summary"
        else:
            scores = _competition_scores(title_blob, summary_blob, body_blob, sport)
            source = "body"
    competition, comp_conf, comp_evidence = _pick_competition(scores)
    if source:
        comp_evidence = [f"source:{source}"] + comp_evidence

    if competition and sport:
        meta = COMPETITIONS.get(competition)
        if meta and meta.get("sport") != sport:
            competition, comp_conf = None, 0.0
            comp_evidence = ["competition-sport-mismatch"]

    if (
        sport == "basketball"
        and not competition
        and any(token in title_blob for token in NBA_FRANCHISE)
        and "euroleague" not in title_blob
        and "ncaa" not in title_blob
    ):
        competition = "nba"
        comp_conf = 0.8
        comp_evidence = ["nba-franchise-context"]

    if sport == "motorsport" and not competition:
        if "grand prix" in title.lower() and (" f1 " in title_blob or "formula" in title_blob):
            competition = "formula-1"
            comp_conf = 0.9
            comp_evidence = ["f1-grand-prix"]

    # Stored league is a last-resort signal only when nothing explicit exists.
    if not competition and stored_league and stored_league not in BROAD_BUCKETS:
        stored_meta = COMPETITIONS.get(stored_league)
        if stored_meta and (not sport or stored_meta.get("sport") == sport) and sport_conf >= 0.86:
            # Still not enough: do not promote stored league to a public competition.
            comp_evidence.append("stored-league-ignored")

    evidence = sport_evidence + comp_evidence
    return TaxonomyResolution(
        sport=sport,
        competition=competition if comp_conf >= MIN_COMPETITION_CONFIDENCE else None,
        sport_confidence=sport_conf,
        competition_confidence=comp_conf if competition and comp_conf >= MIN_COMPETITION_CONFIDENCE else 0.0,
        evidence=evidence,
    )


def title_like_terms(competition_key: str) -> List[str]:
    meta = COMPETITIONS.get(competition_key) or {}
    terms = []
    for alias in meta.get("aliases") or []:
        cleaned = alias.strip()
        if len(cleaned) >= 3:
            terms.append(cleaned)
    label = meta.get("label")
    if label:
        terms.append(label)
    return terms[:8]


def cache_row_to_resolution(row) -> TaxonomyResolution:
    return TaxonomyResolution(
        sport=row.resolved_sport,
        competition=row.resolved_competition,
        sport_confidence=float(row.sport_confidence or 0),
        competition_confidence=float(row.competition_confidence or 0),
        evidence=["cache"],
        resolver_version=row.resolver_version,
    )


def persist_resolution(db, article, resolution: TaxonomyResolution):
    from datetime import datetime

    from models import ArticleTaxonomyResolution

    if not getattr(article, "id", None):
        return resolution
    row = (
        db.query(ArticleTaxonomyResolution)
        .filter(ArticleTaxonomyResolution.article_id == article.id)
        .first()
    )
    if row is None:
        row = ArticleTaxonomyResolution(article_id=article.id)
        db.add(row)
    row.resolved_sport = resolution.sport
    row.resolved_competition = resolution.public_competition
    row.sport_confidence = f"{resolution.sport_confidence:.3f}"
    row.competition_confidence = f"{resolution.competition_confidence:.3f}"
    row.resolver_version = RESOLVER_VERSION
    row.resolved_at = datetime.utcnow()
    return resolution


def resolve_many(db, articles: Sequence) -> Dict[int, TaxonomyResolution]:
    from models import ArticleTaxonomyResolution

    out: Dict[int, TaxonomyResolution] = {}
    if not articles:
        return out
    ids = [article.id for article in articles if getattr(article, "id", None)]
    cached = {}
    if ids:
        rows = (
            db.query(ArticleTaxonomyResolution)
            .filter(
                ArticleTaxonomyResolution.article_id.in_(ids),
                ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            )
            .all()
        )
        cached = {row.article_id: cache_row_to_resolution(row) for row in rows}
    dirty = False
    for article in articles:
        article_id = getattr(article, "id", None)
        if article_id in cached:
            out[article_id] = cached[article_id]
            continue
        resolution = resolve_article_competition(article)
        if article_id:
            persist_resolution(db, article, resolution)
            dirty = True
            out[article_id] = resolution
        else:
            out[id(article)] = resolution
    if dirty:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return out
