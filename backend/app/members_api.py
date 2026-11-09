"""Admin tools for project members; removing a member unassigns tasks atomically."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.auth import get_db, get_current_membership
from app.tasks import get_accessible_project

router = APIRouter(tags=["Project Members"])

class MemberAdd(BaseModel):
    user_id: int = Field(gt=0)


def _admin(user: dict):
    if user["role"] != "agency_admin":
        raise HTTPException(status_code=403, detail="Agency admin required")


@router.get("/projects/{project_id}/members")
def list_members(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    if user["role"] == "client_user":
        raise HTTPException(status_code=403, detail="Staff directory is not available to clients")
    get_accessible_project(db, user, project_id)
    rows = db.execute(text("""
        SELECT u.id AS user_id, u.name, u.email, m.role
        FROM public.project_members pm
        JOIN public.users u ON u.id = pm.user_id
        JOIN public.agency_memberships m
          ON m.user_id = pm.user_id AND m.agency_id = pm.agency_id
        WHERE pm.agency_id = :agency_id AND pm.project_id = :project_id
        ORDER BY u.id
    """), {"agency_id": user["agency_id"], "project_id": project_id}).mappings().all()
    return [dict(row) for row in rows]


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(project_id: int, payload: MemberAdd, db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    _admin(user)
    get_accessible_project(db, user, project_id)
    member = db.execute(text("""
        SELECT 1 FROM public.agency_memberships
        WHERE user_id = :user_id AND agency_id = :agency_id
          AND role IN ('agency_admin', 'agency_member')
    """), {"user_id": payload.user_id, "agency_id": user["agency_id"]}).first()
    if not member:
        raise HTTPException(status_code=400, detail="User is not agency staff for this agency")
    db.execute(text("""
        INSERT INTO public.project_members (agency_id, project_id, user_id)
        VALUES (:agency_id, :project_id, :user_id)
        ON CONFLICT (agency_id, project_id, user_id) DO NOTHING
    """), {"agency_id": user["agency_id"], "project_id": project_id, "user_id": payload.user_id})
    db.commit()
    return {"project_id": project_id, "user_id": payload.user_id, "assigned": True}


@router.delete("/projects/{project_id}/members/{member_user_id}")
def remove_member(project_id: int, member_user_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    _admin(user)
    get_accessible_project(db, user, project_id)
    membership = db.execute(text("""
        SELECT id FROM public.project_members
        WHERE agency_id = :agency_id AND project_id = :project_id
          AND user_id = :member_user_id
        FOR UPDATE
    """), {"agency_id": user["agency_id"], "project_id": project_id, "member_user_id": member_user_id}).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="Project member not found")
    # Tasks cannot retain assignees who are no longer project members.
    count = db.execute(text("""
        UPDATE public.tasks
        SET assignee_user_id = NULL
        WHERE agency_id = :agency_id AND project_id = :project_id
          AND assignee_user_id = :member_user_id
    """), {"agency_id": user["agency_id"], "project_id": project_id, "member_user_id": member_user_id}).rowcount
    db.execute(text("""
        DELETE FROM public.project_members
        WHERE agency_id = :agency_id AND project_id = :project_id
          AND user_id = :member_user_id
    """), {"agency_id": user["agency_id"], "project_id": project_id, "member_user_id": member_user_id})
    db.commit()
    return {"removed": True, "unassigned_tasks": count}
