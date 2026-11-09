"""Apply ordered SQL migrations once, tracking each in schema_migrations."""
from pathlib import Path
from psycopg import connect
from app.database import settings

base = Path(__file__).resolve().parent
with connect(host=settings.db_host, port=settings.db_port, user=settings.db_user,
             password=settings.db_password, dbname=settings.db_name) as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS public.schema_migrations (
        filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    for file in sorted((base / "migrations").glob("*.sql")):
        if conn.execute("SELECT 1 FROM public.schema_migrations WHERE filename=%s",(file.name,)).fetchone():
            print("Already applied:",file.name)
            continue
        with conn.transaction():
            conn.execute(file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO public.schema_migrations(filename) VALUES (%s)",(file.name,))
        print("Applied:",file.name)
print("Migrations complete.")
