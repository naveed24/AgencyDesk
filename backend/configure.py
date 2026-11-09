"""Interactive, standard-library-only first-run config for local Windows setup."""
from getpass import getpass
from pathlib import Path
import json
import secrets

path = Path(__file__).resolve().parent / ".env"
if path.exists():
    print("Existing backend/.env kept unchanged.")
    raise SystemExit(0)
print("\nAgencyDesk first-run setup")
print("Use the password you normally enter in pgAdmin for the postgres user.")
password = getpass("PostgreSQL postgres password: ")
if not password:
    raise SystemExit("PostgreSQL password cannot be empty. Re-run setup.")
print("A separate database 'agencydesk_final' will be created (your old agencydesk remains untouched).")
demo_password = getpass("New local demo password [Enter for Demo@12345]: ") or "Demo@12345"
if len(demo_password) < 8:
    raise SystemExit("Demo password must be at least 8 characters")
items = {
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5432",
    "DB_USER": "postgres",
    "DB_PASSWORD": password,
    "DB_NAME": "agencydesk_final",
    "JWT_SECRET": secrets.token_hex(32),
    "DEMO_PASSWORD": demo_password,
    "CORS_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
}
path.write_text("\n".join(f"{key}={json.dumps(value)}" for key,value in items.items()) + "\n",encoding="utf-8")
print("Saved backend/.env (not tracked by Git).")
