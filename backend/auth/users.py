"""User model backed by SQLite. Phase 1 single-tenant LAN deployment.

Schema mirrors r5-shared-contracts.md.
"""
import sqlite3
import time
from typing import Optional

from auth.passwords import hash_password, verify_password


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  is_admin INTEGER DEFAULT 0,
  settings_json TEXT DEFAULT '{}'
);
"""


def init_db(db_path: str) -> None:
    """Create users table if absent."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_user(
    db_path: str,
    username: str,
    password: str,
    is_admin: bool = False,
) -> int:
    if not username or not password:
        raise ValueError("username and password required")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at, is_admin) "
            "VALUES (?, ?, ?, ?)",
            (username, hash_password(password), time.time(), 1 if is_admin else 0),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"username {username!r} already exists") from e
    finally:
        conn.close()


def _row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "is_admin": bool(row["is_admin"]),
        "settings_json": row["settings_json"],
    }


def get_user_by_username(db_path: str, username: str) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def verify_credentials(db_path: str, username: str, password: str) -> Optional[dict]:
    user = get_user_by_username(db_path, username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def list_all_users(db_path: str) -> list:
    """Return all users sorted by id ASC. Excludes password_hash from each row."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, created_at, is_admin, settings_json "
            "FROM users ORDER BY id ASC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "created_at": r["created_at"],
                "is_admin": bool(r["is_admin"]),
                "settings_json": r["settings_json"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def update_password(db_path: str, username: str, new_password: str) -> None:
    if not new_password:
        raise ValueError("new password cannot be empty")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), username),
        )
        conn.commit()
    finally:
        conn.close()


def set_admin(db_path: str, username: str, is_admin: bool) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE username = ?",
            (1 if is_admin else 0, username),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(db_path: str, username: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def count_admins(db_path: str) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()
