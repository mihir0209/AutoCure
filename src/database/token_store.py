"""
SQLite Token Store for the Self-Healing Software System v2.0

Stores user registrations and PAT tokens securely in SQLite
instead of plaintext JSON files. Tokens are stored with base64
obfuscation (for basic protection; for production use a proper
secret manager or encryption-at-rest).
"""

import sqlite3
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("token_store")

# ─── Database path ───
_cfg = get_config()
DB_DIR = Path(_cfg.logs_path).parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "tokens.db"


def _encode_token(token: str) -> str:
    """Encode a token for storage (base64 obfuscation)."""
    if not token:
        return ""
    return base64.b64encode(token.encode("utf-8")).decode("ascii")


def _decode_token(encoded: str) -> str:
    """Decode a stored token."""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return encoded  # Return as-is if decoding fails


class TokenStore:
    """SQLite-backed store for user registrations and PAT tokens."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS registrations (
                    user_id      TEXT PRIMARY KEY,
                    email        TEXT DEFAULT '',
                    repo_url     TEXT DEFAULT '',
                    repo_token   TEXT DEFAULT '',
                    base_branch  TEXT DEFAULT 'main',
                    notification_email TEXT DEFAULT NULL,
                    owner        TEXT DEFAULT '',
                    created_at   TEXT DEFAULT (datetime('now'))
                )
            """)
            # Migrate: add owner column if missing (existing DBs)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(registrations)").fetchall()]
            if "owner" not in cols:
                conn.execute("ALTER TABLE registrations ADD COLUMN owner TEXT DEFAULT ''")
            conn.commit()
        logger.info(f"Token store initialized: {self.db_path}")

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
        """Insert or update a user registration with encoded token."""
        encoded_token = _encode_token(repo_token)
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO registrations (user_id, email, repo_url, repo_token, base_branch, notification_email, owner)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email = excluded.email,
                    repo_url = excluded.repo_url,
                    repo_token = excluded.repo_token,
                    base_branch = excluded.base_branch,
                    notification_email = excluded.notification_email,
                    owner = excluded.owner
            """, (user_id, email, repo_url, encoded_token, base_branch, notification_email, owner))
            conn.commit()

    def get_registration(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single user registration with decoded token."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM registrations WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def get_all_registrations(self) -> Dict[str, Dict[str, Any]]:
        """Load all registrations with decoded tokens."""
        result = {}
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM registrations").fetchall()
            for row in rows:
                d = self._row_to_dict(row)
                result[d["user_id"]] = d
        return result

    def get_registrations_by_owner(self, owner: str) -> Dict[str, Dict[str, Any]]:
        """Load registrations belonging to a specific owner."""
        result = {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE owner = ?", (owner,)
            ).fetchall()
            for row in rows:
                d = self._row_to_dict(row)
                result[d["user_id"]] = d
        return result

    def delete_registration(self, user_id: str):
        """Delete a user registration."""
        with self._conn() as conn:
            conn.execute("DELETE FROM registrations WHERE user_id = ?", (user_id,))
            conn.commit()

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["repo_token"] = _decode_token(d.get("repo_token", ""))
        return d


# ─── Singleton ───
_token_store: Optional[TokenStore] = None


def get_token_store() -> TokenStore:
    global _token_store
    if _token_store is None:
        _token_store = TokenStore()
    return _token_store
