"""
Database Service - Async PostgreSQL Connection Management
Handles database connections, queries, and transaction management.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from asyncpg import Pool, Connection

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

from ..config import config

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Async PostgreSQL database service using asyncpg.
    Provides connection pooling and common database operations.
    """
    
    def __init__(self):
        self.pool: Optional["Pool"] = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the database connection pool."""
        if not ASYNCPG_AVAILABLE:
            logger.error("asyncpg not installed. Install with: pip install asyncpg")
            return
            
        if self._initialized:
            return
            
        try:
            self.pool = await asyncpg.create_pool(
                host=config.database.host,
                port=config.database.port,
                user=config.database.user,
                password=config.database.password,
                database=config.database.database,
                min_size=config.database.min_connections,
                max_size=config.database.max_connections,
                command_timeout=60,
                # SSL configuration for production
                # ssl='require' if config.database.ssl else None
            )
            self._initialized = True
            logger.info(f"Database pool initialized: {config.database.host}:{config.database.port}")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    async def close(self) -> None:
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("Database pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        async with self.pool.acquire() as conn:
            yield conn
    
    @asynccontextmanager
    async def transaction(self):
        """Execute operations within a transaction."""
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    # =========================================================================
    # User Operations
    # =========================================================================
    
    async def create_user(
        self,
        email: str,
        password_hash: str,
        name: Optional[str] = None
    ) -> Optional[UUID]:
        """Create a new user and return their ID."""
        async with self.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, password_hash, name)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    email, password_hash, name
                )
                return row['id'] if row else None
            except asyncpg.UniqueViolationError:
                logger.warning(f"User with email {email} already exists")
                return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email address."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1 AND is_active = TRUE",
                email
            )
            return dict(row) if row else None
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1 AND is_active = TRUE",
                user_id
            )
            return dict(row) if row else None
    
    async def update_user_websocket_token(self, user_id: UUID, token: str) -> bool:
        """Update user's WebSocket authentication token."""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE users SET websocket_token = $2, updated_at = NOW()
                WHERE id = $1
                """,
                user_id, token
            )
            return result == "UPDATE 1"
    
    async def update_last_login(self, user_id: UUID) -> None:
        """Update user's last login timestamp."""
        async with self.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login_at = NOW() WHERE id = $1",
                user_id
            )
    
    # =========================================================================
    # Repository Operations
    # =========================================================================
    
    async def create_repository(
        self,
        user_id: UUID,
        repo_url: str,
        repo_name: str,
        repo_owner: str,
        base_branch: str = 'main',
        github_token: Optional[str] = None,
        admin_email: Optional[str] = None
    ) -> Optional[UUID]:
        """Create a new repository entry."""
        async with self.acquire() as conn:
            try:
                # Encrypt the GitHub token if provided
                encrypted_token = None
                if github_token:
                    encrypted_token = await conn.fetchval(
                        "SELECT pgp_sym_encrypt($1, $2)",
                        github_token, config.database.encryption_key
                    )
                
                row = await conn.fetchrow(
                    """
                    INSERT INTO repositories (
                        user_id, repo_url, repo_name, repo_owner, 
                        base_branch, github_token_encrypted, admin_email
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    user_id, repo_url, repo_name, repo_owner,
                    base_branch, encrypted_token, admin_email
                )
                return row['id'] if row else None
            except asyncpg.UniqueViolationError:
                logger.warning(f"Repository {repo_url} already exists for user {user_id}")
                return None
            except asyncpg.RaiseError as e:
                # This catches the repo limit trigger exception
                logger.warning(f"Repository limit reached for user {user_id}: {e}")
                return None
    
    async def get_repositories_by_user(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get all repositories for a user."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, repo_url, repo_name, repo_owner, base_branch,
                       workspace_path, current_storage_mb, last_commit_hash,
                       last_sync_at, sync_status, is_monitoring_active,
                       admin_email, created_at
                FROM repositories
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id
            )
            return [dict(row) for row in rows]
    
    async def get_repository_by_id(self, repo_id: UUID) -> Optional[Dict[str, Any]]:
        """Get repository by ID with decrypted token."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT r.*,
                       pgp_sym_decrypt(r.github_token_encrypted, $2) as github_token
                FROM repositories r
                WHERE r.id = $1
                """,
                repo_id, config.database.encryption_key
            )
            return dict(row) if row else None
    
    async def update_repository_sync_status(
        self,
        repo_id: UUID,
        status: str,
        commit_hash: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update repository sync status."""
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE repositories SET
                    sync_status = $2,
                    last_commit_hash = COALESCE($3, last_commit_hash),
                    last_sync_at = CASE WHEN $2 = 'synced' THEN NOW() ELSE last_sync_at END,
                    sync_error_message = $4,
                    updated_at = NOW()
                WHERE id = $1
                """,
                repo_id, status, commit_hash, error_message
            )
    
    async def update_repository_storage(self, repo_id: UUID, storage_mb: float) -> None:
        """Update repository storage usage."""
        async with self.acquire() as conn:
            await conn.execute(
                "UPDATE repositories SET current_storage_mb = $2 WHERE id = $1",
                repo_id, storage_mb
            )
    
    async def delete_repository(self, repo_id: UUID) -> bool:
        """Delete a repository (cascades to related tables)."""
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM repositories WHERE id = $1",
                repo_id
            )
            return result == "DELETE 1"
    
    # =========================================================================
    # Error Log Operations
    # =========================================================================
    
    async def create_error_log(
        self,
        repo_id: UUID,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
        function_name: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        request_payload: Optional[Dict] = None,
        log_level: str = 'ERROR',
        raw_log_entry: Optional[str] = None,
        severity: str = 'medium',
        occurred_at: Optional[datetime] = None
    ) -> Optional[UUID]:
        """Create a new error log entry."""
        import json
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO error_logs (
                    repo_id, error_type, error_message, stack_trace,
                    file_path, line_number, function_name,
                    api_endpoint, http_method, request_payload,
                    log_level, raw_log_entry, severity, occurred_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                repo_id, error_type, error_message, stack_trace,
                file_path, line_number, function_name,
                api_endpoint, http_method, 
                json.dumps(request_payload) if request_payload else None,
                log_level, raw_log_entry, severity,
                occurred_at or datetime.now(timezone.utc)
            )
            return row['id'] if row else None
    
    async def get_error_logs_by_repo(
        self,
        repo_id: UUID,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get error logs for a repository."""
        async with self.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM error_logs
                    WHERE repo_id = $1 AND status = $2
                    ORDER BY occurred_at DESC
                    LIMIT $3
                    """,
                    repo_id, status, limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM error_logs
                    WHERE repo_id = $1
                    ORDER BY occurred_at DESC
                    LIMIT $2
                    """,
                    repo_id, limit
                )
            return [dict(row) for row in rows]
    
    async def update_error_log_status(self, error_id: UUID, status: str) -> None:
        """Update error log status."""
        async with self.acquire() as conn:
            update_fields = "status = $2"
            if status == 'resolved':
                update_fields += ", resolved_at = NOW()"
            
            await conn.execute(
                f"UPDATE error_logs SET {update_fields} WHERE id = $1",
                error_id, status
            )
    
    # =========================================================================
    # Analysis History Operations
    # =========================================================================
    
    async def create_analysis(
        self,
        error_log_id: UUID,
        repo_id: UUID,
        root_cause: str,
        confidence: float,
        fix_proposal: str,
        fix_diff: Optional[str] = None,
        affected_files: Optional[List[str]] = None,
        risk_level: str = 'medium',
        risk_explanation: Optional[str] = None,
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None,
        tokens_used: Optional[int] = None,
        analysis_duration_ms: Optional[int] = None,
        ast_context: Optional[Dict] = None
    ) -> Optional[UUID]:
        """Create a new analysis history entry."""
        import json
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO analysis_history (
                    error_log_id, repo_id, root_cause, root_cause_confidence,
                    fix_proposal, fix_diff, affected_files,
                    risk_level, risk_explanation,
                    ai_provider, ai_model, tokens_used, analysis_duration_ms,
                    ast_context
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                error_log_id, repo_id, root_cause, confidence,
                fix_proposal, fix_diff,
                json.dumps(affected_files) if affected_files else None,
                risk_level, risk_explanation,
                ai_provider, ai_model, tokens_used, analysis_duration_ms,
                json.dumps(ast_context) if ast_context else None
            )
            return row['id'] if row else None
    
    async def mark_analysis_email_sent(
        self,
        analysis_id: UUID,
        recipient: str
    ) -> None:
        """Mark analysis email as sent."""
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE analysis_history SET
                    email_sent = TRUE,
                    email_sent_at = NOW(),
                    email_recipient = $2
                WHERE id = $1
                """,
                analysis_id, recipient
            )
    
    # =========================================================================
    # WebSocket Session Operations
    # =========================================================================
    
    async def create_websocket_session(
        self,
        user_id: UUID,
        connection_id: str,
        repo_id: Optional[UUID] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[UUID]:
        """Create a new WebSocket session record."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO websocket_sessions (
                    user_id, connection_id, repo_id, client_ip, user_agent
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                user_id, connection_id, repo_id, client_ip, user_agent
            )
            return row['id'] if row else None
    
    async def update_websocket_heartbeat(self, connection_id: str) -> None:
        """Update WebSocket session heartbeat."""
        async with self.acquire() as conn:
            await conn.execute(
                "UPDATE websocket_sessions SET last_heartbeat_at = NOW() WHERE connection_id = $1",
                connection_id
            )
    
    async def close_websocket_session(self, connection_id: str) -> None:
        """Mark WebSocket session as closed."""
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE websocket_sessions SET
                    is_active = FALSE,
                    disconnected_at = NOW()
                WHERE connection_id = $1
                """,
                connection_id
            )
    
    # =========================================================================
    # Audit Log Operations
    # =========================================================================
    
    async def create_audit_log(
        self,
        action: str,
        user_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """Create an audit log entry."""
        import json
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (
                    user_id, action, resource_type, resource_id,
                    details, ip_address, user_agent
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                user_id, action, resource_type, resource_id,
                json.dumps(details) if details else None,
                ip_address, user_agent
            )
    
    # =========================================================================
    # Statistics Operations
    # =========================================================================
    
    async def get_user_stats(self, user_id: UUID) -> Dict[str, Any]:
        """Get statistics for a user."""
        async with self.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM repositories WHERE user_id = $1) as total_repos,
                    (SELECT SUM(current_storage_mb) FROM repositories WHERE user_id = $1) as total_storage_mb,
                    (SELECT COUNT(*) FROM error_logs el 
                     JOIN repositories r ON el.repo_id = r.id 
                     WHERE r.user_id = $1) as total_errors,
                    (SELECT COUNT(*) FROM analysis_history ah 
                     JOIN repositories r ON ah.repo_id = r.id 
                     WHERE r.user_id = $1) as total_analyses
                """,
                user_id
            )
            return dict(stats) if stats else {}


# Global database service instance
db = DatabaseService()
