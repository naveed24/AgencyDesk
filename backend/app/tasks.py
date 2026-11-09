"""Task board endpoints. ID guessing never bypasses project/client access checks."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_db, get_current_membership
from app.projects import get_accessible_project

router = APIRouter(tags=["Tasks"])
TaskStatus = Literal["todo", "in_progress", "review", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    assignee_user_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    is_client_visible: bool = False


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_user_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    is_client_visible: bool | None = None


def require_staff(user):
    if user["role"] not in ("agency_admin", "agency_member"):
        raise HTTPException(status_code=403, detail="Only agency staff can modify tasks")


def validate_assignee(db, user, project_id, assignee_id):
    if assignee_id is None:
        return
    row = db.execute(text("""
        SELECT 1 FROM public.project_members pm
        JOIN public.agency_memberships m
          ON m.agency_id=pm.agency_id AND m.user_id=pm.user_id
        WHERE pm.agency_id=:agency_id AND pm.project_id=:project_id
          AND pm.user_id=:assignee AND m.role IN ('agency_admin','agency_member')
    """), {"agency_id": user["agency_id"], "project_id": project_id,
           "assignee": assignee_id}).first()
    if not row:
        raise HTTPException(status_code=400, detail="Assignee must be assigned agency staff")


def get_allowed_task(db, user, task_id):
    row = db.execute(text("""
        SELECT t.* FROM public.tasks t
        WHERE t.id=:task_id AND t.agency_id=:agency_id
    """), {"task_id": task_id, "agency_id": user["agency_id"]}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    get_accessible_project(db, user, row["project_id"])
    if user["role"] == "client_user" and not row["is_client_visible"]:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


# Alias is used by the activity and file modules.
get_accessible_task = get_allowed_task


@router.get("/projects/{project_id}/tasks")
def list_tasks(project_id: int, db: Session = Depends(get_db),
               user: dict = Depends(get_current_membership)):
    get_accessible_project(db, user, project_id)
    visible = " AND is_client_visible=TRUE" if user["role"] == "client_user" else ""
    rows = db.execute(text("""
        SELECT * FROM public.tasks
        WHERE agency_id=:agency_id AND project_id=:project_id
    """ + visible + " ORDER BY id DESC"), {
        "agency_id": user["agency_id"], "project_id": project_id
    }).mappings().all()
    return [dict(r) for r in rows]


@router.get("/tasks/{task_id}")
def read_task(task_id: int, db: Session = Depends(get_db),
              user: dict = Depends(get_current_membership)):
    return get_allowed_task(db, user, task_id)


@router.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: int, data: TaskCreate,
                db: Session = Depends(get_db),
                user: dict = Depends(get_current_membership)):
    require_staff(user)
    get_accessible_project(db, user, project_id)
    validate_assignee(db, user, project_id, data.assignee_user_id)
    try:
        row = db.execute(text("""
            INSERT INTO public.tasks (
              agency_id,project_id,title,description,status,priority,
              assignee_user_id,due_date,is_client_visible
            ) VALUES (
              :agency_id,:project_id,:title,:description,:status,:priority,
              :assignee_user_id,:due_date,:is_client_visible
            ) RETURNING *
        """), {"agency_id": user["agency_id"], "project_id": project_id,
               **data.model_dump()}).mappings().one()
        result = dict(row)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task constraint violation")


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, data: TaskUpdate,
                db: Session = Depends(get_db),
                user: dict = Depends(get_current_membership)):
    require_staff(user)
    # Resolve access FIRST, before locking or changing anything.
    old = get_allowed_task(db, user, task_id)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No changes provided")
    for mandatory in ("title", "status", "priority", "is_client_visible"):
        if mandatory in updates and updates[mandatory] is None:
            raise HTTPException(status_code=422, detail=f"{mandatory} cannot be null")
    if "assignee_user_id" in updates:
        validate_assignee(db, user, old["project_id"], updates["assignee_user_id"])
    # Field identifiers are from the validated Pydantic schema, never arbitrary input.
    assignments = ", ".join(f"{field}=:{field}" for field in updates)
    try:
        row = db.execute(text(f"""
            UPDATE public.tasks SET {assignments}
            WHERE id=:task_id AND agency_id=:agency_id
            RETURNING *
        """), {**updates, "task_id": task_id,
               "agency_id": user["agency_id"]}).mappings().one()
        result = dict(row)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task constraint violation")
