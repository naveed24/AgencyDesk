# Push AgencyDesk to a public GitHub repository

Run CMD from the extracted `AgencyDesk` folder **after** verifying `.gitignore` excludes `backend/.env`, `backend/uploads`, and `.venv`.

```bat
git init
git add .
git status
git commit -m "AgencyDesk multi-tenant take-home project"
git branch -M main
```

Create a new **empty public** repository named `agencydesk` on GitHub (do not initialize it with another README). Then run (replace YOUR_USERNAME):

```bat
git remote add origin https://github.com/YOUR_USERNAME/agencydesk.git
git push -u origin main
```

If `origin` already exists, use `git remote set-url origin https://github.com/YOUR_USERNAME/agencydesk.git`. Authenticate to GitHub when Git prompts. Do **not** push your real `.env` database password or local uploaded files.

Before submitting, also upload the required 3–5 minute recorded walkthrough and include its URL.
