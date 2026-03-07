"""
SQLite Report Store for the Self-Healing Software System v2.0

Lightweight report metadata storage using SQLite (no external DB needed).
Stores the mapping between report IDs, files on disk, and analysis metadata.
Reports themselves are full HTML files on the filesystem; this DB just indexes them.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("report_store")

# ─── Database path ───
_cfg = get_config()
DB_DIR = Path(_cfg.logs_path).parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "reports.db"

REPORTS_DIR = Path(_cfg.logs_path).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
#  Data classes
# ════════════════════════════════════════════════════════════════

@dataclass
class ReportRecord:
    """One row in the reports table."""
    report_id: str
    user_id: str
    error_type: str
    severity: str
    confidence: float
    root_cause: str
    source_file: str
    line_number: int
    file_path: str          # absolute path on disk
    file_name: str          # just the filename
    report_type: str        # "analysis" | "review"
    proposals_count: int
    created_at: str         # ISO-8601


# ════════════════════════════════════════════════════════════════
#  Report Store (sync — SQLite doesn't need async)
# ════════════════════════════════════════════════════════════════

class ReportStore:
    """
    SQLite-backed index for HTML reports on disk.

    Thread-safe: each method opens its own connection (or uses WAL).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    # ── Schema ──

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _ensure_schema(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    report_id   TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL DEFAULT '',
                    error_type  TEXT NOT NULL DEFAULT 'Unknown',
                    severity    TEXT NOT NULL DEFAULT 'medium',
                    confidence  REAL NOT NULL DEFAULT 0.0,
                    root_cause  TEXT NOT NULL DEFAULT '',
                    source_file TEXT NOT NULL DEFAULT '',
                    line_number INTEGER NOT NULL DEFAULT 0,
                    file_path   TEXT NOT NULL,
                    file_name   TEXT NOT NULL,
                    report_type TEXT NOT NULL DEFAULT 'analysis',
                    proposals_count INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_reports_user
                    ON reports(user_id);
                CREATE INDEX IF NOT EXISTS idx_reports_type
                    ON reports(report_type);
                CREATE INDEX IF NOT EXISTS idx_reports_created
                    ON reports(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reports_error_type
                    ON reports(error_type);
            """)
            conn.commit()
            logger.info(f"Report store ready: {self.db_path}")
        finally:
            conn.close()

    # ── CRUD ──

    def insert(
        self,
        file_path: str,
        file_name: str,
        report_type: str = "analysis",
        user_id: str = "",
        error_type: str = "Unknown",
        severity: str = "medium",
        confidence: float = 0.0,
        root_cause: str = "",
        source_file: str = "",
        line_number: int = 0,
        proposals_count: int = 0,
    ) -> str:
        """Insert a new report record. Returns the generated report_id."""
        report_id = uuid.uuid4().hex[:12]
        now = datetime.utcnow().isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO reports
                    (report_id, user_id, error_type, severity, confidence,
                     root_cause, source_file, line_number,
                     file_path, file_name, report_type, proposals_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, user_id, error_type, severity, confidence,
                 root_cause[:500], source_file, line_number,
                 file_path, file_name, report_type, proposals_count, now),
            )
            conn.commit()
            logger.info(f"Report indexed: {report_id} ({report_type})")
            return report_id
        finally:
            conn.close()

    def get(self, report_id: str) -> Optional[ReportRecord]:
        """Fetch a single report by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            if not row:
                return None
            return ReportRecord(**dict(row))
        finally:
            conn.close()

    def get_file_path(self, report_id: str) -> Optional[str]:
        """Get the filesystem path for a report (for serving)."""
        rec = self.get(report_id)
        if rec and Path(rec.file_path).exists():
            return rec.file_path
        return None

    def list_reports(
        self,
        user_id: Optional[str] = None,
        report_type: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReportRecord]:
        """List reports with optional filters."""
        clauses: List[str] = []
        params: List[Any] = []

        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if report_type:
            clauses.append("report_type = ?")
            params.append(report_type)
        if error_type:
            clauses.append("error_type LIKE ?")
            params.append(f"%{error_type}%")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM reports {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [ReportRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    def count(
        self,
        user_id: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> int:
        """Count reports with optional filters."""
        clauses: List[str] = []
        params: List[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if report_type:
            clauses.append("report_type = ?")
            params.append(report_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._get_conn()
        try:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM reports {where}", params).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def delete(self, report_id: str) -> bool:
        """Delete a report record (does NOT delete the HTML file)."""
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM reports WHERE report_id = ?", (report_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_with_file(self, report_id: str) -> bool:
        """Delete both the record and the HTML file on disk."""
        rec = self.get(report_id)
        if not rec:
            return False
        # Delete file
        p = Path(rec.file_path)
        if p.exists():
            p.unlink()
        # Delete record
        return self.delete(report_id)

    def stats(self) -> Dict[str, Any]:
        """Quick statistics for the dashboard."""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
            by_type = {}
            for row in conn.execute(
                "SELECT report_type, COUNT(*) as c FROM reports GROUP BY report_type"
            ).fetchall():
                by_type[row["report_type"]] = row["c"]

            by_severity = {}
            for row in conn.execute(
                "SELECT severity, COUNT(*) as c FROM reports GROUP BY severity"
            ).fetchall():
                by_severity[row["severity"]] = row["c"]

            avg_conf = conn.execute(
                "SELECT AVG(confidence) as a FROM reports"
            ).fetchone()["a"] or 0.0

            unique_errors = conn.execute(
                "SELECT COUNT(DISTINCT error_type) as c FROM reports"
            ).fetchone()["c"]

            total_proposals = conn.execute(
                "SELECT SUM(proposals_count) as s FROM reports"
            ).fetchone()["s"] or 0

            latest = conn.execute(
                "SELECT created_at FROM reports ORDER BY created_at DESC LIMIT 1"
            ).fetchone()

            return {
                "total": total,
                "total_reports": total,
                "by_type": by_type,
                "by_severity": by_severity,
                "avg_confidence": avg_conf * 100,   # 0-100 scale
                "unique_error_types": unique_errors,
                "total_proposals": total_proposals,
                "latest_report_at": latest["created_at"] if latest else None,
            }
        finally:
            conn.close()


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

_store: Optional[ReportStore] = None


def get_report_store() -> ReportStore:
    """Get or create the report-store singleton."""
    global _store
    if _store is None:
        _store = ReportStore()
    return _store
