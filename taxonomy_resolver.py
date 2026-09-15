"""Deterministic public taxonomy resolver.

Stored article.sport / article.league are weak signals, never proof.
Does not write source article rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bot.taxonomy import (
    COMPETITIONS,
    DIRECTORY_SPORT_SLUGS,
    SPORT_ALIASES,
    TEAMS,
    canonical_competition_key,
    compatible_competition,
    competition_sport,
)
from editorial import sanitize_body, sanitize_summary, sanitize_title
from sport_match import EXCLUSIVE_KEYWORDS, MAIN_SPORTS

RESOLVER_VERSION = "4.4.1"
MIN_COMPETITION_CONFIDENCE = 0.72
MIN_SPORT_CONFIDENCE = 0.72
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
    "pistons",
    "kawhi",
    "lebron",
)

# Club names that exist in more than one sport. Never treat them as exclusive.
AMBIGUOUS_CLUBS = (
    "barcelona",
    "barca",
    "real madrid",
    "partizan",
    "crvena zvezda",
    "red star",
)

SPORT_TERMS = {
    "football": (
        "goalkeeper",
        "striker",
        "midfielder",
        "centre back",
        "center back",
        "clean sheet",
        "transfer window",
        "offside",
        "premier league",
        "champions league",
        "serie a",
        "la liga",
        "bundesliga",
        "ligue 1",
        "hat trick",
        "hat-trick",
        "own goal",
        "penalty kick",
        " efl ",
        "league one",
        "league two",
    ),
    "basketball": (
        "rebounds",
        "assists",
        "field goal",
        "three-pointer",
        "three pointer",
        "free throw",
        "point guard",
        "shooting guard",
        "power forward",
        "small forward",
        "euroleague",
        "wnba",
        "ncaa basketball",
        "basquet",
        "bàsquet",
        "box score",
        "shot clock",
        "the paint",
        "triple-double",
        "alley-oop",
        "qualifying offer",
        "exhibit 10",
        "training camp roster",
    ),
    "tennis": (
        "set point",
        "double fault",
        "first serve",
        "break point",
        "match point",
        "grand slam",
        "tiebreak",
        "tie-break",
    ),
    "motorsport": (
        "formula 1",
        "formula one",
        "pole position",
        "pit stop",
        "constructor",
        "motogp",
        "qualifying lap",
        "qualifying session",
        "grid penalty",
        " f1 ",
    ),
}

GOLF_MARKERS = (
    " golf ",
    " pga ",
    "birdie",
    "bogey",
    "fairway",
    "augusta",
    "pinehurst",
    "oakmont",
    "masters tournament",
    "golf tournament",
    "golf club",
    "golf tours",
)
GOLF_OPENS = ("us open", "australian open", "the open")
TABLE_TENNIS_MARKERS = ("table tennis", " wtt ", "ittf")
WIMBLEDON_FOOTBALL_MARKERS = (" efl ", " league one ", " league two ", " afc wimbledon ")

EUROLEAGUE_MARKERS = ("euroleague", "euroliga", "evroliga")

DISCOUNT_PATTERNS = (
    "regardless of {alias}",
    "not the {alias}",
    "outside the {alias}",
)

# Publisher chrome / section nav labels. These may appear in related-link
# blocks and must never decide sport from summary or body alone.
CHROME_NAV_ALIASES = {
    "football": (
        "football",
        "soccer",
        "premier league",
        "champions league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "europa league",
        "world cup",
    ),
    "tennis": (
        "tennis",
        "tenis",
        "wimbledon",
        "roland garros",
        "us open",
        "australian open",
        "atp",
        "wta",
        "grand slam",
    ),
    "basketball": (
        "basketball",
        "nba",
        "euroleague",
        "ncaa",
        "wnba",
    ),
    "motorsport": (
        "formula 1",
        "formula one",
        "f1",
        "motogp",
        "motorsport",
        "grand prix",
    ),
    "golf": ("golf", "pga"),
    "cricket": ("cricket",),
    "rugby": ("rugby",),
    "ice-hockey": ("hockey", "nhl", "ice hockey"),
    "american-football": ("nfl", "american football"),
    "baseball": ("baseball", "mlb"),
}

SCORED_SPORTS = tuple(
    dict.fromkeys((*MAIN_SPORTS, *DIRECTORY_SPORT_SLUGS, *SPORT_ALIASES.keys()))
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


def _is_chrome_alias(sport: str, alias: str) -> bool:
    needle = alias.strip().lower()
    return needle in {item.strip().lower() for item in CHROME_NAV_ALIASES.get(sport, ())}


def _field_weight(sport: str, alias: str, field: str) -> float:
    if field == "title":
        return 4.0 if not _is_chrome_alias(sport, alias) else 3.2
    if _is_chrome_alias(sport, alias):
        return 0.0
    if field == "summary":
        return 0.35
    return 0.15


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
        nav_like = any(_is_chrome_alias(meta.get("sport") or "", alias) for alias in aliases)
        if sport:
            summary_weight = 2.0
            body_weight = 0.0 if nav_like else 0.8
        else:
            summary_weight = 0.15 if nav_like else 2.0
            body_weight = 0.0
        value = title_hits * 4.0 + summary_hits * summary_weight + body_hits * body_weight
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


def _term_hits(blob: str, terms: Sequence[str]) -> float:
    score = 0.0
    for term in terms:
        needle = term if term.startswith(" ") or term.endswith(" ") else f" {term.strip()} "
        if needle in blob:
            score += max(2.0, len(term.strip().split()) * 1.5)
    return score


def _exclusive_aliases(sport: str) -> Tuple[str, ...]:
    blocked = {item.strip() for item in AMBIGUOUS_CLUBS}
    return tuple(
        alias
        for alias in EXCLUSIVE_KEYWORDS.get(sport, ())
        if alias.strip() not in blocked
    )


def _score_sports(title: str, summary: str, body: str) -> Dict[str, float]:
    title_blob = _norm(title)
    summary_blob = _norm(summary)
    body_blob = _norm(body)
    scores = {sport: 0.0 for sport in SCORED_SPORTS}

    for sport in SCORED_SPORTS:
        for alias in _exclusive_aliases(sport):
            padded = alias if alias.startswith(" ") else f" {alias.strip()} "
            if padded in title_blob:
                scores[sport] += max(2.0, len(alias.strip().split())) * _field_weight(sport, alias, "title")
            elif padded in summary_blob:
                scores[sport] += max(2.0, len(alias.strip().split())) * _field_weight(sport, alias, "summary")
            elif padded in body_blob:
                scores[sport] += max(2.0, len(alias.strip().split())) * _field_weight(sport, alias, "body")
        scores[sport] += _term_hits(title_blob, SPORT_TERMS.get(sport, ())) * 4.0
        scores[sport] += _term_hits(summary_blob, SPORT_TERMS.get(sport, ())) * 0.4
        scores[sport] += _term_hits(body_blob, SPORT_TERMS.get(sport, ())) * 0.2
        scores[sport] += _alias_hits(title_blob, SPORT_ALIASES.get(sport, [])) * 3.0
        chrome_aliases = [alias for alias in SPORT_ALIASES.get(sport, []) if _is_chrome_alias(sport, alias)]
        content_aliases = [alias for alias in SPORT_ALIASES.get(sport, []) if not _is_chrome_alias(sport, alias)]
        scores[sport] += _alias_hits(summary_blob, content_aliases) * 0.5
        scores[sport] += _alias_hits(body_blob, content_aliases) * 0.2
        # Chrome aliases in summary/body are ignored unless the title already supports the sport.
        if scores[sport] >= 4:
            scores[sport] += _alias_hits(summary_blob, chrome_aliases) * 0.15
            scores[sport] += _alias_hits(body_blob, chrome_aliases) * 0.05

    combined = _norm(f"{title} {summary} {body}")
    title_only = title_blob
    for team in TEAMS:
        team_sport = team.get("sport")
        if team_sport not in scores:
            continue
        title_hit = _alias_hits(title_only, team.get("aliases") or [])
        body_hit = _alias_hits(combined, team.get("aliases") or [])
        hit = title_hit * 2.8 + (0.0 if not title_hit else body_hit * 0.4)
        if not title_hit:
            # Teams mentioned only in related-link chrome must not decide sport.
            continue
        if team.get("ambiguous_sport"):
            if scores[team_sport] < 4:
                continue
            scores[team_sport] += hit * 0.6
        else:
            scores[team_sport] += hit

    if any(marker in combined for marker in GOLF_MARKERS) and any(name in combined for name in GOLF_OPENS):
        scores["tennis"] = min(scores.get("tennis", 0.0), 1.0)
        if " golf " in title_blob or " pga " in title_blob or "golf tournament" in combined or "golf club" in combined:
            scores["golf"] = scores.get("golf", 0.0) + 8.0
    if any(marker in combined for marker in TABLE_TENNIS_MARKERS):
        scores["tennis"] = min(scores.get("tennis", 0.0), 1.0)
    if " wimbledon " in combined and any(marker in combined for marker in WIMBLEDON_FOOTBALL_MARKERS):
        scores["football"] = scores.get("football", 0.0) + 8.0
        scores["tennis"] = min(scores.get("tennis", 0.0), 1.0)
    if "qualifying offer" in combined or "exhibit 10" in combined:
        scores["basketball"] += 8.0
        scores["motorsport"] = max(0.0, scores.get("motorsport", 0.0) - 8.0)
    if any(marker in combined for marker in ("qualifying session", "qualifying lap", "pole position")):
        scores["motorsport"] += 8.0
    elif " qualifying " in combined and scores.get("motorsport", 0.0) < 6 and scores.get("basketball", 0.0) < 6:
        scores["motorsport"] = max(0.0, scores.get("motorsport", 0.0) - 4.0)
    if any(marker in combined for marker in EUROLEAGUE_MARKERS):
        scores["basketball"] += 8.0
        if " nba " not in title_blob:
            scores["basketball"] += 2.0
    if any(token in title_blob for token in NBA_FRANCHISE) and "euroleague" not in combined:
        scores["basketball"] += 6.0

    # Ambiguous clubs never decide sport by themselves.
    for club in AMBIGUOUS_CLUBS:
        if f" {club} " in title_blob and max(scores.values() or [0]) < 6:
            for sport in SCORED_SPORTS:
                scores[sport] = max(0.0, scores[sport] - 1.0)
    return scores


def _resolve_sport(
    title: str,
    summary: str,
    body: str,
    stored: Optional[str],
) -> Tuple[Optional[str], float, List[str]]:
    scores = _score_sports(title, summary, body)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_sport, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    evidence = [f"sport-score:{best_sport}:{best:.1f}"]
    if second > 0 and best < second * 1.15:
        return None, 0.0, evidence + ["contradictory-sport"]
    if best >= 10 and best >= second * 1.2:
        return best_sport, min(0.97, 0.78 + best / 80.0), evidence + ["strong-context"]
    if best >= 6 and best > second:
        return best_sport, min(0.9, 0.72 + best / 90.0), evidence + ["context"]
    if best >= 4 and best > second * 1.25:
        return best_sport, 0.74, evidence + ["narrow-context"]
    # Stored metadata and feed buckets are never proof.
    if stored:
        evidence.append("stored-sport-ignored")
    return None, 0.0, evidence + ["unknown-sport"]


def resolve_article_competition(article) -> TaxonomyResolution:
    title, summary, body = _blob_parts(article)
    stored_sport = getattr(article, "sport", None)
    stored_league = canonical_competition_key(getattr(article, "league", None))
    sport, sport_conf, sport_evidence = _resolve_sport(title, summary, body, stored_sport)
    if not sport:
        return TaxonomyResolution(
            sport=None,
            competition=None,
            sport_confidence=0.0,
            competition_confidence=0.0,
            evidence=sport_evidence + ["no-sport-no-competition"],
        )
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
        kept = compatible_competition(sport, competition)
        if kept != competition:
            competition, comp_conf = None, 0.0
            comp_evidence = ["competition-sport-mismatch"]
        else:
            owner = competition_sport(competition)
            if owner and owner != sport:
                competition, comp_conf = None, 0.0
                comp_evidence = ["competition-sport-mismatch"]

    if source == "body" and competition and not _competition_scores(title_blob, "", "", sport):
        # Body-only competition hits are too often related-story chrome.
        competition, comp_conf = None, 0.0
        comp_evidence = ["body-only-competition-ignored"]

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
