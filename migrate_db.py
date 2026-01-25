import sqlite3
import psycopg2
import os
import json
from dotenv import load_dotenv
from psycopg2.extras import Json

load_dotenv()

SQLITE_DB = "echo.db"
PG_URL = os.getenv("DATABASE_URL")

if not PG_URL:
    print("Error: DATABASE_URL not found in .env")
    exit(1)

def migrate():
    print("🚀 Starting migration from SQLite to Supabase...")
    
    # 1. Read from SQLite
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.row_factory = sqlite3.Row
        s_cursor = s_conn.cursor()
        
        # Get Entries
        s_cursor.execute("SELECT * FROM entries")
        entries = s_cursor.fetchall()
        print(f"Found {len(entries)} entries in SQLite.")
        
        # Get Profile
        s_cursor.execute("SELECT value FROM user_profile WHERE key='main'")
        profile_row = s_cursor.fetchone()
        profile_data = json.loads(profile_row[0]) if profile_row else None
        print("Found profile data." if profile_data else "No profile data found.")
        
        s_conn.close()
    except Exception as e:
        print(f"Error reading SQLite: {e}")
        return

    # 2. Write to Postgres
    try:
        p_conn = psycopg2.connect(PG_URL)
        p_cursor = p_conn.cursor()
        
        # Create tables if not exist (reuse logic from init_db essentially)
        p_cursor.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'ANCHOR',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        p_cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value JSONB
            )
        ''')
        p_conn.commit()
        
        # Insert Entries
        count = 0
        for row in entries:
            # Parse metadata from string to dict (JSONB expects dict/json)
            try:
                meta = json.loads(row['metadata']) if row['metadata'] else {}
            except:
                meta = {}
            
            # Check if exists to avoid duplicates (optional, but good for retries)
            # Using content as semi-unique key for safety if IDs drifted, 
            # but usually we just want to dump. ignoring conflict check for MVP speed.
            
            p_cursor.execute(
                "INSERT INTO entries (content, type, metadata, created_at) VALUES (%s, %s, %s, %s)",
                (row['content'], row['type'], Json(meta), row['created_at'])
            )
            count += 1
            
        print(f"Transferred {count} entries to Supabase.")

        # Insert Profile
        if profile_data:
            p_cursor.execute(
                "INSERT INTO user_profile (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ('main', Json(profile_data))
            )
            print("Transferred User Profile.")
            
        p_conn.commit()
        p_conn.close()
        print("✅ Migration Complete!")
        
    except Exception as e:
        print(f"Error writing to Postgres: {e}")

if __name__ == "__main__":
    migrate()
