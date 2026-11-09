"""Per-project dashboard with task and time totals scoped to viewer visibility."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_membership, get_db
from app.tasks import get_accessible_project

router = APIRouter(tags=["Project Dashboard"])


@router.get("/projects/{project_id}/dashboard")
def project_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_membership),
):
    get_accessible_project(db, user, project_id)
    only_visible = "AND t.is_client_visible = TRUE" if user["role"] == "client_user" else ""
    params = {"agency_id": user["agency_id"], "project_id": project_id}

    task_rows = db.execute(
        text(f"""
            SELECT t.status, COUNT(*) AS count
            FROM public.tasks t
            WHERE t.agency_id = :agency_id
              AND t.project_id = :project_id
              {only_visible}
            GROUP BY t.status
        """),
        params,
    ).mappings().all()

    time_total = db.execute(
        text(f"""
            SELECT COALESCE(SUM(te.duration_minutes), 0) AS minutes
            FROM public.tasks t
            JOIN public.time_entries te
              ON te.task_id = t.id AND te.agency_id = t.agency_id
            WHERE t.agency_id = :agency_id
              AND t.project_id = :project_id
              {only_visible}
        """),
        params,
    ).scalar_one()

    counts = {"todo": 0, "in_progress": 0, "review": 0, "done": 0}
    for row in task_rows:
        counts[row["status"]] = row["count"]
    minutes = int(time_total)
    return {
        "project_id": project_id,
        "task_counts": counts,
        "total_tasks": sum(counts.values()),
        "total_minutes": minutes,
        "total_hours": round(minutes / 60, 2),
    }
