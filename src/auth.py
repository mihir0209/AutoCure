"""
Authentication module for the AutoCure dashboard.

Simple SQLite-backed user/session management with password hashing.
Creates a default ``admin / admin`` account on first run.
"""

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("auth")

_cfg = get_config()
_AUTH_DB = Path(_cfg.logs_path).parent / "data" / "auth.db"


@dataclass
class User:
    id: int
    username: str
    role: str
    created_at: str


class AuthManager:
    """Cookie/session based auth backed by SQLite."""

    def __init__(self, db_path: Path = _AUTH_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, User] = {}
        self._init_db()

    # ── database ──────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                salt          TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'admin',
                created_at    TEXT    NOT NULL
            );
        """)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        conn.close()
        if count == 0:
            self.create_user("admin", "admin", role="admin")
            logger.info("Default admin user created")

    # ── password hashing ──────────────────────────────────

    @staticmethod
    def _hash(password: str, salt: str | None = None):
        if salt is None:
            salt = os.urandom(32).hex()
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return h, salt

    # ── user CRUD ─────────────────────────────────────────

    def create_user(self, username: str, password: str, role: str = "admin"):
        h, salt = self._hash(password)
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, h, salt, role, datetime.utcnow().isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")
        finally:
            conn.close()

    def verify_user(self, username: str, password: str) -> Optional[User]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if not row:
            return None
        h, _ = self._hash(password, row["salt"])
        if h != row["password_hash"]:
            return None
        return User(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"])

    def list_users(self) -> list[User]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        conn.close()
        return [User(id=r["id"], username=r["username"], role=r["role"], created_at=r["created_at"]) for r in rows]

    def delete_user(self, user_id: int) -> bool:
        conn = self._conn()
        cur = conn.execute("DELETE FROM users WHERE id = ? AND username != 'admin'", (user_id,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def get_user_by_username(self, username: str) -> Optional[User]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if not row:
            return None
        return User(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"])

    def user_exists(self, username: str) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        return row is not None

    def change_password(self, user_id: int, new_password: str):
        h, salt = self._hash(new_password)
        conn = self._conn()
        conn.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (h, salt, user_id))
        conn.commit()
        conn.close()

    # ── sessions (in-memory) ──────────────────────────────

    def create_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = user
        return token

    def get_session(self, token: str) -> Optional[User]:
        return self._sessions.get(token)

    def delete_session(self, token: str):
        self._sessions.pop(token, None)


# ── singleton ─────────────────────────────────────────────

_mgr: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _mgr
    if _mgr is None:
        _mgr = AuthManager()
    return _mgr
