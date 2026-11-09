"""AgencyDesk HTTP API entry point."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine, settings
from app.auth import router as auth_router
from app.projects import router as projects_router
from app.tasks import router as tasks_router
from app.activity import router as activity_router
from app.clients_api import router as clients_router
from app.files_api import router as files_router
from app.dashboard import router as dashboard_router
from app.members_api import router as members_router
from app.invites_api import router as invites_router

app = FastAPI(title="AgencyDesk API", version="1.0.0",
              description="Multi-tenant agency/client workspace. See /docs for API documentation.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (auth_router, clients_router, projects_router, tasks_router,
               activity_router, files_router, dashboard_router, members_router,
               invites_router):
    app.include_router(router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "AgencyDesk API running"}


@app.get("/db-health", tags=["Health"])
def db_health():
    try:
        with engine.connect() as connection:
            database = connection.execute(text("SELECT current_database() ")).scalar_one()
        return {"status": "connected", "database": database}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database connection failed")
