"""Cookie-session auth. No paid identity provider. Passwords are PBKDF2 hashed."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models import SavedArticle, SocialIdentity, User, UserFavorite, UserSession
from editorial import sanitize_title

SESSION_COOKIE = "ninko_session"
CSRF_COOKIE = "ninko_csrf"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 210000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_LANGS = ("en", "sr", "es", "de", "fr", "it", "pt")

_rate_hits: dict = {}

router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, key: str, limit: int, window: int) -> None:
    now = time.time()
    bucket = f"{_client_ip(request)}:{key}"
    hits = [stamp for stamp in _rate_hits.get(bucket, []) if now - stamp < window]
    if len(hits) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    hits.append(now)
    _rate_hits[bucket] = hits[-limit:]


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def validate_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not EMAIL_RE.match(value) or len(value) > 320:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    return value


def validate_password(password: str) -> str:
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if password.isdigit():
        raise HTTPException(status_code=400, detail="Password cannot be only numbers.")
    return password


def _https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def _cookie_flags(request: Request, httponly: bool) -> dict:
    if _https(request):
        return {"httponly": httponly, "secure": True, "samesite": "none", "path": "/"}
    return {"httponly": httponly, "secure": False, "samesite": "lax", "path": "/"}


def set_csrf_cookie(response: Response, request: Request, token: Optional[str] = None) -> str:
    token = token or secrets.token_urlsafe(24)
    response.set_cookie(CSRF_COOKIE, token, max_age=SESSION_DAYS * 86400, **_cookie_flags(request, False))
    return token


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
    )
    db.add(row)
    db.commit()
    return raw


def public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role or "user",
        "preferred_language": user.preferred_language or "en",
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def load_user_from_request(request: Request, db: Session) -> Optional[User]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    row = (
        db.query(UserSession)
        .filter(UserSession.token_hash == hash_token(raw))
        .first()
    )
    if not row or row.expires_at < datetime.utcnow():
        return None
    return db.query(User).filter(User.id == row.user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = load_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get("x-csrf-token") or ""
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Invalid security token.")


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str = Field(min_length=2, max_length=80)


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    preferred_language: Optional[str] = None


class FavoritesIn(BaseModel):
    sports: list[str] = []
    leagues: list[str] = []
    teams: list[str] = []


@router.get("/csrf")
def csrf_token(request: Request, response: Response):
    token = set_csrf_cookie(response, request)
    return {"csrf": token}


@router.get("/session")
def session_status(request: Request, response: Response, db: Session = Depends(get_db)):
    token = set_csrf_cookie(response, request, request.cookies.get(CSRF_COOKIE))
    user = load_user_from_request(request, db)
    return {"user": public_user(user) if user else None, "csrf": token}


@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "register", 8, 600)
    require_csrf(request)
    email = validate_email(payload.email)
    password = validate_password(payload.password)
    name = sanitize_title(payload.display_name) or payload.display_name.strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=name[:80],
        role="user",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    raw = create_session(db, user)
    response.set_cookie(SESSION_COOKIE, raw, max_age=SESSION_DAYS * 86400, **_cookie_flags(request, True))
    csrf = set_csrf_cookie(response, request)
    return {"user": public_user(user), "csrf": csrf}


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(request, "login", 12, 600)
    require_csrf(request)
    email = validate_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    raw = create_session(db, user)
    response.set_cookie(SESSION_COOKIE, raw, max_age=SESSION_DAYS * 86400, **_cookie_flags(request, True))
    csrf = set_csrf_cookie(response, request)
    return {"user": public_user(user), "csrf": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        db.query(UserSession).filter(UserSession.token_hash == hash_token(raw)).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    set_csrf_cookie(response, request)
    return {"ok": True}


@router.patch("/profile")
def update_profile(
    payload: ProfileIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_csrf(request)
    if payload.display_name:
        user.display_name = sanitize_title(payload.display_name)[:80]
    if payload.preferred_language:
        if payload.preferred_language not in ALLOWED_LANGS:
            raise HTTPException(status_code=400, detail="Unsupported language.")
        user.preferred_language = payload.preferred_language
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": public_user(user)}


def _normalize_sport_value(value: str) -> str:
    from sports_registry.sports import canonical_sport_slug, get_sport

    key = canonical_sport_slug(value) or str(value).strip().lower()[:120]
    if key == "other":
        return "other"
    if get_sport(key):
        return key
    return str(value)[:120]


def _normalize_league_value(value: str) -> str:
    from bot.taxonomy import COMPETITIONS, canonical_competition_key, scoped_competition_id

    key = canonical_competition_key(value)
    meta = COMPETITIONS.get(key) if key else None
    sport = meta.get("sport") if meta else None
    return scoped_competition_id(sport, key) or str(value)[:120]


def _fav_payload(db: Session, user: User) -> dict:
    rows = db.query(UserFavorite).filter(UserFavorite.user_id == user.id).all()
    out = {"sports": [], "leagues": [], "teams": []}
    for row in rows:
        value = row.value
        if row.kind == "leagues":
            value = _normalize_league_value(value)
        if row.kind == "sports":
            value = _normalize_sport_value(value)
        if row.kind in out and value not in out[row.kind]:
            out[row.kind].append(value)
    return out


@router.get("/favorites")
def get_favorites(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _fav_payload(db, user)


@router.put("/favorites")
def replace_favorites(
    payload: FavoritesIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_csrf(request)
    next_state = {
        "sports": sorted(
            {
                _normalize_sport_value(item)
                for item in (payload.sports or [])
                if item
            }
        ),
        "leagues": sorted(
            {
                _normalize_league_value(item)
                for item in (payload.leagues or [])
                if item
            }
        ),
        "teams": sorted({str(item) for item in (payload.teams or []) if item}),
    }
    db.query(UserFavorite).filter(UserFavorite.user_id == user.id).delete()
    for kind, values in next_state.items():
        for value in values:
            if not value:
                continue
            db.add(UserFavorite(user_id=user.id, kind=kind, value=str(value)[:120]))
    db.commit()
    return next_state


@router.get("/saved")
def list_saved(db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app import serialize_article
    from models import Article
    from public_index import load_cached_resolution

    rows = (
        db.query(SavedArticle, Article)
        .join(Article, Article.id == SavedArticle.article_id)
        .filter(SavedArticle.user_id == user.id)
        .order_by(SavedArticle.created_at.desc())
        .all()
    )
    return [serialize_article(article, resolution=load_cached_resolution(db, article)) for _, article in rows]


@router.put("/saved/{article_id}")
def save_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_csrf(request)
    from models import Article

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    exists = (
        db.query(SavedArticle)
        .filter(SavedArticle.user_id == user.id, SavedArticle.article_id == article_id)
        .first()
    )
    if not exists:
        db.add(SavedArticle(user_id=user.id, article_id=article_id))
        db.commit()
    return {"saved": True}


@router.delete("/saved/{article_id}")
def unsave_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_csrf(request)
    db.query(SavedArticle).filter(
        SavedArticle.user_id == user.id, SavedArticle.article_id == article_id
    ).delete()
    db.commit()
    return {"saved": False}


def _provider_enabled(name: str) -> bool:
    if name == "google":
        return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))
    if name == "facebook":
        return bool(os.getenv("FACEBOOK_APP_ID") and os.getenv("FACEBOOK_APP_SECRET"))
    return False


@router.get("/providers")
def auth_providers():
    return {
        "password": True,
        "google": _provider_enabled("google"),
        "facebook": _provider_enabled("facebook"),
        "google_callback": os.getenv("GOOGLE_REDIRECT_URI") or "/auth/google/callback",
        "facebook_callback": os.getenv("FACEBOOK_REDIRECT_URI") or "/auth/facebook/callback",
    }


OAUTH_STATE_COOKIE = "ninko_oauth_state"


def _unusable_password() -> str:
    return hash_password(secrets.token_urlsafe(32))


def _set_oauth_state(response: Response, request: Request) -> str:
    state = secrets.token_urlsafe(24)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        **_cookie_flags(request, True),
    )
    return state


def _check_oauth_state(request: Request, state: Optional[str]) -> None:
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected or not state or not hmac.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid sign-in state.")


def _json_request(url: str, data: Optional[bytes] = None, headers: Optional[dict] = None) -> dict:
    from urllib.request import Request as UrlRequest, urlopen

    req = UrlRequest(url, data=data, headers=headers or {"Accept": "application/json"})
    with urlopen(req, timeout=12) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))


def _finish_social_login(
    db: Session,
    response: Response,
    request: Request,
    *,
    provider: str,
    provider_user_id: str,
    email: Optional[str],
    email_verified: bool,
    display_name: str,
):
    from sqlalchemy import func

    identity = (
        db.query(SocialIdentity)
        .filter(
            SocialIdentity.provider == provider,
            SocialIdentity.provider_user_id == str(provider_user_id),
        )
        .first()
    )
    if not provider_user_id:
        raise HTTPException(status_code=401, detail="Social sign-in failed.")
    user = db.query(User).filter(User.id == identity.user_id).first() if identity else None
    if user is None and email_verified and email:
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user:
            db.add(
                SocialIdentity(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=str(provider_user_id),
                )
            )
    if user is None:
        placeholder = email if (email_verified and email) else f"{provider}-{provider_user_id}@users.ninkosports.invalid"
        existing = db.query(User).filter(func.lower(User.email) == placeholder.lower()).first()
        user = existing or User(
            email=placeholder,
            password_hash=_unusable_password(),
            display_name=(display_name or provider.title())[:80],
            email_verified=bool(email_verified and email),
        )
        if existing is None:
            db.add(user)
            db.flush()
        db.add(
            SocialIdentity(
                user_id=user.id,
                provider=provider,
                provider_user_id=str(provider_user_id),
            )
        )
    db.commit()
    raw = create_session(db, user)
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=SESSION_DAYS * 86400,
        **_cookie_flags(request, True),
    )
    csrf = set_csrf_cookie(response, request)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return {"user": public_user(user), "csrf": csrf}


@router.get("/google/start")
def google_start(request: Request, response: Response):
    if not _provider_enabled("google"):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    redirect = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    from urllib.parse import urlencode

    state = _set_oauth_state(response, request)
    params = urlencode(
        {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
        }
    )
    return {"authorize_url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"}


@router.get("/google/callback")
def google_callback(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    code: Optional[str] = None,
    state: Optional[str] = None,
):
    if not _provider_enabled("google"):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    _check_oauth_state(request, state)
    redirect = os.getenv("GOOGLE_REDIRECT_URI")
    from urllib.parse import urlencode

    token = _json_request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "code": code,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access = token.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Google sign-in failed.")
    profile = _json_request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access}", "Accept": "application/json"},
    )
    return _finish_social_login(
        db,
        response,
        request,
        provider="google",
        provider_user_id=str(profile.get("sub") or ""),
        email=profile.get("email"),
        email_verified=bool(profile.get("email_verified")),
        display_name=profile.get("name") or "Google user",
    )


@router.get("/facebook/start")
def facebook_start(request: Request, response: Response):
    if not _provider_enabled("facebook"):
        raise HTTPException(status_code=503, detail="Facebook login is not configured.")
    redirect = os.getenv("FACEBOOK_REDIRECT_URI")
    if not redirect:
        raise HTTPException(status_code=503, detail="Facebook login is not configured.")
    from urllib.parse import urlencode

    state = _set_oauth_state(response, request)
    params = urlencode(
        {
            "client_id": os.getenv("FACEBOOK_APP_ID"),
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "email,public_profile",
            "state": state,
        }
    )
    return {"authorize_url": f"https://www.facebook.com/v21.0/dialog/oauth?{params}"}


@router.get("/facebook/callback")
def facebook_callback(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    code: Optional[str] = None,
    state: Optional[str] = None,
):
    if not _provider_enabled("facebook"):
        raise HTTPException(status_code=503, detail="Facebook login is not configured.")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    _check_oauth_state(request, state)
    redirect = os.getenv("FACEBOOK_REDIRECT_URI")
    from urllib.parse import urlencode

    token = _json_request(
        "https://graph.facebook.com/v21.0/oauth/access_token?"
        + urlencode(
            {
                "client_id": os.getenv("FACEBOOK_APP_ID"),
                "client_secret": os.getenv("FACEBOOK_APP_SECRET"),
                "redirect_uri": redirect,
                "code": code,
            }
        )
    )
    access = token.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Facebook login failed.")
    profile = _json_request(
        "https://graph.facebook.com/me?"
        + urlencode({"fields": "id,name,email", "access_token": access})
    )
    return _finish_social_login(
        db,
        response,
        request,
        provider="facebook",
        provider_user_id=str(profile.get("id") or ""),
        email=profile.get("email"),
        email_verified=False,
        display_name=profile.get("name") or "Facebook user",
    )
