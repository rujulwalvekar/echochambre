import os
import random
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set. Please add your Supabase connection string to .env")
    
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Entries table with metadata support (JSONB for Postgres)
        c.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'ANCHOR',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # User Profile table
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value JSONB
            )
        ''')
        
        conn.commit()
        
        # Initialize default profile structure if empty
        c.execute("SELECT count(*) FROM user_profile WHERE key = 'main'")
        if c.fetchone()['count'] == 0:
            default_profile = {
                "thinking_patterns": [],
                "core_values": [],
                "people": [],
                "communication_style": "Unknown"
            }
            c.execute("INSERT INTO user_profile (key, value) VALUES (%s, %s)", 
                     ('main', json.dumps(default_profile)))
            conn.commit()
            
        conn.close()
        print("Database initialized successfully (Postgres).")
    except Exception as e:
        print(f"Error initializing database: {e}")

def add_entry(content: str, entry_type: str = 'ANCHOR', metadata: Dict = None):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Postgres JSONB handles dicts directly, no need for json.dumps if using psycopg2 with json support
    # But usually json.dumps is safer for strings
    metadata_json = json.dumps(metadata) if metadata else "{}"
    
    if content and content.strip():
        c.execute('INSERT INTO entries (content, type, metadata) VALUES (%s, %s, %s)', 
                 (content, entry_type, metadata_json))
        conn.commit()
    conn.close()

def get_profile() -> Dict:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM user_profile WHERE key = 'main'")
    row = c.fetchone()
    conn.close()
    
    if row:
        # psycop2 RealDictCursor with JSONB returns a dict, not a string
        # so we don't need json.loads if the driver handles it, but let's be safe
        val = row['value']
        if isinstance(val, str):
            return json.loads(val)
        return val
    return {}

def update_profile(profile_data: Dict):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Upsert logic for Postgres requires "ON CONFLICT"
    c.execute('''
        INSERT INTO user_profile (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', ('main', json.dumps(profile_data)))
    
    conn.commit()
    conn.close()

# Keep for backward compatibility but redirect
def add_anchor(content: str):
    add_entry(content, 'ANCHOR')

def get_entry_count() -> int:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT count(*) FROM entries')
    count = c.fetchone()['count']
    conn.close()
    return count

def get_recent_entries(entry_type: str = 'ANCHOR', limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    # If type is ALL, fetch everything
    if entry_type == 'ALL':
        c.execute('SELECT * FROM entries ORDER BY created_at DESC LIMIT %s', (limit,))
    else:
        c.execute('SELECT * FROM entries WHERE type = %s ORDER BY created_at DESC LIMIT %s', (entry_type, limit))
        
    rows = c.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        # Convert row to dict (RealDictCursor already does this conceptually, but ensuring copy)
        d = dict(row)
        
        # Handle metadata: JSONB returns dict, but check just in case
        if isinstance(d.get('metadata'), str):
             try:
                d['metadata'] = json.loads(d['metadata'])
             except:
                d['metadata'] = {}
        elif d.get('metadata') is None:
            d['metadata'] = {}
            
        # Handle created_at formatting (Postgres returns datetime object)
        if d.get('created_at'):
             d['created_at'] = str(d['created_at'])
             
        results.append(d)
    return results

def get_recent_anchors(limit: int = 5) -> List[Dict[str, Any]]:
    return get_recent_entries('ANCHOR', limit)

def get_random_anchors(limit: int = 3) -> List[str]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT content FROM entries WHERE type = %s ORDER BY RANDOM() LIMIT %s', ('ANCHOR', limit))
    rows = c.fetchall()
    conn.close()
    return [row['content'] for row in rows]
