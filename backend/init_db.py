"""Create the fresh local demo database without touching old agencydesk DB."""
from psycopg import connect, sql
from app.database import settings

with connect(host=settings.db_host,port=settings.db_port,user=settings.db_user,
             password=settings.db_password,dbname="postgres",autocommit=True) as conn:
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s",(settings.db_name,)).fetchone()
    if not exists:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.db_name)))
        print("Created database:",settings.db_name)
    else:
        print("Using existing database:",settings.db_name)
