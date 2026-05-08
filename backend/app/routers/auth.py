from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

HARDCODED_ADMIN_ID = "admin"
HARDCODED_ADMIN_PASSWORD = "admin123"
HARDCODED_ADMIN_EMAIL = "admin"


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected = password_hash.split("$", 1)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def to_user_response(user: models.AppUser) -> schemas.UserResponse:
    return schemas.UserResponse(user_id=user.user_id, email=user.email, role=user.role, dob=user.dob, location=user.location)


def record_activity(db: Session, user: Optional[models.AppUser], action: str, login_time: Optional[datetime] = None) -> None:
    db.add(models.UserActivityLog(
        user_id=user.user_id if user else None,
        user_email=user.email if user else None,
        role=user.role if user else None,
        login_time=login_time,
        action_performed=action,
    ))


def minimum_dob_for_signup() -> date:
    today = date.today()
    try:
        return today.replace(year=today.year - 20)
    except ValueError:
        return today.replace(year=today.year - 20, day=28)


def get_or_create_hardcoded_admin(db: Session) -> models.AppUser:
    user = db.scalar(select(models.AppUser).where(models.AppUser.email == HARDCODED_ADMIN_EMAIL))
    if user:
        user.password_hash = hash_password(HARDCODED_ADMIN_PASSWORD)
        user.role = "admin"
        return user
    user = models.AppUser(
        email=HARDCODED_ADMIN_EMAIL,
        password_hash=hash_password(HARDCODED_ADMIN_PASSWORD),
        dob=date(1970, 1, 1),
        location="System",
        role="admin",
    )
    db.add(user)
    db.flush()
    return user


@router.post("/signup", response_model=schemas.AuthResponse)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    if payload.dob > minimum_dob_for_signup():
        raise HTTPException(status_code=400, detail="DOB must be at least 20 years ago")

    email = payload.email.lower()
    existing = db.scalar(select(models.AppUser).where(models.AppUser.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = models.AppUser(
        email=email,
        password_hash=hash_password(payload.password),
        dob=payload.dob,
        location=payload.location,
        role=payload.role,
    )
    db.add(user)
    db.flush()
    token = secrets.token_urlsafe(32)
    db.add(models.UserSession(user_id=user.user_id, token=token))
    record_activity(db, user, "SIGNUP", datetime.utcnow())
    db.commit()
    db.refresh(user)
    return schemas.AuthResponse(token=token, user=to_user_response(user))


@router.post("/login", response_model=schemas.AuthResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    login_id = payload.email.strip().lower()
    if login_id == HARDCODED_ADMIN_ID:
        if payload.password != HARDCODED_ADMIN_PASSWORD:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = get_or_create_hardcoded_admin(db)
    else:
        user = db.scalar(select(models.AppUser).where(models.AppUser.email == login_id))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    login_time = datetime.utcnow()
    db.add(models.UserSession(user_id=user.user_id, token=token))
    record_activity(db, user, "LOGIN", login_time)
    db.commit()
    return schemas.AuthResponse(token=token, user=to_user_response(user))


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> models.AppUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    token = authorization.removeprefix("Bearer ").strip()
    session = db.scalar(
        select(models.UserSession)
        .where(models.UserSession.token == token)
        .where(models.UserSession.is_active.is_(True))
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired login")

    session.last_seen_at = datetime.utcnow()
    user = session.user
    if request.url.path != "/api/v1/admin/audit-logs":
        record_activity(db, user, f"{request.method} {request.url.path}")
    db.commit()
    return user


@router.get("/me", response_model=schemas.UserResponse)
def me(user: models.AppUser = Depends(get_current_user)):
    return to_user_response(user)
