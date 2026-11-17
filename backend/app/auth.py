"""Optional team mode: owner account, invites, logins and roles.

Team mode is OFF until an owner is created (Settings → Team → Set up team). While off, the app behaves
exactly as before (single local user). When on, every /api request needs a valid session cookie (or the
legacy access token / a member API flow), and viewers are read-only.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LoginSession, Member
from app.db.session import get_db, session_scope

COOKIE = "shelfcraft_session"
SESSION_DAYS = 14
INVITE_DAYS = 7
ROLES = ("owner", "admin", "editor", "viewer")
PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/accept-invite"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, dk = stored.split("$")
    test = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(test.hex(), dk)


def team_mode_enabled(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(Member).where(Member.role == "owner", Member.status == "active")) or 0) > 0


def member_from_request(db: Session, request: Request) -> Member | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.scalar(select(LoginSession).where(LoginSession.token_hash == _sha(token)))
    if s is None:
        return None
    exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    m = db.get(Member, s.member_id)
    return m if m and m.status == "active" else None


def check_request(request: Request) -> tuple[bool, str | None, int]:
    """Called by middleware. Returns (allowed, error_message, status)."""
    path = request.url.path
    if not path.startswith("/api") or path in PUBLIC_PATHS:
        return True, None, 200
    if path.startswith("/api/share/") and request.method in ("GET", "HEAD"):
        return True, None, 200  # public share links (token-checked in the share router)
    with session_scope() as db:
        if not team_mode_enabled(db):
            return True, None, 200
        m = member_from_request(db, request)
        if m is None:
            return False, "Please sign in", 401
        if m.role == "viewer" and request.method not in ("GET", "HEAD", "OPTIONS") and not path.startswith("/api/auth/"):
            return False, "Viewers can't make changes — ask an admin for editor access", 403
        if path.startswith("/api/members") and m.role not in ("owner", "admin") and request.method != "GET":
            return False, "Only owners and admins can manage members", 403
    return True, None, 200


def _start_session(db: Session, m: Member, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(member_id=m.id, token_hash=_sha(token), expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
    m.last_login_at = datetime.now(timezone.utc)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_DAYS * 86400, path="/")


def member_out(m: Member) -> dict[str, Any]:
    return {"id": m.id, "name": m.name, "email": m.email, "role": m.role, "status": m.status,
            "last_login_at": m.last_login_at, "created_at": m.created_at}


router = APIRouter(tags=["auth"])


@router.get("/auth/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    enabled = team_mode_enabled(db)
    m = member_from_request(db, request) if enabled else None
    return {"team_mode": enabled, "signed_in": bool(m), "member": member_out(m) if m else None}


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=200)


@router.post("/auth/setup", status_code=201)
def setup(body: SetupIn, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    if team_mode_enabled(db):
        raise HTTPException(409, "team is already set up")
    if not EMAIL.match(body.email):
        raise HTTPException(422, "enter a valid email")
    m = Member(name=body.name, email=body.email.lower(), role="owner", status="active", password_hash=hash_password(body.password))
    db.add(m)
    db.flush()
    _start_session(db, m, response)
    return member_out(m)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.scalar(select(Member).where(Member.email == body.email.lower()))
    if m is None or m.status != "active" or not verify_password(body.password, m.password_hash):
        raise HTTPException(401, "wrong email or password")
    _start_session(db, m, response)
    return member_out(m)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    token = request.cookies.get(COOKIE)
    if token:
        s = db.scalar(select(LoginSession).where(LoginSession.token_hash == _sha(token)))
        if s:
            db.delete(s)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class AcceptIn(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


@router.post("/auth/accept-invite")
def accept(body: AcceptIn, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.scalar(select(Member).where(Member.invite_token_hash == _sha(body.token)))
    if m is None or m.status != "invited":
        raise HTTPException(404, "invite not found or already used")
    exp = m.invite_expires_at.replace(tzinfo=timezone.utc) if m.invite_expires_at and not m.invite_expires_at.tzinfo else m.invite_expires_at
    if exp and exp < datetime.now(timezone.utc):
        raise HTTPException(410, "invite expired — ask for a new one")
    m.name, m.password_hash, m.status, m.invite_token_hash = body.name, hash_password(body.password), "active", None
    _start_session(db, m, response)
    return member_out(m)


@router.get("/members")
def members(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [member_out(m) for m in db.scalars(select(Member).order_by(Member.created_at))]


class InviteIn(BaseModel):
    email: str = Field(max_length=255)
    name: str = Field(default="", max_length=120)
    role: str = Field(default="editor", pattern="^(admin|editor|viewer)$")


@router.post("/members", status_code=201)
def invite(body: InviteIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not team_mode_enabled(db):
        raise HTTPException(422, "set up the team (owner account) first")
    if not EMAIL.match(body.email):
        raise HTTPException(422, "enter a valid email")
    if db.scalar(select(Member).where(Member.email == body.email.lower())):
        raise HTTPException(409, "that email is already a member")
    token = secrets.token_urlsafe(24)
    m = Member(name=body.name or body.email.split("@")[0], email=body.email.lower(), role=body.role, status="invited",
               invite_token_hash=_sha(token), invite_expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS))
    db.add(m)
    db.flush()
    # The link is shown to the inviter to share however they like; Shelfcraft sends no email.
    return {**member_out(m), "invite_path": f"/join?token={token}", "expires_in_days": INVITE_DAYS}


class MemberPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|editor|viewer)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


@router.patch("/members/{member_id}")
def update_member(member_id: str, body: MemberPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    m = db.get(Member, member_id)
    if m is None:
        raise HTTPException(404, "member not found")
    if m.role == "owner":
        raise HTTPException(422, "the owner can't be changed here")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(m, k, v)
    if m.status == "disabled":
        for s in db.scalars(select(LoginSession).where(LoginSession.member_id == m.id)):
            db.delete(s)
    return member_out(m)
