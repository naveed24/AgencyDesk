"""JWT identity with per-request membership validation (role never trusted from JWT)."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str
    agency_id: int = Field(gt=0)


class SwitchRequest(BaseModel):
    agency_id: int = Field(gt=0)


def get_db():
    with SessionLocal() as db:
        yield db


def _issue_token(user_id: int, agency_id: int) -> dict:
    expiry = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": str(user_id), "agency_id": agency_id, "exp": expiry},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(text("""
        SELECT u.id, u.password_hash, m.agency_id
        FROM public.users u
        JOIN public.agency_memberships m ON m.user_id = u.id
        WHERE u.email = :email AND m.agency_id = :agency_id
    """), {"email": data.email.strip().lower(), "agency_id": data.agency_id}).mappings().first()
    if user is None or not password_hash.verify(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials or agency access")
    return _issue_token(user["id"], user["agency_id"])


def get_current_membership(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "agency_id", "exp"]},
        )
        user_id = int(payload["sub"])
        agency_id = int(payload["agency_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_id <= 0 or agency_id <= 0:
        raise HTTPException(status_code=401, detail="Invalid identity")
    membership = db.execute(text("""
        SELECT u.id AS user_id, u.name, u.email, m.agency_id, m.role,
               a.name AS agency_name
        FROM public.users u
        JOIN public.agency_memberships m ON m.user_id = u.id
        JOIN public.agencies a ON a.id = m.agency_id
        WHERE u.id = :user_id AND m.agency_id = :agency_id
    """), {"user_id": user_id, "agency_id": agency_id}).mappings().first()
    if membership is None:
        raise HTTPException(status_code=401, detail="Membership not found")
    return dict(membership)


@router.get("/me")
def me(user: dict = Depends(get_current_membership)):
    return user


@router.get("/my-agencies")
def my_agencies(
    user: dict = Depends(get_current_membership), db: Session = Depends(get_db)
):
    rows = db.execute(text("""
        SELECT m.agency_id, a.name AS agency_name, m.role
        FROM public.agency_memberships m
        JOIN public.agencies a ON a.id = m.agency_id
        WHERE m.user_id = :user_id ORDER BY a.name
    """), {"user_id": user["user_id"]}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/switch")
def switch_agency(data: SwitchRequest,
                  user: dict = Depends(get_current_membership),
                  db: Session = Depends(get_db)):
    found = db.execute(text("""
        SELECT 1 FROM public.agency_memberships
        WHERE user_id = :uid AND agency_id = :aid
    """), {"uid": user["user_id"], "aid": data.agency_id}).first()
    if not found:
        raise HTTPException(status_code=403, detail="No membership in that agency")
    return _issue_token(user["user_id"], data.agency_id)
