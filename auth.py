"""Cookie-session auth. No paid identity provider. Passwords are PBKDF2 hashed."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models import SavedArticle, User, UserFavorite, UserSession
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


def _fav_payload(db: Session, user: User) -> dict:
    rows = db.query(UserFavorite).filter(UserFavorite.user_id == user.id).all()
    out = {"sports": [], "leagues": [], "teams": []}
    for row in rows:
        if row.kind in out and row.value not in out[row.kind]:
            out[row.kind].append(row.value)
    return out


@router.get("/favorites")
def get_favorites(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _fav_payload(db, user)


@router.put("/favorites")
def merge_favorites(
    payload: FavoritesIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    require_csrf(request)
    existing = _fav_payload(db, user)
    merged = {
        "sports": sorted(set(existing["sports"] + list(payload.sports or []))),
        "leagues": sorted(set(existing["leagues"] + list(payload.leagues or []))),
        "teams": sorted(set(existing["teams"] + list(payload.teams or []))),
    }
    db.query(UserFavorite).filter(UserFavorite.user_id == user.id).delete()
    for kind, values in merged.items():
        for value in values:
            if not value:
                continue
            db.add(UserFavorite(user_id=user.id, kind=kind, value=str(value)[:120]))
    db.commit()
    return merged


@router.get("/saved")
def list_saved(db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app import serialize_article
    from models import Article

    rows = (
        db.query(SavedArticle, Article)
        .join(Article, Article.id == SavedArticle.article_id)
        .filter(SavedArticle.user_id == user.id)
        .order_by(SavedArticle.created_at.desc())
        .all()
    )
    return [serialize_article(article) for _, article in rows]


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
