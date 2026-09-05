"""
High-Performance SQLite Database Module for Notepad Web
Features:
- Thread-local persistent connections with WAL mode
- Zero-overhead connection reuse across threads
- Atomic row-level updates (no full file rewrites)
- Auto-migration from legacy notes.json and users.json
"""

import os
import json
import sqlite3
import shutil
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from . import config
from .security import unusable_password

DATA_DIR = config.DATA_DIR
DB_PATH = config.DB_PATH

_local = threading.local()

def get_db_connection() -> sqlite3.Connection:
    """
    Get or reuse a thread-local SQLite connection with WAL mode.
    Fastest possible connection reuse without lock contention.
    """
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA busy_timeout = 30000;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA cache_size = -64000;")  # 64MB cache
        cursor.close()
        _local.conn = conn
        
    return _local.conn

def init_db():
    """Initialize database tables, indexes, and migrate existing JSON data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            owner TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (owner) REFERENCES users(username) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS collaborators (
            note_id TEXT NOT NULL,
            username TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'edit',
            PRIMARY KEY (note_id, username),
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
        );

        -- Performance Indexes
        CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner);
        CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_collab_user ON collaborators(username);
        CREATE INDEX IF NOT EXISTS idx_collab_note ON collaborators(note_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(username);
    """)
    # Owner of notes created while auth is disabled.
    cursor.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        ('anonymous', unusable_password(), datetime.now().isoformat())
    )
    conn.commit()

    # Auto-migrate legacy JSON data if table is currently empty
    migrate_legacy_data(conn)

def migrate_legacy_data(conn: sqlite3.Connection):
    """Safely migrate data from notes.json and users.json if database is fresh"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    users_json_path = os.path.join(DATA_DIR, 'users.json')
    notes_json_path = os.path.join(DATA_DIR, 'notes.json')
    
    if user_count == 0 and os.path.exists(users_json_path):
        try:
            with open(users_json_path, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
            
            now_iso = datetime.now().isoformat()
            for username, data in users_data.items():
                pwd = data.get('password', '')
                cursor.execute(
                    "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, pwd, now_iso)
                )
            conn.commit()
            print(f"[Migration] Migrated {len(users_data)} users from JSON to SQLite.")
            shutil.copy2(users_json_path, users_json_path + '.bak')
        except Exception as e:
            print(f"[Migration Error] Failed to migrate users.json: {e}")

    cursor.execute("SELECT COUNT(*) FROM notes")
    note_count = cursor.fetchone()[0]
    
    if note_count == 0 and os.path.exists(notes_json_path):
        try:
            with open(notes_json_path, 'r', encoding='utf-8') as f:
                notes_data = json.load(f)
            
            for note_id, n in notes_data.items():
                owner = n.get('owner', 'anonymous')
                # ponytail: migrated owners get an unusable random password (they can
                # use /api/auth/register); the old code silently set 'admin123'.
                cursor.execute(
                    "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (owner, unusable_password(), datetime.now().isoformat())
                )
                
                title = n.get('title', 'Untitled')
                content = n.get('content', '')
                created_at = n.get('created_at', datetime.now().isoformat())
                updated_at = n.get('updated_at', created_at)
                
                cursor.execute(
                    "INSERT OR REPLACE INTO notes (id, title, content, owner, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (note_id, title, content, owner, created_at, updated_at)
                )
                
                collabs = n.get('collaborators', {})
                if isinstance(collabs, list):
                    collabs = {u: 'edit' for u in collabs}
                if isinstance(collabs, dict):
                    for u, role in collabs.items():
                        cursor.execute(
                            "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                            (u, unusable_password(), datetime.now().isoformat())
                        )
                        cursor.execute(
                            "INSERT OR REPLACE INTO collaborators (note_id, username, role) VALUES (?, ?, ?)",
                            (note_id, u, str(role))
                        )
            
            conn.commit()
            print(f"[Migration] Migrated {len(notes_data)} notes from JSON to SQLite.")
            shutil.copy2(notes_json_path, notes_json_path + '.bak')
        except Exception as e:
            print(f"[Migration Error] Failed to migrate notes.json: {e}")

# ==================== USER OPERATIONS ====================

def get_user(username: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password_hash, created_at FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row:
        return {'username': row['username'], 'password': row['password_hash'], 'created_at': row['created_at']}
    return None

def create_user(username: str, password_hash: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# ==================== SESSION OPERATIONS ====================

def create_session(username: str) -> str:
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(hours=config.SESSION_TTL_HOURS)).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, username, datetime.now().isoformat(), expires_at)
    )
    conn.commit()
    return token

def get_session_user(token: str) -> Optional[str]:
    if not token:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, expires_at FROM sessions WHERE token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        return None
    expires_at = row['expires_at']
    # Legacy rows have expires_at NULL and stay valid; new rows expire after SESSION_TTL_HOURS.
    if expires_at is not None:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
        except ValueError:
            return None
    return row['username']

def delete_session(token: str):
    if not token:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()

def purge_expired_sessions() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at < ?",
        (datetime.now().isoformat(),)
    )
    deleted = cursor.rowcount
    conn.commit()
    return deleted

def update_user_password(username: str, password_hash: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
    updated = cursor.rowcount > 0
    conn.commit()
    return updated

# ==================== NOTE OPERATIONS ====================

def get_user_notes(username: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT n.id, n.title, n.owner, n.created_at, n.updated_at,
               (SELECT COUNT(*) FROM collaborators WHERE note_id = n.id) AS collab_count,
               (SELECT role FROM collaborators WHERE note_id = n.id AND username = ?) AS user_role
        FROM notes n
        LEFT JOIN collaborators c ON n.id = c.note_id
        WHERE n.owner = ? OR c.username = ?
        GROUP BY n.id
        ORDER BY n.updated_at DESC
    """
    cursor.execute(query, (username, username, username))
    rows = cursor.fetchall()
    
    notes_list = []
    for r in rows:
        owner = r['owner']
        collab_count = r['collab_count'] or 0
        user_role = r['user_role']
        is_owner = (owner == username)
        is_collab = (not is_owner) or (collab_count > 0)
        notes_list.append({
            'id': r['id'],
            'title': r['title'],
            'owner': owner,
            'created_at': r['created_at'],
            'updated_at': r['updated_at'],
            'collab_count': collab_count,
            'user_role': 'owner' if is_owner else (user_role or 'read'),
            'is_owner': is_owner,
            'is_collab': is_collab
        })
    return notes_list

def get_note(note_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, owner, created_at, updated_at FROM notes WHERE id = ?", (note_id,))
    row = cursor.fetchone()
    if not row:
        return None
    
    cursor.execute("SELECT username, role FROM collaborators WHERE note_id = ?", (note_id,))
    collabs = {c['username']: c['role'] for c in cursor.fetchall()}
    
    return {
        'id': row['id'],
        'title': row['title'],
        'content': row['content'],
        'owner': row['owner'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'collaborators': collabs
    }

def create_note(note_id: str, title: str, owner: str, content: str = '') -> Dict[str, Any]:
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO notes (id, title, content, owner, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, title, content, owner, now, now)
    )
    conn.commit()
    
    return {
        'id': note_id,
        'title': title,
        'content': content,
        'owner': owner,
        'created_at': now,
        'updated_at': now,
        'collaborators': {}
    }

def update_note(note_id: str, title: Optional[str] = None, content: Optional[str] = None) -> bool:
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if title is not None and content is not None:
        cursor.execute("UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?", (title, content, now, note_id))
    elif title is not None:
        cursor.execute("UPDATE notes SET title = ?, updated_at = ? WHERE id = ?", (title, now, note_id))
    elif content is not None:
        cursor.execute("UPDATE notes SET content = ?, updated_at = ? WHERE id = ?", (content, now, note_id))
    else:
        return False
        
    updated = cursor.rowcount > 0
    conn.commit()
    return updated

def delete_note(note_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    return deleted

def add_collaborator(note_id: str, username: str, role: str = 'edit') -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
    if not cursor.fetchone():
        return False
        
    cursor.execute(
        "INSERT OR REPLACE INTO collaborators (note_id, username, role) VALUES (?, ?, ?)",
        (note_id, username, role)
    )
    cursor.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (datetime.now().isoformat(), note_id))
    conn.commit()
    return True

def remove_collaborator(note_id: str, username: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM collaborators WHERE note_id = ? AND username = ?", (note_id, username))
    removed = cursor.rowcount > 0
    if removed:
        cursor.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (datetime.now().isoformat(), note_id))
        conn.commit()
    return removed
