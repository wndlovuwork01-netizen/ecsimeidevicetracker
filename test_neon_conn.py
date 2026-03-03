import psycopg2
import os

def test_conn():
    url = "postgresql://neondb_owner:npg_opw0xS3VkHQt@ep-damp-union-agyj46hm-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    print(f"Attempting to connect to: {url.split('@')[-1]}")
    try:
        conn = psycopg2.connect(url)
        print("Connection successful!")
        cur = conn.cursor()
        cur.execute("SELECT version();")
        print(f"DB Version: {cur.fetchone()}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_conn()
