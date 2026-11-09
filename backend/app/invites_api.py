"""Concurrency-safe invitation resends and idempotent acceptance."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.auth import get_current_membership, get_db

router = APIRouter(prefix="/invitations", tags=["Invitations"])
hasher = PasswordHash.recommended()

class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: Literal["agency_admin", "agency_member", "client_user"]
    client_id: int | None = None

    @field_validator("email")
    @classmethod
    def email_normalized(cls, value):
        result = value.strip().lower()
        if "@" not in result or " " in result:
            raise ValueError("Invalid email")
        return result

class InvitationAccept(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)


@router.post("", status_code=201)
def create_or_resend_invite(payload: InvitationCreate, db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    if user["role"] != "agency_admin":
        raise HTTPException(status_code=403, detail="Agency admin required")
    if (payload.role == "client_user") != (payload.client_id is not None):
        raise HTTPException(status_code=422, detail="client_id required only for client users")
    if payload.client_id is not None:
        client = db.execute(text("""
            SELECT 1 FROM public.clients WHERE id = :client_id AND agency_id = :agency_id
        """), {"client_id": payload.client_id, "agency_id": user["agency_id"]}).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
    token = secrets.token_urlsafe(32)
    token_hash = sha256(token.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    # The partial UNIQUE index on (agency_id, lower(email)) WHERE pending
    # makes simultaneous resend requests update the same row, not duplicate it.
    row = db.execute(text("""
        INSERT INTO public.invitations
           (agency_id, client_id, email, role, token_hash, expires_at)
        VALUES (:agency_id, :client_id, :email, :role, :token_hash, :expires_at)
        ON CONFLICT (agency_id, (lower(email))) WHERE status = 'pending'
        DO UPDATE SET
            token_hash = EXCLUDED.token_hash,
            expires_at = EXCLUDED.expires_at,
            role = EXCLUDED.role,
            client_id = EXCLUDED.client_id
        RETURNING id, agency_id, client_id, email, role, expires_at
    """), {
        "agency_id": user["agency_id"],
        "client_id": payload.client_id,
        "email": payload.email,
        "role": payload.role,
        "token_hash": token_hash,
        "expires_at": expires,
    }).mappings().one()
    db.commit()
    # For this local demo, admins copy the token; a production app would email a link.
    return {**dict(row), "invite_token": token}


@router.post("/accept")
def accept_invite(payload: InvitationAccept, db: Session = Depends(get_db)):
    if not payload.token:
        raise HTTPException(status_code=400, detail="Missing invitation token")
    digest = sha256(payload.token.encode()).hexdigest()
    invite = db.execute(text("""
        SELECT id, agency_id, client_id, email, role, status, expires_at
        FROM public.invitations
        WHERE token_hash = :token_hash
        FOR UPDATE
    """), {"token_hash": digest}).mappings().first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite["status"] == "accepted":
        # Safe retry: do not create a second user or membership.
        return {"accepted": True, "already_accepted": True, "agency_id": invite["agency_id"]}
    if invite["status"] != "pending":
        raise HTTPException(status_code=409, detail="Invitation revoked")
    if invite["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation expired")

    user_row = db.execute(text("""
        SELECT id, password_hash FROM public.users WHERE lower(email) = :email FOR UPDATE
    """), {"email": invite["email"].lower()}).mappings().first()
    if user_row:
        # Token possession alone is not enough to take over an existing login.
        if not hasher.verify(payload.password, user_row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid account password")
        user_id = user_row["id"]
    else:
        new_user_id = db.execute(text("""
            INSERT INTO public.users (name, email, password_hash)
            VALUES (:name, :email, :hashed)
            ON CONFLICT (email) DO NOTHING
            RETURNING id
        """), {
            "name": payload.name.strip(), "email": invite["email"].lower(),
            "hashed": hasher.hash(payload.password),
        }).scalar_one_or_none()
        if new_user_id is not None:
            user_id = new_user_id
        else:
            # Another invitation may have created this global user concurrently.
            concurrent_user = db.execute(text("""
                SELECT id, password_hash FROM public.users
                WHERE email = :email FOR UPDATE
            """), {"email": invite["email"].lower()}).mappings().one()
            if not hasher.verify(payload.password, concurrent_user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid account password")
            user_id = concurrent_user["id"]

    db.execute(text("""
        INSERT INTO public.agency_memberships (user_id, agency_id, role)
        VALUES (:user_id, :agency_id, :role)
        ON CONFLICT (user_id, agency_id) DO UPDATE SET role = EXCLUDED.role
    """), {"user_id": user_id, "agency_id": invite["agency_id"], "role": invite["role"]})
    if invite["role"] == "client_user":
        db.execute(text("""
            INSERT INTO public.client_memberships (user_id, agency_id, client_id)
            VALUES (:user_id, :agency_id, :client_id)
            ON CONFLICT (agency_id, client_id, user_id) DO NOTHING
        """), {"user_id": user_id, "agency_id": invite["agency_id"], "client_id": invite["client_id"]})
    db.execute(text("""
        UPDATE public.invitations
        SET status = 'accepted', accepted_at = CURRENT_TIMESTAMP
        WHERE id = :id
    """), {"id": invite["id"]})
    db.commit()
    return {"accepted": True, "already_accepted": False,
            "agency_id": invite["agency_id"], "user_id": user_id}
