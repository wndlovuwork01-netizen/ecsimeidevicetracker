import psycopg2
from psycopg2.extras import DictCursor

def check_neon():
    url = "postgresql://neondb_owner:npg_opw0xS3VkHQt@ep-damp-union-agyj46hm-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    try:
        conn = psycopg2.connect(url)
        cur = conn.cursor(cursor_factory=DictCursor)
        
        print("--- Tables ---")
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        for row in cur.fetchall():
            print(row['table_name'])
            
        print("\n--- User Count ---")
        cur.execute("SELECT count(*) FROM users;")
        print(cur.fetchone()[0])
        
        print("\n--- Device Count ---")
        cur.execute("SELECT count(*) FROM devices;")
        print(cur.fetchone()[0])
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Check failed: {e}")

if __name__ == "__main__":
    check_neon()
