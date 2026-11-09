"""Project endpoints. Every query is tenant-scoped and role-filtered."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_membership, get_db

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    client_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    status: Literal["active", "completed", "archived"] = "active"

    @field_validator("name")
    @classmethod
    def strip_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Project name cannot be empty")
        return v


def access_condition(role: str) -> str:
    if role == "agency_admin":
        return ""
    if role == "agency_member":
        return """ AND EXISTS (
            SELECT 1 FROM public.project_members pm
            WHERE pm.project_id=p.id AND pm.agency_id=p.agency_id
              AND pm.user_id=:user_id
        ) """
    if role == "client_user":
        return """ AND EXISTS (
            SELECT 1 FROM public.client_memberships cm
            WHERE cm.client_id=p.client_id AND cm.agency_id=p.agency_id
              AND cm.user_id=:user_id
        ) """
    raise HTTPException(status_code=403, detail="Invalid membership role")


def get_accessible_project(db: Session, user: dict, project_id: int):
    row = db.execute(text("""
        SELECT p.id, p.agency_id, p.client_id, p.name, p.description,
               p.status, p.created_at
        FROM public.projects p
        WHERE p.id=:project_id AND p.agency_id=:agency_id
    """ + access_condition(user["role"])), {
        "project_id": project_id, "agency_id": user["agency_id"],
        "user_id": user["user_id"],
    }).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@router.get("")
def list_projects(db: Session = Depends(get_db),
                  user: dict = Depends(get_current_membership)):
    rows = db.execute(text("""
        SELECT p.id, p.agency_id, p.client_id, p.name, p.description,
               p.status, p.created_at
        FROM public.projects p
        WHERE p.agency_id=:agency_id
    """ + access_condition(user["role"]) + " ORDER BY p.id DESC"), {
        "agency_id": user["agency_id"], "user_id": user["user_id"]
    }).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{project_id}")
def read_project(project_id: int, db: Session = Depends(get_db),
                 user: dict = Depends(get_current_membership)):
    return get_accessible_project(db, user, project_id)


@router.post("", status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db),
                   user: dict = Depends(get_current_membership)):
    if user["role"] != "agency_admin":
        raise HTTPException(status_code=403, detail="Only agency admins can create projects")
    client = db.execute(text("""
        SELECT 1 FROM public.clients
        WHERE agency_id=:agency_id AND id=:client_id
    """), {"agency_id": user["agency_id"], "client_id": data.client_id}).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    try:
        row = db.execute(text("""
            INSERT INTO public.projects (agency_id, client_id, name, description, status)
            VALUES (:agency_id,:client_id,:name,:description,:status)
            RETURNING id,agency_id,client_id,name,description,status,created_at
        """), {"agency_id": user["agency_id"], **data.model_dump()}).mappings().one()
        result = dict(row)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project constraint violation")
