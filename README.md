# AgencyDesk — multi-tenant agency/client workspace

React + FastAPI (Python) + PostgreSQL take-home submission. One deployment serves multiple agencies, with agency-scoped access and client-facing task portals.

## Quick start (Windows; target under 10 minutes)

**Requirements:** Python 3.11–3.14, Node.js 20+, PostgreSQL server running locally on port 5432, and the `postgres` account password. You already have Python, Node.js, and PostgreSQL installed; PostgreSQL **server** must be started as well. An internet connection is needed for first-time dependency installation.

1. Extract this ZIP to any local folder (for example, `Desktop\AgencyDesk`). Do not merge it into the earlier incomplete project.
2. Double-click **`setup_windows.bat`**, or open Command Prompt in this folder and run `setup_windows.bat`. Enter your local PostgreSQL `postgres` password. Choose a demo login password (press Enter to use the local default, `Demo@12345`). The script installs backend/frontend packages, creates **`agencydesk_final`** if absent, applies migrations, and seeds demo data.
3. Double-click **`start_windows.bat`**. It opens two terminals: the API and React frontend.
4. Visit **http://127.0.0.1:5173** (app) or **http://127.0.0.1:8000/docs** (Swagger).

**If PostgreSQL uses another port or username:** Edit `backend/.env` after setup configuration, then rerun `setup_windows.bat`. If the database is missing or partially initialized, use a **new** `DB_NAME` in `.env`, then rerun. Do not drop your earlier `agencydesk` database.

### Demo logins

All seeded accounts share the demo password you selected during setup. Agency IDs are printed by `seed_demo.py` and written locally to `backend/.seed_ids.json` (not committed to Git). On a fresh `agencydesk_final` database the IDs are usually **1** for Northstar and **2** for Bluebird.

| Email | Agency | Role | Demonstrates |
| --- | --- | --- | --- |
| `admin@agencydesk.local` | Northstar | `agency_admin` | Full agency administration |
| `client@agencydesk.local` | Northstar | `client_user` | Sees only Acme projects and visible content |
| `member@agencydesk.local` | Northstar | `agency_member` | Assigned project access only |
| `blueadmin@agencydesk.local` | Bluebird | `agency_admin` | Second tenant |
| `admin@agencydesk.local` | Bluebird | `client_user` | Same identity, different agency role |

> Use these credentials only for local demonstration. Never deploy with a demo password or use PostgreSQL's superuser as an application credential in production.

## How to test tenant isolation and visibility

After setup, open CMD in `backend`, activate the virtual environment, then run:

```bat
cd backend
.venv\Scripts\activate.bat
python -m pytest -v
```

These are **live PostgreSQL integration tests**, not mocked or skipped tests. They use FastAPI's `TestClient` against your seeded local database without requiring Uvicorn to be running. A missing seed is treated as a test failure.

The tests cover: cross-tenant reads/writes, client project restrictions, hidden tasks and comments, hidden file lists/downloads/reviews, dashboard aggregation, unauthorized time logging, project assignment rules, invite resend and double acceptance, removing a project member while assigned tasks exist, and the same email in different agencies.

**Note:** Some tests create a local invitation and temporarily unassign/reassign the demo member. Use a fresh demo database when testing.

## Features

- **Agency admin**: create clients/projects, create/update tasks, assign staff, comment, log time, upload files, invite users.
- **Agency member**: assigned projects only; tasks, comments, time tracking, and uploads on those projects.
- **Client user**: only client-assigned projects; only client-visible tasks, comments, files and matching dashboard totals; can comment on visible tasks and approve/request changes on visible files; cannot create/update tasks or log time.
- **Invite lifecycle**: pending invitation unique by agency/email; resends atomically update the invite; acceptance locks the row and is idempotent. For this demo, an invite token is returned to the admin; SMTP delivery is not configured.
- **Files**: actual local uploads/downloads, 10 MB limit, agency-specific random server filenames; file API never exposes storage paths.

### API highlights

| Endpoint | Function |
| --- | --- |
| `POST /auth/login`, `GET /auth/me`, `POST /auth/switch` | Tenant-aware login, identity and agency switching |
| `GET/POST /clients`, `GET/POST /projects` | Client and project access |
| `GET/POST /projects/{id}/tasks`, `GET/PATCH /tasks/{id}` | Task board |
| `GET/POST /tasks/{id}/comments` | Visibility-aware comments |
| `POST /tasks/{id}/time-entries` | Staff time logging |
| `GET /projects/{id}/time-summary` | Per-project hours |
| `GET /projects/{id}/dashboard` | Status counts and visible hours |
| `POST /tasks/{id}/files`, `GET /tasks/{id}/files` | Upload/list attachments |
| `GET /files/{id}/download`, `PATCH /files/{id}/review` | Protected file download / client approval |
| `POST /invitations`, `POST /invitations/accept` | Invite lifecycle |
| `GET/POST/DELETE /projects/{id}/members` | Project membership |

## Directory structure

```text
AgencyDesk/
  backend/
    app/               # FastAPI routers, auth and database engine
    migrations/        # Sequential PostgreSQL schema and integrity migrations
    tests/             # Live tenant isolation / client visibility tests
    configure.py       # First-run private configuration
    init_db.py         # Create demo database if missing
    migrate.py         # Apply migrations exactly once
    seed_demo.py       # Two agencies + clients + sample tasks/comments/files
    requirements.txt
    .env.example       # Placeholder only; actual .env is gitignored
  frontend/
    src/               # React application and styling
    package.json
  DESIGN.md
  VIDEO_WALKTHROUGH.md
  SUBMISSION_CHECKLIST.md
  setup_windows.bat
  start_windows.bat
```

## Manual setup (macOS/Linux, or when .bat scripts cannot be used)

1. Ensure PostgreSQL is running. Copy `backend/.env.example` to `backend/.env`; fill in your own PostgreSQL password and replace `JWT_SECRET` with a randomly generated 64-character hex string. The default demo DB is `agencydesk_final`.
2. `cd backend && python -m venv .venv`, activate the environment, then `python -m pip install -r requirements.txt`.
3. Still in `backend`, run `python init_db.py`, `python migrate.py`, and `python seed_demo.py`.
4. Start the API: `python -m uvicorn app.main:app --reload`.
5. In another terminal: `cd frontend && npm install && npm run dev`.
6. Run tests from `backend`: `python -m pytest -v`.

## Database and security notes

- The initial schema has twelve domain tables with normalization, primary/foreign keys, uniqueness, CHECK constraints, partial invite index, and composite `(agency_id, entity_id)` foreign keys.
- The role is **not trusted from JWT claims**. Each protected request validates the user's current membership in the selected agency. A removed membership invalidates the user's access.
- Scope is applied to both list and detail endpoints, including comments, file download/review and dashboard aggregates. Unknown/unauthorized IDs return 404 to avoid revealing existence.
- Database composite foreign keys prevent linking objects from one tenant to another. **Confidentiality** requires the API authorization filters; the schema alone does not make a shared table private to a superuser. See `DESIGN.md`.
- `backend/uploads/`, credentials, virtual environments and local `.seed_ids.json` are excluded from Git.

## Submission

Create a **public** GitHub repository and push the whole `AgencyDesk` folder, including migrations, seed script, frontend, tests, README and DESIGN. Confirm the new clone starts on another machine. **A 3–5 minute Loom (or similar) video is required by the assignment**; follow `VIDEO_WALKTHROUGH.md`, record the real running UI and schema, and include the final video URL in your submission.

## Known scope limits

This is an interview MVP, not a production SaaS deployment. Local uploads are not backed by object storage, email delivery for invitations is manual, and development uses a local `postgres` account for easiest setup. For production, use a least-privileged application DB role, HTTPS, external secrets, antivirus scanning, rate limiting, durable storage, and stronger operational monitoring. Full CRM and Gantt views are not part of the assignment.
