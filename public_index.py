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
from bot.news_policy import CRICKET_TITLE_RE, VOLLEYBALL_TITLE_RE, RUGBY_LEAGUE_TITLE_RE, RUGBY_UNION_TITLE_RE, RALLY_TITLE_RE, gossip_news_reason, non_article_news_reason, publisher_branding_reason, source_path_conflict_reason
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
    # Menu placement is downstream of every factual/quality/public admission
    # gate. It cannot rescue a rejected article or insert claims into its copy.
    from bot.news_football_sections import assign_public_football_section
    assign_public_football_section(article, row)
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
    rotate: bool = False,
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
    query = (
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
    )
    rotation_scope = rotation_cursor = None
    if rotate:
        import os
        from bot.news_image_rotation import next_image_health_rows
        rows, rotation_scope, rotation_cursor = next_image_health_rows(
            query, limit=limit, football_only=os.environ.get('NEWS_FOOTBALL_ONLY') == '1',
            window=max_age_hours,
        )
    else:
        rows = query.order_by(
            Article.image_url.ilike("%soccernews.com/og/og-image.%").desc(),
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        ).limit(max(1, min(int(limit), 160))).all()

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
        "signed_image_display_incompatible",
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
    # A transient CDN failure is never grounds to hide an article. Prefer
    # its own source-page photo check within the EXISTING six-check allowance.
    alignment_rows = sorted(rows, key=lambda row: bool(
        probes.get(str(row[0].image_url or '').strip(), (False, 'missing'))[0]))
    for article, tax in alignment_rows:
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
    if rotate:
        from bot.news_image_rotation import finish_image_health_rows
        finish_image_health_rows(rotation_scope, rotation_cursor)
        logger.info('[public_index] News rotating photo check scope=%s checked=%s failed=%s next_id=%s source_checks=%s',
                    rotation_scope, len(rows), dict(reasons), rotation_cursor, checks)
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
    if re.fullmatch(r'\[?blank\s+line\]?', (getattr(article, 'summary', None) or '').strip(), re.I):
        previous = article.summary
        article.summary = "Adriana Taranto will captain Adelaide United in the 2026/27 Ninja A-League Women's season."
        changes['summary'] = {'before': previous, 'after': article.summary}
    for field in ('content', 'ai_content'):
        value = getattr(article, field, None)
        if value and '[Blank Line]' in value:
            revised = value.replace('\n[Blank Line]\n', '\n\n').replace('[Blank Line]', '')
            setattr(article, field, revised)
            changes[field] = {'before': value, 'after': revised}
    return changes


def _correct_confirmed_football_prose(article: Article) -> dict:
    """Exact, source-compared corrections; preserve row identity and archive."""
    if article.id == 22632:
        # Compare-and-set: never overwrite a subsequently edited article.
        # Southport's own resignation notice names Neil Danns, not Duffy.
        # Tranmere's official player reporting supplies the correct club name.
        import hashlib
        if (article.title != 'Mark Duffy named Southport manager after interim spell'
                or article.sport != 'football'
                or any(not isinstance(getattr(article, field, None), str)
                       or hashlib.sha256(getattr(article, field).encode()).hexdigest()
                       != '5ba9557f0b365ab09093c42e62adba28fffd04485da01bca4b5643820228aea1'
                       for field in ('content', 'ai_content'))):
            return {}
    sources = {
        22632: 'https://the72.co.uk/2026/10/02/sheffield-united-mark-duffy-new-managerial-job/',
        22204: 'https://fss.rs/aleksandar-stankovic-prva-utakmica-na-marakani-u-dresu-a-tima-ostvarenje-jednog-od-mojih-snova/',
        22206: 'https://www.footmercato.net/a2290739679306661964-un-ancien-prodige-du-real-madrid-evoque-un-eventuel-retour',
        22207: 'https://fss.rs/dusan-tadic-pokazali-smo-zajednistvo-i-borbenost-to-je-put-kojim-treba-da-idemo/',
        22210: 'https://football-italia.net/kayode-impresses-italy-debut-palestra-duel/',
        22213: 'https://rmcsport.bfmtv.com/football/equipe-de-france/belgique-france-le-coach-m-a-donne-toute-sa-confiance-les-conseils-de-zinedine-zidane-avant-les-debuts-des-petits-nouveaux_AV-202609290379.html',
    }
    if not article.ai_generated or sources.get(article.id) != article.source_url:
        return {}
    changes = {}
    for field in ('title', 'summary', 'content', 'ai_content'):
        old = getattr(article, field, None)
        if not isinstance(old, str):
            continue
        new = old
        if article.id == 22204:
            if field == 'summary' and old.strip().casefold() == 'blank line':
                new = 'Aleksandar Stanković described his first senior Serbia appearance at Rajko Mitić Stadium as the fulfilment of a childhood dream.'
            else:
                new = new.replace("Young Serbian international made his debut against Netherlands and praised his team's character despite a 1:2 defeat.", '')
                new = re.sub(r'(?im)^\s*\[?blank\s+line\]?\s*$', '', new).strip()
        elif article.id == 22206:
            new = new.replace('Aurélien Tchouaméni, Eduardo Camavinga and Bernardo Silva',
                              'Tchouaméni, Camavinga and Bernardo Silva')
        elif article.id == 22207:
            new = new.replace('Serbia football captain Dušan Tadić', 'Serbia’s Dušan Tadić')
            new = new.replace('The captain explained', 'Tadić explained')
            new = new.replace('He stated that many of these players grew up alongside him and share mutual respect and affection.',
                'He said he had played alongside many of them and that the affection and respect were mutual.')
        elif article.id == 22210:
            if field == 'summary' and old == 'Brentford defender Michael Kayode earned Man of the Match honors from multiple Italian newspapers after scoring and assisting in a victory.':
                new = 'Michael Kayode scored on his senior Italy debut as the team beat Türkiye 4-1 in Bursa.'
            else:
                new = new.replace('The 22-year-old right-back', 'The 22-year-old Brentford defender')
                new = new.replace('in March before sustaining an injury.', 'in March.')
                for fragment in (
                    ' Most Italian publications selected him as the standout performer following the 4-1 result against Türkiye.',
                    ' Gazzetta and Corriere della Sera both assigned him a rating of 7/10 for the display.',
                    ' Gazzetta described the performance as commanding and noted the player scored his first goal for the national team.',
                    ' Corriere della Sera questioned whether Kayode might displace Palestra from the starting lineup once that player recovers from injury.',
                    ' Corriere dello Sport and Tuttosport rated Kayode 7.5/10 for the match, though the former outlet gave the Man of the Match award to Sandro Tonali with an 8/10 rating.',
                    ' Lorenzo Bettoni serves as the Editor of Football Italia.',
                ):
                    new = new.replace(fragment, '')
        elif article.id == 22213:
            new = new.replace('Pierre Kalulu, making his third appearance for the national team,',
                'Pierre Kalulu, who had three national-team appearances before the match,')
            new = new.replace('Andy Diouf debuted in a central defensive role despite limited prior experience in that position.',
                'Andy Diouf played on the left side of defence for the first time and said the position was unfamiliar to him.')
            new = new.replace('Lucas Da Cunha, a Côme player with only three caps,',
                'Lucas Da Cunha, a Côme player,')
        elif article.id == 22632 and field in ('content', 'ai_content'):
            new = new.replace('Duffy had been Southport’s assistant manager to Neil Danns, but stood down from those duties earlier this month before taking the top job.',
                'Duffy had been Southport’s assistant manager to Neil Danns before taking the top job.')
            new = new.replace('Tranmere Town', 'Tranmere Rovers')
        if new != old:
            setattr(article, field, new)
            changes[field] = {'before': old, 'after': new}
    return changes


def _recover_confirmed_language_hold(db: Session, article: Article, tax) -> bool:
    """Recheck only AI drafts seen failing the old name/diacritic gate.

    These rows passed both factual validators before insertion. Never admit
    legacy imports, Live Scores, arbitrary held rows, or any open incident.
    """
    from editorial import SLAVIC_LETTER_RE
    from bot.news_policy import news_freshness_reason
    from bot.news_image_http import news_image_is_reachable
    from bot.dedupe import titles_are_near_duplicate
    if (article.id not in {22202, 22204, 22205, 22207} or tax.public_ok
            or not article.ai_generated or tax.resolved_sport != 'football'
            or urlsplit(article.source_url or '').hostname not in {'fss.rs', 'www.novosti.rs'}
            or '/live-scores' in (article.source_url or '').lower()):
        return False
    body = article.ai_content or article.content or ''
    old_signal = (len(SLAVIC_LETTER_RE.findall(body)) >= 3
                  or len(SLAVIC_LETTER_RE.findall(article.title or '')) >= 2)
    quality = evaluate_quality(title=article.title, summary=article.summary,
        body=body, image_url=article.image_url)
    logger.info('[public_index] language hold review article=%s old_name_signal=%s flags=%s title=%s body=%s',
        article.id, old_signal, quality.get('flags'), article.title, body[:420])
    stamp = article.published_at
    if stamp is not None and stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)  # schema stores UTC
    if (not old_signal or not quality.get('ok')
            or news_freshness_reason(stamp, datetime.now(timezone.utc))
            or article_has_open_incident(db, article.id)):
        return False
    peers = db.query(Article.title).join(ArticleTaxonomyResolution,
        ArticleTaxonomyResolution.article_id == Article.id).filter(
            ArticleTaxonomyResolution.public_ok.is_(True),
            ArticleTaxonomyResolution.resolved_sport == 'football',
            Article.id != article.id).all()
    if any(titles_are_near_duplicate(article.title or '', title or '') for title, in peers):
        return False
    if not news_image_is_reachable(article.image_url):
        return False
    persist_public_article(db, article, cache_row_to_resolution(tax), commit=False)
    if not tax.public_ok:
        return False
    from bot.news_learning import record_incident
    record_incident(db, reason_code='english_proper_name_false_language_hold',
        article_id=article.id, source_url=article.source_url, sport='football',
        phase='public-admission', status='auto_corrected',
        writer_provider='news-audit', writer_model='deterministic',
        details={'evidence': 'Observed AI factual-validation pass followed by non_english admission hold; Latin proper names excluded from letter heuristic; full public gates and image rechecked; original copy/date preserved'})
    logger.info('[public_index] recovered English proper-name false hold article=%s', article.id)
    return True


def _correct_confirmed_chema_currency(article: Article) -> dict:
    if (article.id != 22206 or not article.ai_generated or article.source_url !=
            'https://www.footmercato.net/a2290739679306661964-un-ancien-prodige-du-real-madrid-evoque-un-eventuel-retour'):
        return {}
    changes = {}
    for field in ('content', 'ai_content'):
        old = getattr(article, field, None)
        if not isinstance(old, str):
            continue
        new = old.replace("23 millions d'euros", '€23 million').replace("14,5 millions d'euros", '€14.5 million')
        if new != old:
            setattr(article, field, new)
            changes[field] = {'before': old, 'after': new}
    return changes


def repair_recent_gossip_news(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Hold recent public non-news, branded copy and gossip; retain source rows."""
    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    import os
    football_focus = os.environ.get('NEWS_FOOTBALL_ONLY') == '1'
    ordering = [func.coalesce(Article.published_at, Article.created_at).desc(), Article.id.desc()]
    if football_focus:
        # Otherwise newer rows from other sports permanently starve older
        # still-public football mistakes. Retain the SAME bounded budget.
        ordering.insert(0, (ArticleTaxonomyResolution.resolved_sport == 'football').desc())
    rows = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            or_(ArticleTaxonomyResolution.public_ok.is_(True), Article.id.in_((22166, 22195, 22202, 22204, 22205, 22207))),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(*ordering)
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )
    logger.info('[public_index] News editorial repair scanned=%s football_focus=%s', len(rows), football_focus)
    hidden = 0
    corrected = 0
    reasons = {}
    for article, tax in rows:
        prose_changes = _correct_confirmed_football_prose(article)
        if prose_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='confirmed_football_prose_scope',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected', writer_provider='news-audit',
                writer_model='deterministic', details={'changes': prose_changes,
                    'primary_evidence': (['https://southportfc.net/neil-danns-stands-down/',
                        'https://www.tranmererovers.co.uk/news/2021/september/tranmere-4-1-leeds-united-u21s/']
                        if article.id == 22632 else []),
                    'evidence': 'Compared with exact source; for 22632, primary club notices confirm Danns resigned and Duffy played for Tranmere Rovers:  stadium appearance is not an international debut; rebound contribution is not a credited assist; captaincy requires explicit source evidence; playing together does not establish shared childhood; remove literal formatting, author bio, newspaper ratings and unsourced given names'})
            corrected += 1
            logger.info('[public_index] corrected confirmed football prose article=%s', article.id)
        if not tax.public_ok and article.id in {22202, 22204, 22205, 22207}:
            if _recover_confirmed_language_hold(db, article, tax):
                corrected += 1
            else:
                continue
        currency_changes = _correct_confirmed_chema_currency(article)
        if currency_changes:
            db.add(article)
            from bot.news_learning import record_incident
            record_incident(db, reason_code='untranslated_currency_unit',
                article_id=article.id, source_url=article.source_url, sport='football',
                phase='postpublish', status='auto_corrected', writer_provider='news-audit',
                writer_model='deterministic', details={'changes': currency_changes,
                    'evidence': 'French euro amounts rendered in English without changing currency or value'})
            corrected += 1
            logger.info('[public_index] corrected English currency units article=%s', article.id)
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
            from bot.news_learning import mark_auto_corrected
            from models import NewsIncident
            for incident in db.query(NewsIncident).filter(
                    NewsIncident.article_id == article.id, NewsIncident.reason_code == 'draft_placeholder',
                    NewsIncident.writer_provider == 'news-audit', NewsIncident.writer_model == 'deterministic',
                    NewsIncident.phase == 'postpublish', NewsIncident.status == 'open',
                    NewsIncident.confirmed.is_(False)).all():
                mark_auto_corrected(db, incident, note='Exact source-confirmed Taranto formatting correction; full public gates rechecked')
            from bot.news_image_http import news_image_is_reachable
            if news_image_is_reachable(article.image_url):
                persist_public_article(db, article, cache_row_to_resolution(tax), commit=False)
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
    from bot.dedupe import (titles_are_near_duplicate, confirmed_interview_key,
                           confirmed_football_report_key, same_report_window)

    from bot.news_report_similarity import draw_report_signature, same_draw_report

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution,
            Article.id,
            Article.title,
            func.coalesce(Article.ai_content, Article.content, Article.summary),
            Article.published_at,
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
    kept_interviews: dict[str, dict[str, int]] = {}
    kept_reports: dict[str, dict[int, tuple[str, Optional[datetime]]]] = {}
    kept_draws: dict[int, tuple[object, Optional[datetime]]] = {}
    token_index: dict[str, dict[str, set[int]]] = {}
    hidden = 0
    for tax, article_id, article_title, article_body, published_at in rows:
        sport = str(tax.resolved_sport or "")
        title = article_title or ""
        if not sport or not title:
            continue
        tokens = _title_tokens(title)
        sport_titles = kept_titles.setdefault(sport, {})
        sport_index = token_index.setdefault(sport, {})
        interview_key = confirmed_interview_key(article_body)
        sport_interviews = kept_interviews.setdefault(sport, {})
        report_key = confirmed_football_report_key(title, article_body) if sport == 'football' else None
        sport_reports = kept_reports.setdefault(sport, {})
        draw_report = draw_report_signature(title, article_body) if sport == 'football' else None

        def outside_report_window(kept_id):
            prior = sport_reports.get(kept_id)
            existing_draw = kept_draws.get(kept_id)
            if draw_report and existing_draw and not same_draw_report(draw_report, existing_draw[0], published_at, existing_draw[1]):
                return True
            return bool(report_key and prior and not same_report_window(prior[1], published_at))

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
        duplicate_id = sport_interviews.get(interview_key) if interview_key else None
        if duplicate_id is None and report_key:
            duplicate_id = next((kept_id for kept_id, (key, stamp) in sport_reports.items()
                                 if key == report_key and same_report_window(stamp, published_at)), None)
        if duplicate_id is None and draw_report:
            duplicate_id = next((kept_id for kept_id, (identity, stamp) in kept_draws.items()
                                 if same_draw_report(draw_report, identity, published_at, stamp)), None)
        for candidate_id in candidate_ids:
            if outside_report_window(candidate_id):
                continue
            other = sport_titles.get(candidate_id, "")
            if other and titles_are_near_duplicate(title, other):
                duplicate_id = candidate_id
                break
        if duplicate_id is None:
            from bot.textutil import normalize_title

            normalized = normalize_title(title)
            duplicate_id = next((
                kept_id for kept_id, other in sport_titles.items()
                if normalize_title(other) == normalized and not outside_report_window(kept_id)
            ), None)
        if duplicate_id is not None:
            tax.public_ok = False
            db.add(tax)
            # A plain public_ok=False is reversible by taxonomy/image repair.
            # Use the existing post-publication incident gate so maintenance
            # cannot resurrect the duplicate. No row or timestamp is deleted.
            from bot.news_learning import record_incident
            record_incident(db, article_id=article_id, sport=sport,
                reason_code='duplicate_story', phase='postpublish', status='open',
                writer_provider='news-audit', writer_model='deterministic',
                draft={'title': title, 'body': article_body or ''},
                details={'kept_article_id': duplicate_id,
                         'evidence': interview_key or report_key or ('same_participants_draw_scorers_window' if draw_report and duplicate_id in kept_draws else 'strict_headline_duplicate')})
            logger.info('[public_index] held duplicate article=%s kept_article=%s', article_id, duplicate_id)
            hidden += 1
            continue

        sport_titles[int(article_id)] = title
        if interview_key:
            sport_interviews[interview_key] = int(article_id)
        if report_key:
            sport_reports[int(article_id)] = (report_key, published_at)
        if draw_report:
            kept_draws[int(article_id)] = (draw_report, published_at)
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
    if RALLY_TITLE_RE.search(value):
        return 'motorsport'
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
