"""Tenant-scoped task attachments and client approval endpoints for AgencyDesk."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_membership, get_db
from app.activity import get_allowed_task

router = APIRouter(tags=["Files and Approvals"])

UPLOAD_ROOT = (Path(__file__).resolve().parents[1] / "uploads").resolve()
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".doc", ".docx", ".zip"}


class FileReview(BaseModel):
    status: str


def _get_allowed_file(db: Session, user: dict, file_id: int) -> dict:
    record = db.execute(
        text("""
            SELECT id, agency_id, task_id, original_filename,
                   storage_path, content_type, is_client_visible,
                   approval_status, uploaded_by_user_id,
                   reviewed_by_user_id, reviewed_at, created_at
            FROM public.task_files
            WHERE id = :file_id AND agency_id = :agency_id
        """),
        {"file_id": file_id, "agency_id": user["agency_id"]},
    ).mappings().first()
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Checking the task also checks its project, agency, and client visibility.
    get_allowed_task(db, user, record["task_id"])
    if user["role"] == "client_user" and not record["is_client_visible"]:
        raise HTTPException(status_code=404, detail="File not found")
    return dict(record)


def _public_file(record: dict) -> dict:
    # Deliberately do not expose internal storage paths to API consumers.
    return {key: value for key, value in record.items() if key != "storage_path"}


@router.post("/tasks/{task_id}/files", status_code=201)
async def upload_task_file(
    task_id: int,
    file: UploadFile = File(...),
    is_client_visible: bool = Form(False),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_membership),
):
    if user["role"] not in ("agency_admin", "agency_member"):
        raise HTTPException(status_code=403, detail="Only agency staff can upload files")
    get_allowed_task(db, user, task_id)

    original_filename = Path((file.filename or "").replace("\\", "/")).name
    if not original_filename or len(original_filename) > 255:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(original_filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported file extension")

    agency_folder = UPLOAD_ROOT / str(user["agency_id"])
    agency_folder.mkdir(parents=True, exist_ok=True)
    generated_name = uuid4().hex
    storage_file = agency_folder / generated_name
    relative_path = f"{user['agency_id']}/{generated_name}"

    size = 0
    try:
        with storage_file.open("xb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds 10 MB")
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty files are not allowed")

        row = db.execute(
            text("""
                INSERT INTO public.task_files
                    (agency_id, task_id, uploaded_by_user_id,
                     original_filename, storage_path, content_type,
                     is_client_visible)
                VALUES
                    (:agency_id, :task_id, :user_id,
                     :original_filename, :storage_path, :content_type,
                     :is_client_visible)
                RETURNING id, agency_id, task_id, uploaded_by_user_id,
                          original_filename, storage_path, content_type,
                          is_client_visible, approval_status,
                          reviewed_by_user_id, reviewed_at, created_at
            """),
            {
                "agency_id": user["agency_id"],
                "task_id": task_id,
                "user_id": user["user_id"],
                "original_filename": original_filename,
                "storage_path": relative_path,
                "content_type": file.content_type,
                "is_client_visible": is_client_visible,
            },
        ).mappings().one()
        db.commit()
        return _public_file(dict(row))
    except Exception:
        db.rollback()
        storage_file.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/tasks/{task_id}/files")
def list_task_files(
    task_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_membership),
):
    get_allowed_task(db, user, task_id)
    visibility_sql = "AND is_client_visible = TRUE" if user["role"] == "client_user" else ""
    rows = db.execute(
        text(f"""
            SELECT id, agency_id, task_id, uploaded_by_user_id,
                   original_filename, content_type, is_client_visible,
                   approval_status, reviewed_by_user_id, reviewed_at, created_at
            FROM public.task_files
            WHERE agency_id = :agency_id AND task_id = :task_id
            {visibility_sql}
            ORDER BY id DESC
        """),
        {"agency_id": user["agency_id"], "task_id": task_id},
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/files/{file_id}/download")
def download_task_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_membership),
):
    record = _get_allowed_file(db, user, file_id)
    path = (UPLOAD_ROOT / record["storage_path"]).resolve()
    if not path.is_relative_to(UPLOAD_ROOT) or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=path,
        filename=record["original_filename"],
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.patch("/files/{file_id}/review")
def review_task_file(
    file_id: int,
    data: FileReview,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_membership),
):
    if user["role"] != "client_user":
        raise HTTPException(status_code=403, detail="Only client users can review files")
    if data.status not in ("approved", "needs_changes"):
        raise HTTPException(status_code=422, detail="Use approved or needs_changes")

    # Locks review state while checking that the user is allowed to access it.
    record = _get_allowed_file(db, user, file_id)
    result = db.execute(
        text("""
            UPDATE public.task_files
            SET approval_status = :status,
                reviewed_by_user_id = :user_id,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = :file_id AND agency_id = :agency_id
            RETURNING id, task_id, original_filename, is_client_visible,
                      approval_status, reviewed_by_user_id, reviewed_at
        """),
        {
            "status": data.status,
            "user_id": user["user_id"],
            "file_id": record["id"],
            "agency_id": user["agency_id"],
        },
    ).mappings().one()
    db.commit()
    return dict(result)
