"""Comments and time tracking guarded by parent-task access and visibility."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.auth import get_db, get_current_membership
from app.tasks import get_allowed_task
from app.projects import get_accessible_project

router = APIRouter(tags=["Comments & Time Tracking"])


class CommentCreate(BaseModel):
    content: str = Field(min_length=1)
    is_client_visible: bool = False

    @field_validator("content")
    @classmethod
    def strip_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Comment must not be empty")
        return v


class TimeEntryCreate(BaseModel):
    duration_minutes: int = Field(gt=0, le=1440)
    note: str | None = None
    entry_date: date | None = None


@router.get("/tasks/{task_id}/comments")
def list_comments(task_id: int, db: Session = Depends(get_db),
                  user: dict = Depends(get_current_membership)):
    get_allowed_task(db, user, task_id)
    visible = " AND is_client_visible=TRUE" if user["role"] == "client_user" else ""
    rows = db.execute(text("""
        SELECT id,task_id,user_id,content,is_client_visible,created_at
        FROM public.comments WHERE agency_id=:agency_id AND task_id=:task_id
    """ + visible + " ORDER BY created_at,id"), {
        "agency_id": user["agency_id"], "task_id": task_id
    }).mappings().all()
    return [dict(r) for r in rows]


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: int, data: CommentCreate,
                db: Session = Depends(get_db),
                user: dict = Depends(get_current_membership)):
    get_allowed_task(db, user, task_id)
    visible = True if user["role"] == "client_user" else data.is_client_visible
    row = db.execute(text("""
        INSERT INTO public.comments (agency_id,task_id,user_id,content,is_client_visible)
        VALUES (:agency_id,:task_id,:user_id,:content,:visible)
        RETURNING id,task_id,user_id,content,is_client_visible,created_at
    """), {"agency_id": user["agency_id"], "task_id": task_id,
           "user_id": user["user_id"], "content": data.content,
           "visible": visible}).mappings().one()
    db.commit()
    return dict(row)


@router.post("/tasks/{task_id}/time-entries", status_code=201)
def log_time(task_id: int, data: TimeEntryCreate,
             db: Session = Depends(get_db),
             user: dict = Depends(get_current_membership)):
    if user["role"] not in ("agency_admin", "agency_member"):
        raise HTTPException(status_code=403, detail="Only agency staff can log time")
    get_allowed_task(db, user, task_id)
    row = db.execute(text("""
        INSERT INTO public.time_entries (
          agency_id,task_id,user_id,duration_minutes,note,entry_date
        ) VALUES (
          :agency_id,:task_id,:user_id,:duration_minutes,:note,
          COALESCE(:entry_date,CURRENT_DATE)
        ) RETURNING *
    """), {"agency_id": user["agency_id"], "task_id": task_id,
           "user_id": user["user_id"], **data.model_dump()}).mappings().one()
    result = dict(row)
    db.commit()
    return result


@router.get("/projects/{project_id}/time-summary")
def time_summary(project_id: int, db: Session = Depends(get_db),
                 user: dict = Depends(get_current_membership)):
    get_accessible_project(db, user, project_id)
    visible = " AND t.is_client_visible=TRUE" if user["role"] == "client_user" else ""
    data = db.execute(text("""
        SELECT COALESCE(SUM(te.duration_minutes),0) AS total_minutes,
               COUNT(te.id) AS entries_count
        FROM public.time_entries te
        JOIN public.tasks t ON t.id=te.task_id AND t.agency_id=te.agency_id
        WHERE t.agency_id=:agency_id AND t.project_id=:project_id
    """ + visible), {"agency_id": user["agency_id"], "project_id": project_id}).mappings().one()
    total = int(data["total_minutes"])
    return {"project_id": project_id, "total_minutes": total,
            "total_hours": round(total/60,2), "entries_count": data["entries_count"]}
