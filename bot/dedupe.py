"""Conservative duplicate detection for NEW articles."""

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session, load_only

from models import Article
from .textutil import normalize_title
from .news_policy import news_source_identity


def unprocessed_source_items(db: Session, items: list) -> list:
    """Remove known source identities before editorial slots are allocated.

    One exact lookup plus the same bounded canonical history used at ingest.
    Includes held Article rows: rediscovery must not resurrect or rewrite them.
    The final ingest duplicate checks remain authoritative.
    """
    urls = {str(item.get('url') or '') for item in items if item.get('url')}
    if not urls:
        return items
    exact = db.query(Article.source_url, Article.external_id).filter(
        (Article.source_url.in_(urls)) | (Article.external_id.in_(urls))
    ).all()
    recent = db.query(Article.source_url, Article.external_id).filter(
        Article.source_url.isnot(None)
    ).order_by(Article.id.desc()).limit(500).all()
    known = {
        news_source_identity(value)
        for source, external in [*exact, *recent]
        for value in (source, external)
        if value and news_source_identity(value)
    }
    return [item for item in items if news_source_identity(item.get('url')) not in known]


def existing_by_url(db: Session, source_url: str) -> Optional[Article]:
    if not source_url:
        return None
    exact = (
        db.query(Article)
        .filter(
            (Article.external_id == source_url) | (Article.source_url == source_url)
        )
        .first()
    )
    if exact is not None:
        return exact
    target = news_source_identity(source_url)
    if not target:
        return None
    recent = (
        db.query(Article)
        .options(load_only(Article.id, Article.source_url, Article.external_id))
        .filter(Article.source_url.isnot(None))
        .order_by(Article.id.desc())
        .limit(500)
        .all()
    )
    for article in recent:
        if news_source_identity(article.source_url or article.external_id or "") == target:
            return article
    return None


def _title_tokens(value: str) -> set[str]:
    stop = {
        "the","and","for","with","from","before","into","over","under","will",
        "news","latest","update","report","live","says","set","new","sport",
    }
    aliases = {
        "confirms": "confirm", "confirmed": "confirm", "confirming": "confirm",
        "following": "after",
        "clash": "match", "game": "match", "fixture": "match",
        "beats": "beat", "beaten": "beat",
        "wins": "win", "won": "win",
        "signs": "sign", "signed": "sign",
        "joins": "join", "joined": "join",
    }
    tokens = set()
    for token in re.findall(r"[a-z0-9]{3,}", normalize_title(value or "")):
        if token in stop:
            continue
        tokens.add(aliases.get(token, token))
    return tokens


def title_similarity(left: str, right: str) -> float:
    """Conservative cross-source headline similarity.

    Exact normalized titles are 1.0. Otherwise combine character similarity and
    significant-token overlap. This is deliberately strict to avoid collapsing
    genuinely different stories about the same club/player.
    """
    a = normalize_title(left or "")
    b = normalize_title(right or "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    chars = SequenceMatcher(None, a, b).ratio()
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return chars
    shared = len(ta & tb)
    union = len(ta | tb)
    jaccard = shared / max(1, union)
    containment = shared / max(1, min(len(ta), len(tb)))
    # Strong character agreement or a near-contained significant-token set.
    if chars >= 0.90:
        return chars
    if shared >= 4 and jaccard >= 0.72:
        return max(chars, jaccard)
    if shared >= 5 and containment >= 0.86 and chars >= 0.72:
        return max(chars, containment)
    return max(chars, jaccard * 0.92)


def _confirmed_financial_verdict(title: str):
    """A narrow repeated-announcement family, not all news about one club.

    Confirmed overnight: several publishers rewrote the same Premier League
    finding with different word order and counts. Appeals, reactions, penalties
    and predictions are separate developments and must not be collapsed here.
    Unknown clubs/jurisdictions retain ordinary conservative title matching.
    """
    value = normalize_title(title or '')
    if not all(re.search(pattern, value) for pattern in (
        r'\bpremier league\b', r'\bfinancial\b', r'\bguilty\b',
        r'\b(?:finds|found|declares|declared|rules|ruled)\b',
    )):
        return None
    if re.search(r'\b(?:not|if|could|may|might|whether|awaits?|appeals?|denies|denial|innocence|'
                 r'reacts?|reaction|response|sanctions?|points?|fines?|relegation|damages|'
                 r'revelations?|leaked|ceo|owner|before|after)\b', value):
        return None
    from .taxonomy import TEAMS
    clubs = {alias for team in TEAMS if team.get('sport') == 'football'
             for alias in team.get('aliases', [])
             if len(alias) >= 5 and re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', value)}
    return ('premier-league-financial-verdict', next(iter(clubs))) if len(clubs) == 1 else None


def titles_are_near_duplicate(left: str, right: str) -> bool:
    left_verdict = _confirmed_financial_verdict(left)
    right_verdict = _confirmed_financial_verdict(right)
    if left_verdict is not None or right_verdict is not None:
        # A one-word negation, different club or appeal can still have a very
        # similar headline. Do not let fuzzy matching erase that distinction.
        return left_verdict == right_verdict
    return title_similarity(left, right) >= 0.86


def confirmed_interview_key(body: str):
    """One audited repeated interview, despite English/Serbian name spelling.

    All independent details must agree. A new injury, transfer, fixture preview
    or another player's interview never matches just because the club is shared.
    Callers restrict comparisons to their existing recent-News window.
    """
    value = ''.join(ch for ch in unicodedata.normalize('NFKD', body or '')
                    if not unicodedata.combining(ch)).casefold()
    markers = (
        r'\b(?:boakye|boaci)\b', r'\b(?:red star|crvena zvezda)\b',
        r'\bmilunovic\b', r'\bbukari\b', r'\bivanic\b',
        r'\bpenalties\b', r'\bbench\b', r'\bminor injury\b',
        r'\bunity\b', r'\bvictory\b',
    )
    if all(re.search(pattern, value) for pattern in markers):
        return 'boakye-copenhagen-retrospective-interview'
    return None


def confirmed_football_report_key(title: str, body: str):
    """Audited England/Czechia recap family, never a fixture/result authority.

    The headline must report the same win and the copy must contain all five
    named participants plus the dismissal. Reactions, injuries, youth/women's
    matches and different scores remain separate. Callers also require source
    publication times within 24 hours; this cannot join rematches/seasons.
    """
    def plain(value):
        return ''.join(ch for ch in unicodedata.normalize('NFKD', value or '')
                       if not unicodedata.combining(ch)).casefold()

    headline, copy = plain(title), plain(body)
    if not re.match(r'^england\b.{0,35}\b(?:beats?|defeats?|wins?|earns?|secure[sd]?)\b', headline):
        return None
    if not all(re.search(p, headline) for p in (
        r'\bczech(?:ia| republic)\b', r'\bnations league\b',
    )):
        return None
    if re.search(r'\b(?:women\w*|youth|under[ -]?\d+|u\d+|says?|react\w*|'
                 r'injur\w*|appeal\w*|denies|preview|could|might|not|no)\b', headline):
        return None
    scores = re.findall(r'(?<![\w\d-])(\d{1,2})[:–-](\d{1,2})(?![\w\d-])', headline)
    if any(score != ('2', '0') for score in scores):
        return None
    if not all(re.search(p, copy) for p in (
        r'\banthony gordon\b', r'\bharry kane\b', r'\bpavel sulc\b',
        r'\belliot anderson\b', r'\b(?:trent )?alexander-arnold\b', r'\bred card\b',
    )):
        return None
    return 'england-czechia-nations-league-gordon-kane-sulc'


def same_report_window(left: Optional[datetime], right: Optional[datetime]) -> bool:
    if left is None or right is None:
        return False
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return abs(utc(left) - utc(right)) <= timedelta(hours=24)


def existing_near_duplicate(
    db: Session,
    title: str,
    published_at: Optional[datetime],
    *,
    body: Optional[str] = None,
) -> Optional[Article]:
    key = normalize_title(title)
    if not key or len(key) < 16:
        return None

    window_start = None
    if published_at:
        window_start = published_at - timedelta(hours=48)

    interview_key = confirmed_interview_key(body) if body else None
    report_key = confirmed_football_report_key(title, body) if body else None
    columns = [Article.id, Article.title, Article.created_at]
    if interview_key or report_key:
        columns.extend((Article.ai_content, Article.content, Article.published_at))
    query = db.query(Article).options(load_only(*columns))
    if window_start:
        query = query.filter(Article.created_at >= window_start - timedelta(days=2))
    recent = query.order_by(Article.created_at.desc()).limit(400).all()
    for article in recent:
        existing = article.title or ""
        existing_report = (confirmed_football_report_key(existing, article.ai_content or article.content)
                           if report_key else None)
        if report_key and existing_report:
            if report_key == existing_report and same_report_window(published_at, article.published_at):
                return article
            # Fuzzy or exact headlines cannot undo the source-date boundary.
            continue
        if normalize_title(existing) == key or titles_are_near_duplicate(existing, title):
            return article
        if interview_key and confirmed_interview_key(article.ai_content or article.content) == interview_key:
            return article
    return None
