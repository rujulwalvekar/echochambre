import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor, connect_timeout=5)
    register_vector(conn)
    return conn


def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute('CREATE EXTENSION IF NOT EXISTS vector')

        c.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'ANCHOR',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                embedding vector(768),
                source TEXT DEFAULT 'web'
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value JSONB
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                peer TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        conn.commit()

        # Initialize default profile if empty
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
        print("Database initialized.")
    except Exception as e:
        print(f"Error initializing database: {e}")


# --- Entries ---

def add_entry(content: str, entry_type: str = 'ANCHOR', metadata: dict = None,
              embedding: list = None, source: str = 'web'):
    conn = get_db_connection()
    c = conn.cursor()
    metadata_json = json.dumps(metadata) if metadata else "{}"
    if content and content.strip():
        if embedding:
            c.execute(
                'INSERT INTO entries (content, type, metadata, embedding, source) VALUES (%s, %s, %s, %s, %s)',
                (content, entry_type, metadata_json, embedding, source)
            )
        else:
            c.execute(
                'INSERT INTO entries (content, type, metadata, source) VALUES (%s, %s, %s, %s)',
                (content, entry_type, metadata_json, source)
            )
        conn.commit()
    conn.close()


def add_anchor(content: str):
    add_entry(content, 'ANCHOR')


def get_entry_count() -> int:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT count(*) FROM entries')
    count = c.fetchone()['count']
    conn.close()
    return count


def _normalize_rows(rows) -> List[Dict[str, Any]]:
    """Normalize DB rows: parse metadata, format timestamps, drop embedding from output."""
    results = []
    for row in rows:
        d = dict(row)
        # Don't send embeddings to the frontend
        d.pop('embedding', None)

        if isinstance(d.get('metadata'), str):
            try:
                d['metadata'] = json.loads(d['metadata'])
            except Exception:
                d['metadata'] = {}
        elif d.get('metadata') is None:
            d['metadata'] = {}

        if d.get('created_at'):
            d['created_at'] = str(d['created_at'])

        results.append(d)
    return results


def get_recent_entries(entry_type: str = 'ANCHOR', limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    if entry_type == 'ALL':
        c.execute('SELECT * FROM entries ORDER BY created_at DESC LIMIT %s', (limit,))
    else:
        c.execute('SELECT * FROM entries WHERE type = %s ORDER BY created_at DESC LIMIT %s',
                  (entry_type, limit))
    rows = c.fetchall()
    conn.close()
    return _normalize_rows(rows)


def get_recent_anchors(limit: int = 5) -> List[Dict[str, Any]]:
    return get_recent_entries('ANCHOR', limit)


def get_random_anchors(limit: int = 3) -> List[str]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT content FROM entries WHERE type = %s ORDER BY RANDOM() LIMIT %s',
              ('ANCHOR', limit))
    rows = c.fetchall()
    conn.close()
    return [row['content'] for row in rows]


def search_entries_vector(query_embedding: list, entry_type: str = 'ALL',
                          limit: int = 5) -> List[Dict[str, Any]]:
    """Find the most relevant entries by cosine similarity."""
    conn = get_db_connection()
    c = conn.cursor()

    if entry_type == 'ALL':
        c.execute(
            '''SELECT *, 1 - (embedding <=> %s::vector) AS similarity
               FROM entries WHERE embedding IS NOT NULL
               ORDER BY embedding <=> %s::vector LIMIT %s''',
            (query_embedding, query_embedding, limit)
        )
    else:
        c.execute(
            '''SELECT *, 1 - (embedding <=> %s::vector) AS similarity
               FROM entries WHERE embedding IS NOT NULL AND type = %s
               ORDER BY embedding <=> %s::vector LIMIT %s''',
            (query_embedding, entry_type, query_embedding, limit)
        )

    rows = c.fetchall()
    conn.close()

    if not rows:
        # Fallback to recency if no embeddings exist
        fallback_type = entry_type if entry_type != 'ALL' else 'ANCHOR'
        return get_recent_entries(fallback_type, limit)

    return _normalize_rows(rows)


# --- Embeddings backfill ---

def get_entries_without_embedding() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, content FROM entries WHERE embedding IS NULL ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_entry_embedding(entry_id: int, embedding: list):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE entries SET embedding = %s WHERE id = %s', (embedding, entry_id))
    conn.commit()
    conn.close()


# --- Profile ---

def get_profile() -> Dict:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM user_profile WHERE key = 'main'")
    row = c.fetchone()
    conn.close()
    if row:
        val = row['value']
        if isinstance(val, str):
            return json.loads(val)
        return val
    return {}


def update_profile(profile_data: Dict):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO user_profile (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', ('main', json.dumps(profile_data)))
    conn.commit()
    conn.close()


# --- Conversations ---

def add_conversation_message(peer: str, role: str, content: str):
    if not content or not content.strip():
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'INSERT INTO conversations (peer, role, content) VALUES (%s, %s, %s)',
        (peer, role, content)
    )
    conn.commit()
    conn.close()


def get_conversation(peer: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'SELECT role, content, created_at FROM conversations WHERE peer = %s ORDER BY created_at DESC LIMIT %s',
        (peer, limit)
    )
    rows = c.fetchall()
    conn.close()
    # Reverse so oldest is first
    results = []
    for row in reversed(rows):
        d = dict(row)
        if d.get('created_at'):
            d['created_at'] = str(d['created_at'])
        results.append(d)
    return results
