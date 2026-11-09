# Required 3–5 minute walkthrough (record this yourself)

Record screen + voice with Loom, OBS, or similar. **The assignment will not review submissions without this video.** Upload it and paste the final public-viewable video URL into your submission.

## 0:00–0:30 — Project overview
Open the React login page. Say: "AgencyDesk is a React, FastAPI, PostgreSQL multi-tenant project workspace with an agency portal and restricted client portal. One deployment serves multiple agencies."

## 0:30–1:15 — Agency admin workflow
Log in to Northstar using `admin@agencydesk.local` and the demo password. Show the Acme Website board, internal versus client-visible task badges, status updates, adding a comment, logging time, and uploading a sample file. Open the project dashboard and show hours and task counts.

## 1:15–2:05 — Client portal and visible content
Log out, log in as `client@agencydesk.local` under Northstar. Show that the client sees only Acme projects and client-visible tasks. Open a visible task, show that the internal budget comment and internal attached file are missing, add a client comment and mark a visible file "Approved" or "Needs changes". Point out the client has no task creation or status controls.

## 2:05–3:00 — Database schema and tenant isolation
In pgAdmin, show `users`, `agencies`, `agency_memberships`, `clients`, `projects`, `tasks`, `comments`, `time_entries`, `task_files`, and `invitations`. Explain composite `(agency_id, id)` foreign keys. Highlight that email identity is shared across memberships and that authorization scopes the same person differently in two agencies.

## 3:00–3:40 — Tests and edge cases
In backend CMD, run `python -m pytest -v`. Show actual green test results. Explain how tests cover guessed IDs, hidden comments/files, cross-tenant projects, invitation idempotency, and unassigning tasks when a member is removed.

## 3:40–4:10 — Setup and wrap-up
Show `README.md`, `DESIGN.md`, ordered migrations and `seed_demo.py`. Explain the one-command Windows setup. End with a view of your public GitHub repository and its folder structure.

## Final recording checklist
- Show an actual **running** application and live schema, not static mockups.
- Keep the recording between **3 and 5 minutes**.
- Check microphone audio and make the video accessible to reviewers.
- Do not show `backend/.env`, passwords, JWTs, or other credentials.
