import os
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor

# Path to the local SQLite database
SQLITE_DB = os.path.join(os.path.dirname(__file__), "data", "app.db")

def migrate():
    # Priority: 1. Environment Variable, 2. Hardcoded Fallback
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        url = "postgresql://neondb_owner:npg_opw0xS3VkHQt@ep-damp-union-agyj46hm-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_c = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(url)
    pg_c = pg_conn.cursor()

    # Ensure tables exist in PostgreSQL
    print("Creating tables in PostgreSQL if they don't exist...")
    pg_c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','viewer')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            phone TEXT
        )
    """)
    pg_c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id SERIAL PRIMARY KEY,
            owner TEXT,
            imei TEXT UNIQUE,
            phone TEXT UNIQUE,
            carrier TEXT,
            region TEXT,
            api_token TEXT NOT NULL,
            last_update TIMESTAMPTZ,
            last_lat REAL,
            last_lng REAL
        )
    """)
    pg_c.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id SERIAL PRIMARY KEY,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    pg_conn.commit()

    # Migrate users
    print("Migrating users...")
    sqlite_c.execute("SELECT * FROM users")
    for row in sqlite_c.fetchall():
        pg_c.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at, phone) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (row["id"], row["username"], row["password_hash"], row["role"], row["created_at"], row["phone"])
        )
    print("Users migrated.")

    # Migrate devices
    print("Migrating devices...")
    sqlite_c.execute("SELECT * FROM devices")
    for row in sqlite_c.fetchall():
        pg_c.execute(
            "INSERT INTO devices (id, owner, imei, phone, carrier, region, api_token, last_update, last_lat, last_lng) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (row["id"], row["owner"], row["imei"], row["phone"], row["carrier"], row["region"], row["api_token"], row["last_update"], row["last_lat"], row["last_lng"])
        )
    print("Devices migrated.")

    # Migrate locations
    print("Migrating locations...")
    sqlite_c.execute("SELECT * FROM locations")
    for row in sqlite_c.fetchall():
        pg_c.execute(
            "INSERT INTO locations (id, device_id, lat, lng, ts) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (row["id"], row["device_id"], row["lat"], row["lng"], row["ts"])
        )
    print("Locations migrated.")

    pg_conn.commit()

    # Close connections
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
