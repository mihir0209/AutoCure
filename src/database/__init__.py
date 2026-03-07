"""
Database module exports

db_service and redis_service use relative imports (from ..config)
that only work when the package is installed or run as a proper package.
We guard them with try/except so that importing database.report_store
(which uses absolute imports) still works in standalone mode.
"""

try:
    from .db_service import DatabaseService, db
except Exception:
    DatabaseService = None  # type: ignore[misc,assignment]
    db = None  # type: ignore[assignment]

try:
    from .redis_service import RedisService, redis_service
except Exception:
    RedisService = None  # type: ignore[misc,assignment]
    redis_service = None  # type: ignore[assignment]

from .report_store import ReportStore, get_report_store, REPORTS_DIR

__all__ = [
    "DatabaseService",
    "db",
    "RedisService",
    "redis_service",
    "ReportStore",
    "get_report_store",
    "REPORTS_DIR",
]
