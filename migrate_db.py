import os
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor

# Path to the local SQLite database
SQLITE_DB = os.path.join(os.path.dirname(__file__), "data", "app.db")

def migrate():
    # Get the Neon connection string from the environment
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise Exception("DATABASE_URL environment variable not set.")
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_c = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(url)
    pg_c = pg_conn.cursor()

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
