"""
PostgreSQL-backed ReportStore — same interface as report_store.ReportStore.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

from config import get_config
from utils.logger import setup_colored_logger

logger = setup_colored_logger("pg_report_store")

REPORTS_DIR = Path(get_config().logs_path).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_TABLE = "store_reports"


@dataclass
class ReportRecord:
    report_id: str
    user_id: str
    error_type: str
    severity: str
    confidence: float
    root_cause: str
    source_file: str
    line_number: int
    file_path: str
    file_name: str
    report_type: str
    proposals_count: int
    created_at: str
    proposals_json: str = ""
    branch_name: str = ""
    branch_url: str = ""
    compare_url: str = ""
    fix_status: str = "pending"


class PgReportStore:
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
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {_TABLE} (
                        report_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL DEFAULT '',
                        error_type TEXT NOT NULL DEFAULT 'Unknown',
                        severity TEXT NOT NULL DEFAULT 'medium',
                        confidence REAL NOT NULL DEFAULT 0.0,
                        root_cause TEXT NOT NULL DEFAULT '',
                        source_file TEXT NOT NULL DEFAULT '',
                        line_number INTEGER NOT NULL DEFAULT 0,
                        file_path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        report_type TEXT NOT NULL DEFAULT 'analysis',
                        proposals_count INTEGER NOT NULL DEFAULT 0,
                        proposals_json TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        branch_name TEXT NOT NULL DEFAULT '',
                        branch_url TEXT NOT NULL DEFAULT '',
                        compare_url TEXT NOT NULL DEFAULT '',
                        fix_status TEXT NOT NULL DEFAULT 'pending'
                    )
                """)
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_sr_user ON {_TABLE}(user_id)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_sr_type ON {_TABLE}(report_type)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_sr_created ON {_TABLE}(created_at DESC)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_sr_err ON {_TABLE}(error_type)")
        self.normalize_existing_confidence()
        logger.info("PG report store ready")

    # re-export _norm_conf as static so callers can use it
    @staticmethod
    def _norm_conf(confidence: float) -> float:
        if confidence <= 1.0:
            return max(0.0, confidence)
        if confidence <= 10.0:
            return confidence / 10.0
        if confidence <= 100.0:
            return confidence / 100.0
        return 1.0

    def normalize_existing_confidence(self) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {_TABLE} SET confidence = 1.0 WHERE confidence > 1.0")
                n = cur.rowcount
        if n:
            logger.info(f"Normalized {n} report confidence values (PG)")
        return n

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
        proposals_json: str = "",
    ) -> str:
        report_id = uuid.uuid4().hex[:12]
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO {_TABLE}
                        (report_id, user_id, error_type, severity, confidence,
                         root_cause, source_file, line_number,
                         file_path, file_name, report_type, proposals_count,
                         proposals_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (report_id, user_id, error_type, severity, confidence,
                     root_cause[:500], source_file, int(line_number or 0),
                     file_path, file_name, report_type, proposals_count,
                     proposals_json, now),
                )
        logger.info(f"Report indexed (PG): {report_id} ({report_type})")
        return report_id

    def _row_to_record(self, row) -> ReportRecord:
        return ReportRecord(**dict(row))

    def get(self, report_id: str) -> Optional[ReportRecord]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT * FROM {_TABLE} WHERE report_id = %s", (report_id,))
                row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def update_branch_info(self, report_id: str, branch_name: str = "",
                           branch_url: str = "", compare_url: str = "",
                           fix_status: str = "pending") -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE {_TABLE}
                       SET branch_name=%s, branch_url=%s, compare_url=%s, fix_status=%s
                       WHERE report_id=%s""",
                    (branch_name, branch_url, compare_url, fix_status, report_id),
                )
                return cur.rowcount > 0

    def get_file_path(self, report_id: str) -> Optional[str]:
        rec = self.get(report_id)
        if rec and Path(rec.file_path).exists():
            return rec.file_path
        return None

    def list_reports(self, user_id: Optional[str] = None,
                     report_type: Optional[str] = None,
                     error_type: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> List[ReportRecord]:
        clauses, params = [], []
        if user_id:
            clauses.append("user_id = %s"); params.append(user_id)
        if report_type:
            clauses.append("report_type = %s"); params.append(report_type)
        if error_type:
            clauses.append("error_type LIKE %s"); params.append(f"%{error_type}%")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM {_TABLE} {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    params + [limit, offset],
                )
                return [self._row_to_record(r) for r in cur.fetchall()]

    def count(self, user_id: Optional[str] = None, report_type: Optional[str] = None) -> int:
        clauses, params = [], []
        if user_id:
            clauses.append("user_id = %s"); params.append(user_id)
        if report_type:
            clauses.append("report_type = %s"); params.append(report_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM {_TABLE} {where}", params)
                return cur.fetchone()[0]

    def delete(self, report_id: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {_TABLE} WHERE report_id = %s", (report_id,))
                return cur.rowcount > 0

    def delete_with_file(self, report_id: str) -> bool:
        rec = self.get(report_id)
        if not rec:
            return False
        p = Path(rec.file_path)
        if p.exists():
            p.unlink()
        return self.delete(report_id)

    def get_latest_for_user(self, user_id: str) -> Optional[ReportRecord]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM {_TABLE} WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def count_for_user(self, user_id: str) -> int:
        return self.count(user_id=user_id)

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT COUNT(*) AS c FROM {_TABLE}")
                total = cur.fetchone()["c"]

                by_type, by_severity = {}, {}
                cur.execute(f"SELECT report_type, COUNT(*) AS c FROM {_TABLE} GROUP BY report_type")
                for r in cur.fetchall():
                    by_type[r["report_type"]] = r["c"]
                cur.execute(f"SELECT severity, COUNT(*) AS c FROM {_TABLE} GROUP BY severity")
                for r in cur.fetchall():
                    by_severity[r["severity"]] = r["c"]

                cur.execute(f"SELECT AVG(confidence) AS a FROM {_TABLE}")
                avg_conf = cur.fetchone()["a"] or 0.0

                cur.execute(f"SELECT COUNT(DISTINCT error_type) AS c FROM {_TABLE}")
                unique_errors = cur.fetchone()["c"]

                cur.execute(f"SELECT SUM(proposals_count) AS s FROM {_TABLE}")
                total_proposals = cur.fetchone()["s"] or 0

                cur.execute(f"SELECT created_at FROM {_TABLE} ORDER BY created_at DESC LIMIT 1")
                latest = cur.fetchone()

        return {
            "total": total,
            "total_reports": total,
            "by_type": by_type,
            "by_severity": by_severity,
            "avg_confidence": min(avg_conf * 100, 100),
            "unique_error_types": unique_errors,
            "total_proposals": total_proposals,
            "latest_report_at": latest["created_at"] if latest else None,
        }
