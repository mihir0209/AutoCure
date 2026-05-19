"""
PostgreSQL-backed AuthManager — same interface as auth.AuthManager.
"""

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import psycopg2
import psycopg2.extras

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("pg_auth")


@dataclass
class User:
    id: int
    username: str
    role: str
    created_at: str


class PgAuthManager:
    """Cookie/session based auth backed by PostgreSQL."""

    def __init__(self):
        cfg = get_config().database
        self._dsn = (
            f"host={cfg.host} port={cfg.port} dbname={cfg.database} "
            f"user={cfg.user} password={cfg.password}"
        )
        self._sessions: Dict[str, User] = {}
        self._ensure_schema()
        self._seed_admin()

    def _conn(self):
        c = psycopg2.connect(self._dsn)
        c.autocommit = True
        return c

    def _ensure_schema(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS auth_users (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'admin',
                        created_at TEXT NOT NULL
                    )
                """)
        logger.info("PG auth schema ready")

    def _seed_admin(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM auth_users")
                if cur.fetchone()[0] == 0:
                    self.create_user("admin", "admin", role="admin")
                    logger.info("Default admin user created (PG)")

    @staticmethod
    def _hash(password: str, salt: str | None = None):
        if salt is None:
            salt = os.urandom(32).hex()
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return h, salt

    def create_user(self, username: str, password: str, role: str = "admin"):
        h, salt = self._hash(password)
        with self._conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO auth_users (username, password_hash, salt, role, created_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (username, h, salt, role, datetime.utcnow().isoformat()),
                    )
                except psycopg2.errors.UniqueViolation:
                    raise ValueError(f"Username '{username}' already exists")

    def verify_user(self, username: str, password: str) -> Optional[User]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM auth_users WHERE username = %s", (username,))
                row = cur.fetchone()
        if not row:
            return None
        h, _ = self._hash(password, row["salt"])
        if h != row["password_hash"]:
            return None
        return User(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"])

    def list_users(self) -> list[User]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM auth_users ORDER BY id")
                rows = cur.fetchall()
        return [User(id=r["id"], username=r["username"], role=r["role"], created_at=r["created_at"]) for r in rows]

    def delete_user(self, user_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM auth_users WHERE id = %s AND username != 'admin'", (user_id,))
                return cur.rowcount > 0

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM auth_users WHERE username = %s", (username,))
                row = cur.fetchone()
        if not row:
            return None
        return User(id=row["id"], username=row["username"], role=row["role"], created_at=row["created_at"])

    def user_exists(self, username: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM auth_users WHERE username = %s", (username,))
                return cur.fetchone() is not None

    def change_password(self, user_id: int, new_password: str):
        h, salt = self._hash(new_password)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE auth_users SET password_hash=%s, salt=%s WHERE id=%s", (h, salt, user_id))

    # Sessions remain in-memory
    def create_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = user
        return token

    def get_session(self, token: str) -> Optional[User]:
        return self._sessions.get(token)

    def delete_session(self, token: str):
        self._sessions.pop(token, None)
