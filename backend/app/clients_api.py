"""Client list and creation, tenant-scoped."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.auth import get_current_membership, get_db

router = APIRouter(prefix="/clients", tags=["Clients"])

class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)

@router.get("")
def list_clients(db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    if user["role"] == "client_user":
        rows = db.execute(text("""
            SELECT c.id, c.agency_id, c.name, c.created_at
            FROM public.clients c
            JOIN public.client_memberships cm
              ON cm.client_id = c.id AND cm.agency_id = c.agency_id
            WHERE c.agency_id = :agency_id AND cm.user_id = :user_id
            ORDER BY c.id
        """), {"agency_id": user["agency_id"], "user_id": user["user_id"]}).mappings().all()
    else:
        rows = db.execute(text("""
            SELECT DISTINCT c.id, c.agency_id, c.name, c.created_at
            FROM public.clients c
            WHERE c.agency_id = :agency_id
              AND (:is_admin OR EXISTS (
                  SELECT 1 FROM public.projects p
                  JOIN public.project_members pm
                    ON pm.project_id = p.id AND pm.agency_id = p.agency_id
                  WHERE p.client_id = c.id AND p.agency_id = c.agency_id
                    AND pm.user_id = :user_id
              ))
            ORDER BY c.id
        """), {"agency_id": user["agency_id"], "user_id": user["user_id"],
               "is_admin": user["role"] == "agency_admin"}).mappings().all()
    return [dict(r) for r in rows]

@router.post("", status_code=201)
def create_client(data: ClientCreate, db: Session = Depends(get_db), user: dict = Depends(get_current_membership)):
    if user["role"] != "agency_admin":
        raise HTTPException(status_code=403, detail="Only agency admins can create clients")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Client name cannot be empty")
    row = db.execute(text("""
        INSERT INTO public.clients (agency_id, name)
        VALUES (:agency_id, :name)
        RETURNING id, agency_id, name, created_at
    """), {"agency_id": user["agency_id"], "name": name}).mappings().one()
    db.commit()
    return dict(row)
