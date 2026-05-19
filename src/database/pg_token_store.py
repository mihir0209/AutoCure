"""
PostgreSQL-backed TokenStore — same interface as token_store.TokenStore.
"""

import base64
from datetime import datetime
from typing import Optional, Dict, Any

import psycopg2
import psycopg2.extras

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("pg_token_store")


def _encode_token(token: str) -> str:
    if not token:
        return ""
    return base64.b64encode(token.encode("utf-8")).decode("ascii")


def _decode_token(encoded: str) -> str:
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return encoded


class PgTokenStore:
    """PostgreSQL-backed store for user registrations and PAT tokens."""

    def __init__(self):
        cfg = get_config().database
        self._dsn = (
            f"host={cfg.host} port={cfg.port} dbname={cfg.database} "
            f"user={cfg.user} password={cfg.password}"
        )
        self._ensure_schema()

    def _conn(self):
        c = psycopg2.connect(self._dsn)
        c.autocommit = True
        return c

    def _ensure_schema(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS token_registrations (
                        user_id TEXT PRIMARY KEY,
                        email TEXT DEFAULT '',
                        repo_url TEXT DEFAULT '',
                        repo_token TEXT DEFAULT '',
                        base_branch TEXT DEFAULT 'main',
                        notification_email TEXT DEFAULT NULL,
                        owner TEXT DEFAULT '',
                        created_at TEXT DEFAULT now()::text
                    )
                """)
        logger.info("PG token store ready")

    def save_registration(
        self,
        user_id: str,
        email: str = "",
        repo_url: str = "",
        repo_token: str = "",
        base_branch: str = "main",
        notification_email: Optional[str] = None,
        owner: str = "",
    ):
        encoded_token = _encode_token(repo_token)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO token_registrations
                        (user_id, email, repo_url, repo_token, base_branch, notification_email, owner)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        email = EXCLUDED.email,
                        repo_url = EXCLUDED.repo_url,
                        repo_token = EXCLUDED.repo_token,
                        base_branch = EXCLUDED.base_branch,
                        notification_email = EXCLUDED.notification_email,
                        owner = EXCLUDED.owner
                """, (user_id, email, repo_url, encoded_token, base_branch, notification_email, owner))

    def get_registration(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM token_registrations WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def get_all_registrations(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM token_registrations")
                for row in cur.fetchall():
                    d = self._row_to_dict(row)
                    result[d["user_id"]] = d
        return result

    def get_registrations_by_owner(self, owner: str) -> Dict[str, Dict[str, Any]]:
        result = {}
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM token_registrations WHERE owner = %s", (owner,))
                for row in cur.fetchall():
                    d = self._row_to_dict(row)
                    result[d["user_id"]] = d
        return result

    def delete_registration(self, user_id: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM token_registrations WHERE user_id = %s", (user_id,))

    def count(self) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM token_registrations")
                return cur.fetchone()[0]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        d = dict(row)
        d["repo_token"] = _decode_token(d.get("repo_token", ""))
        return d
