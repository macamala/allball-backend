"""Persist public-ready article eligibility at ingest/backfill time.

Public GET handlers must read these rows, not reclassify or re-score bodies.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Sequence
from urllib.parse import urlsplit

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from editorial import classify_media_url, evaluate_quality, news_image_is_publishable
from bot.news_image_http import score_news_image_candidate
from bot.feeds import news_source_is_excluded
from models import Article, ArticleTaxonomyResolution
from sport_match import MAIN_SPORTS, isolation_ok
from bot.taxonomy import COMPETITIONS
from bot.news_learning import article_has_open_incident
from bot.news_policy import CRICKET_TITLE_RE, VOLLEYBALL_TITLE_RE, RUGBY_LEAGUE_TITLE_RE, RUGBY_UNION_TITLE_RE, gossip_news_reason, non_article_news_reason, publisher_branding_reason, source_path_conflict_reason
from taxonomy_resolver import (
    MIN_SPORT_CONFIDENCE,
    RESOLVER_VERSION,
    persist_resolution,
    resolve_article_competition,
    TaxonomyResolution,
    cache_row_to_resolution,
)

logger = logging.getLogger("ninkosports.public_index")
_NEWS_CLOCK_REPORTED = False


def persist_public_article(db: Session, article: Article, resolution=None, commit: bool = False):
    """Classify once, store taxonomy + quality + public eligibility."""
    resolved = resolution or resolve_article_competition(article)
    persist_resolution(db, article, resolved)
    db.flush()
    article.sport = resolved.sport
    article.league = resolved.public_competition
    if resolved.public_competition:
        meta = COMPETITIONS.get(resolved.public_competition) or {}
        if meta.get("country"):
            article.country = meta.get("country")
    db.add(article)
    media_kind = classify_media_url(article.image_url)
    if media_kind in {"CREST_OR_LOGO", "GRAPHIC"}:
        article.image_url = None
        media_kind = "MISSING"
        db.add(article)
    quality = evaluate_quality(
        title=article.title,
        summary=article.summary,
        body=article.ai_content or article.content or article.summary,
        image_url=article.image_url,
    )
    isolated = True
    if resolved.sport in MAIN_SPORTS:
        isolated = isolation_ok(
            article, resolved.sport, strict=True, resolution=resolved
        )
    admission_item = {
        "title": article.title,
        "summary": article.summary,
        "body": article.ai_content or article.content or "",
        "url": article.source_url,
    }
    editorial_hold = (gossip_news_reason(admission_item) or non_article_news_reason(admission_item)
                      or publisher_branding_reason(admission_item)
                      or source_path_conflict_reason(admission_item, resolved.sport))
    public = bool(
        quality.get("ok")
        and resolved.sport
        and resolved.sport_confidence >= MIN_SPORT_CONFIDENCE
        and isolated
        and news_image_is_publishable(article.image_url)
        and not editorial_hold
        and not article_has_open_incident(db, article.id)
    )
    if editorial_hold:
        logger.warning(
            "[public_index] hold gossip article=%s reason=%s title=%s",
            getattr(article, "id", None),
            editorial_hold,
            (article.title or "")[:120],
        )
    row = (
        db.query(ArticleTaxonomyResolution)
        .filter(ArticleTaxonomyResolution.article_id == article.id)
        .first()
    )
    if row is None:
        return resolved
    row.quality_ok = bool(quality.get("ok"))
    row.public_ok = public
    row.hero_media_kind = media_kind
    row.word_count = int(quality.get("word_count") or 0)
    db.add(row)
    if commit:
        db.commit()
    return resolved


def index_missing(db: Session, limit: int = 400) -> int:
    """Backfill articles that lack a current public index row. Never called from GET."""
    missing = (
        db.query(Article)
        .outerjoin(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            (ArticleTaxonomyResolution.id.is_(None))
            | (ArticleTaxonomyResolution.resolver_version != RESOLVER_VERSION)
            | (ArticleTaxonomyResolution.hero_media_kind.is_(None))
            | (Article.image_url.ilike("%/images/ic/%"))
        )
        .order_by(Article.id.desc())
        .limit(limit)
        .all()
    )
    counted = 0
    for article in missing:
        persist_public_article(db, article)
        counted += 1
    if counted:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("public index backfill failed")
            return 0
    return counted


def repair_recent_unresolved(db: Session, limit: int = 24) -> int:
    """Re-evaluate only recent AI articles already held from public News by taxonomy.

    This is bounded, zero-AI and never rewrites article copy. It exists so a
    newly added safe sport marker can rescue recent valid stories without
    enabling historical mass repair.
    """
    rows = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            Article.ai_generated.is_(True),
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(False),
            Article.image_url.isnot(None),
            Article.image_url != "",
        )
        .order_by(Article.id.desc())
        .limit(max(1, min(int(limit), 50)))
        .all()
    )
    repaired = 0
    attempted = 0
    for article, cached in rows:
        # Resolve in memory first. Most held rows remain unresolved; do not spend
        # multiple round-trips re-persisting a result that still cannot publish.
        resolved = resolve_article_competition(article)
        if (
            not resolved.sport
            or resolved.sport_confidence < MIN_SPORT_CONFIDENCE
            or not news_image_is_publishable(article.image_url)
        ):
            continue
        attempted += 1
        persist_public_article(db, article, resolved, commit=False)
        if cached.public_ok:
            repaired += 1
    if rows:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent unresolved News repair failed")
            return 0
    if repaired or attempted:
        logger.info(
            "[public_index] unresolved repair candidates=%s repaired=%s scanned=%s",
            attempted,
            repaired,
            len(rows),
        )
    return repaired


def load_cached_resolution(db: Session, article: Article):
    if not getattr(article, "id", None):
        return None
    return (
        db.query(ArticleTaxonomyResolution)
        .filter(
            ArticleTaxonomyResolution.article_id == article.id,
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        )
        .first()
    )


def load_cached_resolutions(db: Session, articles: Sequence[Article]) -> dict:
    ids = [article.id for article in articles if getattr(article, "id", None)]
    if not ids:
        return {}
    rows = (
        db.query(ArticleTaxonomyResolution)
        .filter(
            ArticleTaxonomyResolution.article_id.in_(ids),
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        )
        .all()
    )
    return {row.article_id: row for row in rows}



def recent_public_sport_inventory(db: Session, max_age_hours: int = 72, *, editorial_timezone=None, now=None) -> dict[str, int]:
    """Counts the same current, image-valid News inventory readers can browse."""
    global _NEWS_CLOCK_REPORTED
    if not _NEWS_CLOCK_REPORTED and db.get_bind().dialect.name == 'postgresql':
        try:
            with db.begin_nested():
                column = db.execute(text("SELECT data_type, datetime_precision FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='articles' AND column_name='published_at'")).first()
            logger.info('[public_index] news_publication_clock_storage=%s', tuple(column) if column else 'unknown')
            _NEWS_CLOCK_REPORTED = True
        except Exception as exc:
            logger.warning('[public_index] news clock storage diagnostic unavailable: %s', type(exc).__name__)
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("inventory clock must be timezone-aware")
    end = clock.astimezone(timezone.utc).replace(tzinfo=None)
    if editorial_timezone:
        local = clock.astimezone(ZoneInfo(editorial_timezone))
        cutoff = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    else:
        cutoff = end - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution.resolved_sport,
            func.count(ArticleTaxonomyResolution.id),
        )
        .join(Article, Article.id == ArticleTaxonomyResolution.article_id)
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            ArticleTaxonomyResolution.resolved_sport.isnot(None),
            ArticleTaxonomyResolution.hero_media_kind.in_(("EDITORIAL_PHOTO", "UNKNOWN")),
            Article.image_url.isnot(None),
            Article.image_url != "",
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
            func.coalesce(Article.published_at, Article.created_at) <= end,
        )
        .group_by(ArticleTaxonomyResolution.resolved_sport)
        .all()
    )
    return {str(sport): int(count or 0) for sport, count in rows if sport}



def _legacy_non_news_source_url(url: str) -> bool:
    """Never resurrect historical score-derived rows as News."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    path = (parts.path or "").lower()
    return host in {"ninkosports.com", "www.ninkosports.com"} and path.startswith("/live-scores")


def _reachable_source_image(
    source_url: str,
    *,
    current_url: Optional[str] = None,
    max_checks: int = 6,
    include_current: bool = False,
) -> Optional[str]:
    """Pick a reachable editorial image from one canonical source page."""
    from bot.extract import extract_image_candidates_from_url
    from bot.news_image_http import news_image_is_reachable, news_hero_url

    if _legacy_non_news_source_url(source_url) or news_source_is_excluded(source_url):
        return None

    # Repair a verified same-photo hero size before fetching a whole source page.
    # The stored thumbnail is never approved merely because a variant exists.
    upgraded = news_hero_url(current_url or "")
    if (not include_current and upgraded and upgraded != current_url and news_image_is_publishable(upgraded)
            and news_image_is_reachable(upgraded)):
        return upgraded

    try:
        candidates = extract_image_candidates_from_url(source_url, timeout=12.0)
    except Exception:
        candidates = []

    ranked = []
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = news_hero_url(str(candidate.get("url") or "").strip())
        if (
            not url
            or url in seen
            or (not include_current and url == str(current_url or "").strip())
            or len(url) > 500
            or not news_image_is_publishable(url)
        ):
            continue
        score = score_news_image_candidate(candidate)
        if score < 0:
            continue
        seen.add(url)
        ranked.append((score, url))
    ranked.sort(key=lambda row: row[0], reverse=True)

    for _score, url in ranked[: max(1, int(max_checks))]:
        if news_image_is_reachable(url):
            return url
    return None


def _image_repair_resolution(article, cached):
    """An image change must not discard source-backed ingest taxonomy."""
    resolved = resolve_article_competition(article)
    if (cached and cached.resolver_version == RESOLVER_VERSION
            and cached.resolved_sport
            and float(cached.sport_confidence or 0) >= MIN_SPORT_CONFIDENCE
            and (not resolved.sport or resolved.sport == cached.resolved_sport)):
        return cache_row_to_resolution(cached)
    # Recover UEFA football source evidence lost by older image-only repair.
    # The football competition path is explicit; UEFA futsal never matches.
    parts = urlsplit(str(article.source_url or ""))
    if (not resolved.sport and parts.hostname == "www.uefa.com"
            and parts.path.startswith(("/uefachampionsleague/news/", "/uefaeuropaleague/news/",
                                       "/uefaconferenceleague/news/", "/uefanationsleague/news/",
                                       "/womenschampionsleague/news/", "/european-qualifiers/news/"))
            and re.search(r"\b(?:UEFA|Champions League|Europa League|Conference League|Nations League)\b", article.title or "", re.I)):
        return TaxonomyResolution(sport="football", competition=None,
            sport_confidence=0.99, competition_confidence=0,
            evidence=["verified-uefa-football-article-path"])
    return resolved


_SOURCE_IMAGE_CHECKED = {}


def repair_recent_news_images(
    db: Session,
    *,
    limit: int = 80,
    max_age_hours: int = 72,
    recover_limit: int = 8,
) -> int:
    """Verify recent public hero URLs and recover fresh images without AI.

    A syntactically plausible image URL is not enough: it must actually serve
    image bytes. Broken public heroes are refreshed from the canonical source
    page when possible; otherwise the row is held until a future recovery finds
    a working image.
    """
    from collections import Counter

    from bot.news_image_http import probe_news_images

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            Article.image_url.isnot(None),
            Article.image_url != "",
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 160)))
        .all()
    )

    probes = probe_news_images(
        [article.image_url for article, _tax in rows
         if article.image_url and news_image_is_publishable(article.image_url)],
        max_workers=6,
    )
    # Reachable bytes do not make a logo/title card an editorial photograph.
    # Apply the same type gate as ingestion before restoring public visibility.
    probes.update({article.image_url: (False, 'non_editorial_hero')
                   for article, _tax in rows
                   if not news_image_is_publishable(article.image_url)})
    definitive_reasons = {
        "non_editorial_hero",
        "invalid_or_nonpublic_url",
        "redirect_without_location",
        "redirect_limit",
        "not_image_content",
        "empty_image_response",
        "http_400",
        "http_401",
        "http_403",
        "http_404",
        "http_410",
        "http_451",
        "bad_aspect_ratio",
        "image_too_small",
        "image_dimensions_unverified",
        "composited_overlay",
        "promotional_banner",
        "publisher_default_image",
    }
    failed = [
        (article, tax, probes.get(str(article.image_url or "").strip(), (False, "probe_missing"))[1])
        for article, tax in rows
        if not probes.get(str(article.image_url or "").strip(), (False, "probe_missing"))[0]
    ]
    broken = [row for row in failed if row[2] in definitive_reasons]
    reasons = Counter(reason for _article, _tax, reason in failed)
    refreshed = 0
    hidden = 0
    touched_ids: set[int] = set()

    refresh_budget = max(0, min(int(recover_limit), 16))
    for index, (article, tax, _reason) in enumerate(broken):
        touched_ids.add(int(article.id))
        replacement = None
        source_url = str(article.source_url or "").strip()
        if index < refresh_budget and source_url:
            replacement = _reachable_source_image(
                source_url,
                current_url=article.image_url,
                max_checks=6,
            )

        if replacement:
            article.image_url = replacement
            db.add(article)
            resolved = _image_repair_resolution(article, tax)
            persist_public_article(db, article, resolved, commit=False)
            if tax.public_ok:
                refreshed += 1
                continue

        # Never leave a known-dead hero in the public feed. Rows beyond the
        # bounded source-refresh budget are held immediately and can recover in
        # a later cycle from their canonical source page.
        article.image_url = None
        tax.hero_media_kind = "MISSING"
        tax.public_ok = False
        db.add(article)
        db.add(tax)
        hidden += 1

    # A previously held recent row may become recoverable when the publisher
    # changes its hero URL. Re-extract a small bounded set every cycle.
    recovery_rows = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(False),
            Article.source_url.isnot(None),
            Article.source_url != "",
            ((Article.image_url.is_(None)) | (Article.image_url == "")),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(recover_limit), 16)))
        .all()
    )
    recovered = 0
    for article, tax in recovery_rows:
        if int(article.id) in touched_ids:
            continue
        candidate = _reachable_source_image(
            str(article.source_url),
            current_url=article.image_url,
            max_checks=6,
        )
        if not candidate:
            continue
        article.image_url = candidate
        db.add(article)
        resolved = _image_repair_resolution(article, tax)
        persist_public_article(db, article, resolved, commit=False)
        if tax.public_ok:
            recovered += 1

    # A reachable photograph can still belong to a recommendation card. Audit
    # a bounded set against each original article, using the same hero ordering
    # as new ingestion. Cache by source+stored image, so a change is rechecked.
    aligned = 0
    checks = 0
    now = time.monotonic()
    for key, expires in list(_SOURCE_IMAGE_CHECKED.items()):
        if expires <= now:
            _SOURCE_IMAGE_CHECKED.pop(key, None)
    for article, tax in rows:
        if not tax.public_ok or int(article.id) in touched_ids or not article.source_url:
            continue
        key = (int(article.id), article.source_url, article.image_url)
        if key in _SOURCE_IMAGE_CHECKED or checks >= min(6, refresh_budget):
            continue
        checks += 1
        preferred = _reachable_source_image(article.source_url,
            current_url=article.image_url, max_checks=6, include_current=True)
        _SOURCE_IMAGE_CHECKED[key] = now + (6 * 3600 if preferred else 900)
        if preferred and preferred != article.image_url:
            article.image_url = preferred
            tax.hero_media_kind = classify_media_url(preferred)
            db.add(article)
            db.add(tax)
            _SOURCE_IMAGE_CHECKED[(int(article.id), article.source_url, preferred)] = now + 6 * 3600
            aligned += 1
            logger.info("[public_index] aligned hero with source article=%s", article.id)
    changed = refreshed + hidden + recovered + aligned
    if changed:
        try:
            db.commit()
        except Exception:
            db.rollback()
            _SOURCE_IMAGE_CHECKED.clear()
            logger.exception("recent News image repair failed")
            return 0
        logger.info(
            "[public_index] image repair checked=%s failed=%s definitive=%s refreshed=%s hidden=%s recovered=%s reasons=%s aligned=%s",
            len(rows),
            len(failed),
            len(broken),
            refreshed,
            hidden,
            recovered,
            dict(reasons),
            aligned,
        )
    elif broken:
        logger.info(
            "[public_index] image repair checked=%s failed=%s definitive=%s changed=0 reasons=%s",
            len(rows),
            len(failed),
            len(broken),
            dict(reasons),
        )
    return changed

def _correct_confirmed_deadline_copy(article: Article) -> dict:
    """Remove only the exact disproven clause from the audited News original.

    Source 555050 says both "večeras do ponoći" and "večeras do 24 časa".
    The preceding midnight statement is accurate; the added duration is not.
    This cannot affect another source, translated rows or a held row's state.
    """
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22162 or not article.ai_generated
            or source.hostname not in {'www.mozzartsport.com', 'mozzartsport.com'}
            or source.path.rstrip('/') != '/kosarka/vesti/ostoja-mijailovic-aba-liga-ce-poceti-poslali-smo-novi-predlog-sudijama/555050'):
        return {}
    clause = ', which is set for 24 hours from now'
    changes = {}
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if value and clause + '.' in value and 'tonight at midnight' in value:
            revised = value.replace(clause + '.', '.')
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_lead_headline(article: Article) -> dict:
    """Repair the audited source-lead headline without changing its URL or date."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    old_title = ('All Blacks head coach Dave Rennie has named a 34-man squad for the '
                 'Bledisloe Cup series starting next weekend at Eden Park in Auckland.')
    if (article.id != 22163 or not article.ai_generated
            or source.hostname not in {'www.rugbypass.com', 'rugbypass.com'}
            or source.path.rstrip('/') != '/news/scott-barrett-among-notable-inclusions-in-34-man-all-blacks-bledisloe-cup-squad'
            or article.title != old_title):
        return {}
    article.title = 'Barrett and Frizell return as Taylor takes All Blacks captaincy'
    return {'title': {'before': old_title, 'after': article.title}}


def _correct_confirmed_ufc_copy(article: Article) -> dict:
    """Apply only source-verified spelling and commercial-copy corrections."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22165 or not article.ai_generated
            or source.hostname not in {'www.ufc.com', 'ufc.com'}
            or source.path.rstrip('/') != '/news/octagon-returns-down-under-ufc-fight-night-sydney-sunday-february-7'):
        return {}
    commercial_copy = (
        ' Travel packages for fans are available through Sportsnet Holidays, and exclusive corporate suites can be booked directly via Afterpay Arena.',
        ' General public and UFC VIP ticket details will be announced later, with pre‑sale access available through UFC.com/Sydney.',
    )
    changes = {}
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if not value:
            continue
        revised = value.replace('Volkovski vs. Lopes', 'Volkanovski vs. Lopes')
        for sentence in commercial_copy:
            revised = revised.replace(sentence, '')
        if revised != value:
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_mccabe_copy(article: Article, tax) -> dict:
    """The official header says Women's Team; it does not establish EPL."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    old = 'Katie McCabe helps Chelsea defeat former club Arsenal in Premier League match'
    previous_repair = "McCabe reflects on Chelsea Women's victory over former club Arsenal"
    new = "McCabe praises Walsh after Chelsea Women's victory over Arsenal"
    if (article.id != 22166 or not article.ai_generated
            or source.hostname not in {'www.chelseafc.com', 'chelseafc.com'}
            or source.path.rstrip('/') != '/en/news/article/katie-mccabe-on-playing-smart-and-riding-the-storms-against-former-club'
            or article.title not in {old, previous_repair, new}):
        return {}
    changes = {}
    if article.title != new:
        changes['title'] = {'before': article.title, 'after': new}
        article.title = new
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if value and 'surrounding her return to Stamford Bridge' in value:
            revised = value.replace('surrounding her return to Stamford Bridge', 'around facing her former club')
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    if tax.resolved_competition == 'england-premier-league':
        changes['competition'] = {'before': tax.resolved_competition, 'after': None}
        tax.resolved_competition = None
        tax.competition_confidence = 0.0
    if article.league == 'england-premier-league':
        article.league = None
        article.country = None
        changes['article_league'] = {'before': 'england-premier-league', 'after': None}
    return changes


def _correct_confirmed_fss_copy(article: Article) -> dict:
    """Repair the exact audited original; preserve its date, slug and status."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22191 or not article.ai_generated
            or source.hostname != 'fss.rs'
            or source.path.rstrip('/') != '/a-tim-promene-u-sastavu-pred-nastavak-lige-nacija'):
        return {}
    replacements = {
        'Veľko Paukovic': 'Veljko Paunović',
        'Ognen Mimovic': 'Ognjen Mimović',
        'Dragun Rosic': 'Dragan Rosić',
        'Voivodina': 'Vojvodina',
        'a home game against Germany in Munich': 'an away game against Germany in Munich',
    }
    changes = {}
    for field in ('summary', 'content', 'ai_content'):
        value = getattr(article, field, None)
        if not value:
            continue
        revised = value
        for old, new in replacements.items():
            revised = revised.replace(old, new)
        if revised != value:
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_yakin_copy(article: Article) -> dict:
    """Remove two audited translation errors, leaving this News row in place."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22193 or not article.ai_generated
            or source.hostname != 'www.blick.ch'
            or source.path.rstrip('/') != '/sport/fussball/nations-league/nati-pk-vor-schottland-yakin-und-elvedi-live/mqh1lxn'):
        return {}
    replacements = {
        'Assistant coaches Davide Callà and Nico Elvedi addressed media questions.':
            'Davide Callà and Nico Elvedi answered media questions.',
        'The team’s arrival also faced delays after a fuel calculation error forced an emergency refueling stop in Zurich, causing a three-hour delay.':
            'The team’s flight stopped in Zurich to refuel following discrepancies in weight calculations, and the team arrived roughly three hours late.',
    }
    changes = {}
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if not value:
            continue
        revised = value
        for old, new in replacements.items():
            revised = revised.replace(old, new)
        if revised != value:
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_gudelj_copy(article: Article) -> dict:
    """Keep the audited study's position category and the correct actor."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22201 or not article.ai_generated
            or source.hostname != 'www.crvenazvezdafk.com'
            or source.path.rstrip('/') != '/vesti/gudelj-medju-najboljim-mladim-stoperima-sveta'):
        return {}
    replacements = {
        'Stefan Gudelj ranked eighth among world’s best football defenders under 22':
            'Gudelj takes eighth place in CIES under-22 centre-back study',
        'Stefan Gudelj of Red Star Belgrade has been ranked eighth among the world’s best defenders under 22, according to the latest CIES football observer study.':
            'CIES ranked Red Star Belgrade’s Stefan Gudelj eighth among centre-backs under 22.',
        'The study covers more than 70 leagues worldwide and gives Gudelj an index of 79.4, placing him among the top young defenders globally.':
            'The study covers more than 70 leagues worldwide and gives Gudelj an index of 79.4.',
        'Red Star’s consistent progress and the player’s maturity have earned him international recognition and another strong endorsement of the club’s youth academy.':
            'The club credited Gudelj’s performances, progress and maturity with earning the recognition, and described it as further evidence of the work of its youth academy.',
    }
    changes = {}
    for field in ('title', 'summary', 'content', 'ai_content'):
        value = getattr(article, field, None)
        if not value:
            continue
        revised = value
        for old, new in replacements.items():
            revised = revised.replace(old, new)
        if revised != value:
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_taranto_format(article: Article) -> dict:
    """Remove an audited formatting marker without changing the report."""
    try:
        source = urlsplit(article.source_url or '')
    except ValueError:
        return {}
    if (article.id != 22195 or not article.ai_generated
            or source.hostname != 'aleagues.com.au'
            or source.path.rstrip('/') != '/news/news-adriana-taranto-named-new-adelaide-united-captain'):
        return {}
    changes = {}
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if value and '[Blank Line]' in value:
            revised = value.replace('\n[Blank Line]\n', '\n\n').replace('[Blank Line]', '')
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def repair_recent_gossip_news(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Hold recent public non-news, branded copy and gossip; retain source rows."""
    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            or_(ArticleTaxonomyResolution.public_ok.is_(True), Article.id == 22166),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )
    hidden = 0
    corrected = 0
    reasons = {}
    for article, tax in rows:
        gudelj_changes = _correct_confirmed_gudelj_copy(article)
        if gudelj_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='expanded_player_position_scope',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Source ranks under-22 centre-backs (штопера); performances, progress and maturity belong to Gudelj, not to the club',
                         'changes': gudelj_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed player ranking scope article=%s', article.id)
        format_changes = _correct_confirmed_taranto_format(article)
        if format_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='draft_placeholder',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Literal [Blank Line] editorial marker is not source reporting',
                         'changes': format_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed format marker article=%s', article.id)
        yakin_changes = _correct_confirmed_yakin_copy(article)
        if yakin_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='expanded_role_scope_and_travel_cause',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Source names Callà and Elvedi without establishing both as assistant coaches; Gewichtsberechnung is weight calculation, not fuel calculation; no emergency refuelling assertion',
                         'changes': yakin_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed interview role and travel cause article=%s', article.id)
        fss_changes = _correct_confirmed_fss_copy(article)
        if fss_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='serbian_name_spelling_and_away_fixture',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'FSS: Вељко Пауновић; Огњен Мимовић; Драгану Росићу; Војводине; гостовање Немачкој у Минхену',
                         'changes': fss_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed FSS names and away fixture article=%s', article.id)
        mccabe_changes = _correct_confirmed_mccabe_copy(article, tax)
        if mccabe_changes:
            db.add_all([article, tax])
            from bot.news_learning import record_incident, mark_auto_corrected
            from models import NewsIncident
            previous_repair = "McCabe reflects on Chelsea Women's victory over former club Arsenal"
            for incident in db.query(NewsIncident).filter(
                    NewsIncident.article_id == article.id,
                    NewsIncident.reason_code == 'non_news_retrospective_commentary',
                    NewsIncident.phase == 'postpublish',
                    NewsIncident.writer_provider == 'news-audit',
                    NewsIncident.writer_model == 'deterministic',
                    NewsIncident.status == 'open',
                    NewsIncident.confirmed.is_(False)).all():
                if (incident.draft_excerpt or '').startswith(previous_repair):
                    mark_auto_corrected(db, incident, note='Current report retitled without retrospective wording; source-confirmed womens team; public gates rechecked')
            # The previous repair title triggered the retrospective filter.
            # Re-run public admission for this exact audited row, preserving
            # all other incidents and requiring a working photo first.
            from bot.news_image_http import news_image_is_reachable
            if news_image_is_reachable(article.image_url):
                persist_public_article(db, article, cache_row_to_resolution(tax), commit=False)
            else:
                tax.public_ok = False
                db.add(tax)
            record_incident(db, reason_code='inferred_mens_competition_for_womens_team',
                article_id=article.id, source_url=article.source_url, sport=tax.resolved_sport,
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Official current ArticleHeader category is Womens Team; source never names Premier League',
                         'changes': mccabe_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed womens-team competition article=%s', article.id)
        ufc_changes = _correct_confirmed_ufc_copy(article)
        if ufc_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='confirmed_participant_spelling_and_commercial_copy',
                article_id=article.id, source_url=article.source_url, sport=tax.resolved_sport,
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Official source spells VOLKANOVSKI vs. LOPES 2; omit booking and presale directions',
                         'changes': ufc_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed UFC copy article=%s', article.id)
        headline_changes = _correct_confirmed_lead_headline(article)
        if headline_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='headline_too_similar_to_source',
                article_id=article.id, source_url=article.source_url, sport=tax.resolved_sport,
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Audited source confirms Barrett/Frizell return and Taylor captaincy; former headline closely rewrote its opening sentence',
                         'changes': headline_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed source-lead headline article=%s', article.id)
        copy_changes = _correct_confirmed_deadline_copy(article)
        if copy_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='clock_time_as_duration',
                article_id=article.id, source_url=article.source_url, sport=tax.resolved_sport,
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'evidence': 'Source states tonight by midnight; 24 is a clock time, not elapsed hours',
                         'changes': copy_changes})
            corrected += 1
            logger.info('[public_index] corrected confirmed deadline article=%s', article.id)
        # A publisher's domestic feed label cannot turn an explicit national
        # tournament headline into that country's club league. Clear the
        # unsupported competition only; never infer a fixture or enable a hold.
        from bot.taxonomy import COMPETITIONS
        competition = tax.resolved_competition
        country = (COMPETITIONS.get(competition) or {}).get('country')
        if (tax.resolved_sport == 'football'
                and re.search(r'\bnations league\b', article.title or '', re.I)
                and country and country not in {'international', 'global', 'europe'}):
            tax.resolved_competition = None
            tax.competition_confidence = 0.0
            article.league = None
            article.country = None
            db.add_all([article, tax])
            from bot.news_learning import record_incident
            record_incident(db, reason_code='taxonomy_competition_mismatch',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected',
                writer_provider='news-audit', writer_model='deterministic',
                details={'previous_competition': competition,
                         'evidence': 'explicit Nations League headline; domestic league unsupported'})
            corrected += 1
            logger.info('[public_index] cleared unsupported domestic competition article=%s previous=%s', article.id, competition)
        item = {
            "title": article.title,
            "summary": article.summary,
            "body": article.ai_content or article.content or "",
            "url": article.source_url,
        }
        reason = (gossip_news_reason(item) or non_article_news_reason(item)
                  or publisher_branding_reason(item)
                  or source_path_conflict_reason(item, tax.resolved_sport))
        if not reason:
            continue
        tax.public_ok = False
        db.add(tax)
        from bot.news_learning import record_incident
        record_incident(
            db, reason_code=reason, article_id=article.id, source_url=article.source_url,
            phase="postpublish", draft=item, writer_provider="news-audit",
            writer_model="deterministic", details={"gate": "public_news_admission"},
        )
        hidden += 1
        reasons[reason] = reasons.get(reason, 0) + 1
        logger.warning(
            "[public_index] hide gossip article=%s reason=%s title=%s",
            article.id,
            reason,
            (article.title or "")[:120],
        )
    if hidden or corrected:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent News gossip repair failed")
            return 0
        logger.info(
            "[public_index] gossip repair hidden=%s reasons=%s competition_corrections=%s",
            hidden,
            reasons,
            corrected,
        )
    return hidden + corrected


def repair_recent_duplicate_news(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Hide recent cross-source duplicate News rows without deleting articles.

    Newest public row wins. The stricter ingest-time detector prevents recurrence;
    this bounded repair cleans legacy duplicate cards already in the public index.
    """
    from bot.dedupe import titles_are_near_duplicate

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution,
            Article.id,
            Article.title,
        )
        .join(
            Article,
            Article.id == ArticleTaxonomyResolution.article_id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )
    from bot.dedupe import _title_tokens

    kept_titles: dict[str, dict[int, str]] = {}
    token_index: dict[str, dict[str, set[int]]] = {}
    hidden = 0
    for tax, article_id, article_title in rows:
        sport = str(tax.resolved_sport or "")
        title = article_title or ""
        if not sport or not title:
            continue
        tokens = _title_tokens(title)
        sport_titles = kept_titles.setdefault(sport, {})
        sport_index = token_index.setdefault(sport, {})

        candidate_ids: set[int] = set()
        token_hits: dict[int, int] = {}
        for token in tokens:
            for candidate_id in sport_index.get(token, ()):
                token_hits[candidate_id] = token_hits.get(candidate_id, 0) + 1
        # Near-duplicate headlines should share multiple meaningful terms. Exact
        # normalization still gets a fallback scan over the small recent set.
        candidate_ids.update(
            candidate_id for candidate_id, hits in token_hits.items() if hits >= 3
        )
        normalized = None
        duplicate = False
        for candidate_id in candidate_ids:
            other = sport_titles.get(candidate_id, "")
            if other and titles_are_near_duplicate(title, other):
                duplicate = True
                break
        if not duplicate:
            from bot.textutil import normalize_title

            normalized = normalize_title(title)
            duplicate = any(
                normalize_title(other) == normalized
                for other in sport_titles.values()
            )
        if duplicate:
            tax.public_ok = False
            db.add(tax)
            hidden += 1
            continue

        sport_titles[int(article_id)] = title
        for token in tokens:
            sport_index.setdefault(token, set()).add(int(article_id))
    if hidden:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent News duplicate repair failed")
            return 0
        logger.info("[public_index] hid recent duplicate News rows=%s", hidden)
    return hidden



def _distinctive_title_sport_support(title: str, sport: str) -> bool:
    """Require a word-bounded alias unique to the proposed sport in the headline."""
    from bot.taxonomy import SPORT_ALIASES

    haystack = " " + (title or "").casefold() + " "
    aliases = [
        str(alias).casefold()
        for alias in SPORT_ALIASES.get(sport, ())
        if str(alias).strip()
    ]
    other_aliases = {
        str(alias).casefold().strip()
        for other_sport, rows in SPORT_ALIASES.items()
        if other_sport != sport
        for alias in rows
        if str(alias).strip()
    }
    for alias in aliases:
        needle = alias.strip()
        if len(needle) < 4 or needle in other_aliases:
            continue
        pattern = re.compile(
            r"(?<!\w)" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?!\w)",
            re.IGNORECASE,
        )
        if pattern.search(haystack):
            return True
    return False

def _explicit_title_sport_override(title: str) -> Optional[str]:
    """Very narrow, high-signal title markers allowed to correct a cached sport."""
    value = " " + (title or "").casefold() + " "
    # MMA/UFC are unambiguous sport labels in a News headline. They must outrank
    # incidental city/club words such as Brighton that otherwise resemble football.
    if re.search(r"(?<!\w)(?:mma|ufc|mixed\s+martial\s+arts|oktagon)(?!\w)", value, re.I):
        return "mma"
    if CRICKET_TITLE_RE.search(value):
        return "cricket"
    if VOLLEYBALL_TITLE_RE.search(value):
        return "volleyball"
    if RUGBY_LEAGUE_TITLE_RE.search(value) and not RUGBY_UNION_TITLE_RE.search(value):
        return "rugby-league"
    if RUGBY_UNION_TITLE_RE.search(value) and not RUGBY_LEAGUE_TITLE_RE.search(value):
        return "rugby"
    # Strong road-cycling phrases outrank the generic words "Grand Prix".
    # This is intentionally narrow so motorsport Grand Prix stories are unchanged.
    if re.search(
        r"(?<!\w)(?:road\s+race\s+world\s+(?:title|champion|championships?)|"
        r"road\s+cycling|uci\s+road(?:\s+world)?|peloton)(?!\w)",
        value,
        re.I,
    ):
        return "cycling"
    if re.search(r"(?<!\w)(?:darts|pdc)(?!\w)", value, re.I):
        return "darts"
    if re.search(r"(?<!\w)snooker(?!\w)", value, re.I):
        return "snooker"
    if (
        re.search(r"(?<!\w)napoli(?!\w)", value, re.I)
        and re.search(
            r"(?<!\w)(?:defender|midfielder|striker|goalkeeper|contract|new\s+deal|serie\s+a)(?!\w)",
            value,
            re.I,
        )
    ):
        return "football"
    return None


def repair_recent_sport_mislabels(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Correct recent public sport mislabels when two independent resolvers agree.

    Feed/source hints are excluded. A conflicting row is reassigned only when:
    1) the independent ingest classifier names a different sport,
    2) that sport has a distinctive headline marker, and
    3) the public taxonomy resolver independently agrees at publish confidence.
    If the third check fails, the suspect row is hidden instead of guessing.
    """
    from bot.classify import classify_article
    from bot.taxonomy import SPORT_ALIASES

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution,
            Article.id,
            Article.title,
        )
        .join(
            Article,
            Article.id == ArticleTaxonomyResolution.article_id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            ArticleTaxonomyResolution.resolved_sport.isnot(None),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )

    alias_owners: dict[str, set[str]] = {}
    for candidate_sport, aliases in SPORT_ALIASES.items():
        for alias in aliases or ():
            value = str(alias or "").casefold().strip()
            if len(value) >= 4:
                alias_owners.setdefault(value, set()).add(candidate_sport)
    distinctive_aliases = [
        (alias, next(iter(owners)))
        for alias, owners in alias_owners.items()
        if len(owners) == 1
    ]

    candidates: dict[int, tuple[ArticleTaxonomyResolution, str, set[str]]] = {}
    for tax, article_id, title in rows:
        cached = str(tax.resolved_sport or "")
        raw_title = title or ""
        if not cached or not raw_title:
            continue
        possible: set[str] = set()
        explicit_title_sport = _explicit_title_sport_override(raw_title)
        if explicit_title_sport and explicit_title_sport != cached:
            possible.add(explicit_title_sport)
        for alias, candidate_sport in distinctive_aliases:
            if candidate_sport == cached:
                continue
            pattern = re.compile(
                r"(?<!\w)" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?!\w)",
                re.IGNORECASE,
            )
            if pattern.search(raw_title):
                possible.add(candidate_sport)
        if possible:
            candidates[int(article_id)] = (tax, raw_title, possible)

    if not candidates:
        return 0

    articles = {
        int(article.id): article
        for article in (
            db.query(Article)
            .filter(Article.id.in_(list(candidates)))
            .all()
        )
    }

    corrected = 0
    hidden = 0
    for article_id, (tax, title, possible) in candidates.items():
        article = articles.get(article_id)
        if article is None:
            continue
        body = article.ai_content or article.content or article.summary or ""
        explicit_title_sport = _explicit_title_sport_override(title)
        if explicit_title_sport and explicit_title_sport != str(tax.resolved_sport or ""):
            forced = TaxonomyResolution(
                sport=explicit_title_sport,
                competition=None,
                sport_confidence=0.99,
                competition_confidence=0.0,
                evidence=["explicit-title-sport-marker"],
            )
            cached_sport = str(tax.resolved_sport or "")
            persist_public_article(db, article, forced, commit=False)
            if tax.public_ok and tax.resolved_sport == explicit_title_sport:
                corrected += 1
                from bot.news_learning import record_incident
                record_incident(
                    db, article_id=article.id, source_url=article.source_url,
                    sport=explicit_title_sport, reason_code="taxonomy_sport_mismatch",
                    phase="postpublish", status="auto_corrected",
                    draft={"title": article.title, "summary": article.summary, "body": body},
                    writer_provider="news-audit", writer_model="deterministic",
                    details={"previous_sport": cached_sport, "corrected_sport": explicit_title_sport,
                             "gate": "explicit_title_sport_marker"},
                )
                logger.warning(
                    "[public_index] corrected explicit-title sport article=%s cached=%s corrected=%s title=%s",
                    article_id,
                    cached_sport,
                    explicit_title_sport,
                    title[:100],
                )
                continue
            tax.public_ok = False
            db.add(tax)
            hidden += 1
            logger.warning(
                "[public_index] hide explicit-title sport conflict article=%s cached=%s expected=%s title=%s",
                article_id,
                cached_sport,
                explicit_title_sport,
                title[:100],
            )
            continue

        independent = classify_article(
            title,
            body,
            feed_kind="mixed",
            feed_sport=None,
            feed_league=None,
            feed_country=None,
        )
        if not (
            independent.sport
            and independent.sport in possible
            and tax.resolved_sport
            and independent.sport != tax.resolved_sport
            and _distinctive_title_sport_support(title, independent.sport)
        ):
            continue

        cached_sport = str(tax.resolved_sport or "")
        resolved = resolve_article_competition(article)
        if (
            resolved.sport == independent.sport
            and resolved.sport_confidence >= MIN_SPORT_CONFIDENCE
            and news_image_is_publishable(article.image_url)
        ):
            persist_public_article(db, article, resolved, commit=False)
            if tax.public_ok and tax.resolved_sport == independent.sport:
                corrected += 1
                logger.warning(
                    "[public_index] corrected sport mismatch article=%s cached=%s corrected=%s title=%s",
                    article_id,
                    cached_sport,
                    independent.sport,
                    title[:100],
                )
                continue

        logger.warning(
            "[public_index] hide sport mismatch article=%s cached=%s independent=%s title=%s",
            article_id,
            cached_sport,
            independent.sport,
            title[:100],
        )
        tax.public_ok = False
        db.add(tax)
        hidden += 1

    changed = corrected + hidden
    if changed:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent News sport-mislabel repair failed")
            return 0
        logger.info(
            "[public_index] sport-mislabel repair corrected=%s hidden=%s",
            corrected,
            hidden,
        )
    return changed
