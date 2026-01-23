"""
Main FastAPI Server for the Self-Healing Software System v2.0
WebSocket-based log streaming, error detection, and fix proposal system.

No actual fixes or test execution - focuses on:
- Error detection from live logs via WebSocket
- AST-based root cause analysis
- Fix proposals via email with interactive AST visualization
- Code review for PRs
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config, get_config
from utils.logger import setup_colored_logger
from utils.models import (
    LogEntry, DetectedError, WebSocketMessage, WebSocketConnection,
    UserRegistration, RepositoryInfo, PRInfo, ErrorSeverity,
)
from services import (
    get_log_analyzer, get_ast_service, get_ai_analyzer, get_email_service,
    get_github_service, get_error_replicator,
)
# Import AST trace and confidence validation services
try:
    from services.ast_trace_service import get_ast_trace_service
    from services.confidence_validator import get_confidence_validator
except ImportError:
    get_ast_trace_service = None
    get_confidence_validator = None

logger = setup_colored_logger("server")


# ============================================================================
# WebSocket Connection Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections from user services."""
    
    def __init__(self):
        # user_id -> WebSocketConnection
        self.active_connections: Dict[str, WebSocketConnection] = {}
        # user_id -> WebSocket
        self.websockets: Dict[str, WebSocket] = {}
        # user_id -> list of recent log entries
        self.log_buffers: Dict[str, list[LogEntry]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept a new WebSocket connection from a user's service."""
        await websocket.accept()
        
        import uuid
        connection_id = str(uuid.uuid4())
        
        self.websockets[user_id] = websocket
        self.active_connections[user_id] = WebSocketConnection(
            connection_id=connection_id,
            user_id=user_id,
            connected_at=datetime.utcnow(),
        )
        self.log_buffers[user_id] = []
        
        logger.info(f"✓ WebSocket connected: user={user_id}, conn={connection_id[:8]}")
        
    def disconnect(self, user_id: str):
        """Handle WebSocket disconnection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.websockets:
            del self.websockets[user_id]
            
        logger.info(f"✗ WebSocket disconnected: user={user_id}")
        
    async def send_message(self, user_id: str, message: WebSocketMessage):
        """Send a message to a specific user's service."""
        if user_id in self.websockets:
            await self.websockets[user_id].send_json(message.model_dump(mode='json'))
            
    async def broadcast(self, message: WebSocketMessage):
        """Broadcast a message to all connected services."""
        for user_id in self.websockets:
            await self.send_message(user_id, message)
            
    def add_log(self, user_id: str, log_entry: LogEntry):
        """Add a log entry to the user's buffer."""
        if user_id not in self.log_buffers:
            self.log_buffers[user_id] = []
        self.log_buffers[user_id].append(log_entry)
        
        # Keep only last 1000 logs
        if len(self.log_buffers[user_id]) > 1000:
            self.log_buffers[user_id] = self.log_buffers[user_id][-1000:]


# Global connection manager
manager = ConnectionManager()

# User registrations: user_id -> UserRegistration
user_registrations: Dict[str, UserRegistration] = {}

# Repository info: user_id -> RepositoryInfo
user_repos: Dict[str, RepositoryInfo] = {}


# ============================================================================
# Error Analysis Pipeline
# ============================================================================

async def analyze_error(user_id: str, log_entry: LogEntry):
    """
    Full error analysis pipeline:
    1. Parse error and extract details
    2. Build AST trace for error context
    3. Get AI root cause analysis
    4. Run multi-iteration confidence validation
    5. Generate fix proposal (if high confidence)
    6. Send email notification with AST trace
    """
    config = get_config()
    
    logger.info(f"Starting analysis for user {user_id}: {log_entry.message[:80]}...")
    
    try:
        # Get services
        log_analyzer = get_log_analyzer()
        ai_analyzer = get_ai_analyzer()
        email_service = get_email_service()
        
        # 1. Parse the error
        detected_error = log_analyzer.analyze_log(log_entry)
        
        if not detected_error:
            # Create basic detected error from log entry
            detected_error = DetectedError(
                error_type="UnknownError",
                message=log_entry.message,
                stack_trace=log_entry.stack_trace or "",
                source_file=log_entry.source_file or "unknown",
                line_number=log_entry.line_number or 0,
                severity=ErrorSeverity.MEDIUM,
                timestamp=log_entry.timestamp,
                api_endpoint=log_entry.api_endpoint,
                http_method=log_entry.http_method,
                original_payload=log_entry.payload,
            )
        
        logger.info(f"Detected error: {detected_error.error_type} - {detected_error.message[:50]}")
        
        # 2. Build AST trace for error context (if possible)
        ast_trace = None
        repo_info = user_repos.get(user_id)
        
        if get_ast_trace_service and detected_error.source_file and detected_error.source_file != "unknown":
            try:
                ast_trace_service = get_ast_trace_service()
                repo_path = str(repo_info.local_path) if repo_info and repo_info.local_path else ""
                
                ast_trace = ast_trace_service.trace_error(
                    error_file=detected_error.source_file,
                    error_line=detected_error.line_number or 1,
                    repo_path=repo_path,
                    source_code=None  # Will read from file
                )
                logger.info(f"AST trace built: {len(ast_trace.error_path)} nodes in path, "
                           f"{len(ast_trace.references)} references")
            except Exception as e:
                logger.warning(f"AST trace failed (continuing without it): {e}")
                ast_trace = None
        
        # 3. Get root cause analysis from AI
        ast_context = None
        ast_trace_service = None
        
        if get_ast_trace_service:
            ast_trace_service = get_ast_trace_service()
        
        if ast_trace and ast_trace.main_ast and ast_trace_service:
            # Build AI context from AST trace
            try:
                ast_context = ast_trace_service.build_ai_context(ast_trace)
            except Exception as e:
                logger.warning(f"Failed to build AI context from AST trace: {e}")
        
        analysis = await ai_analyzer.analyze_error(
            error=detected_error,
            ast_context=ast_context,
            source_code=ast_trace.error_context_code if ast_trace else None,
        )
        
        logger.info(f"AI Analysis complete - Initial Confidence: {analysis.confidence:.0%}")
        
        # 4. Run multi-iteration confidence validation
        validation_result = None
        if get_confidence_validator and detected_error.api_endpoint:
            try:
                confidence_validator = get_confidence_validator()
                validation_result = await confidence_validator.validate_error(
                    error=detected_error,
                    initial_analysis=analysis,
                    base_url=None  # Use default from config
                )
                logger.info(f"Validation complete - Final Confidence: {validation_result.confidence_score:.0f}%")
                
                if not validation_result.confidence_met:
                    logger.warning(f"Confidence {validation_result.confidence_score:.0f}% below threshold - "
                                  "will show possible causes instead of fix proposals")
            except Exception as e:
                logger.warning(f"Confidence validation failed (using initial analysis): {e}")
                validation_result = None
        
        # 5. Generate fix proposal (only if high confidence or no validation)
        fix_proposals = []
        should_suggest_fixes = True
        
        if validation_result:
            should_suggest_fixes = validation_result.confidence_met
        
        if should_suggest_fixes:
            fix_proposals = await ai_analyzer.generate_fix_proposals(
                error=detected_error,
                analysis=analysis,
                source_code=ast_trace.error_context_code if ast_trace else "",
            )
            
            if fix_proposals:
                logger.info(f"Generated {len(fix_proposals)} fix proposal(s)")
            else:
                logger.info("No specific fix proposals generated")
        else:
            logger.info("Skipping fix proposal generation due to low confidence")
        
        # 6. Determine recipient email
        registration = user_registrations.get(user_id)
        to_email = config.email.admin_email
        if registration and hasattr(registration, 'notification_email') and registration.notification_email:
            to_email = registration.notification_email
        
        # 7. Send email notification with AST trace and validation results
        if config.email.enable_notifications and to_email:
            await email_service.send_analysis_email(
                to_email=to_email,
                analysis=analysis,
                proposals=fix_proposals,
                ast_trace=ast_trace,  # Include AST trace
                validation_result=validation_result,  # Include validation results
            )
            logger.info(f"Email sent to {to_email}")
        else:
            logger.warning("Email notifications disabled or no recipient configured")
        
        # 8. Notify via WebSocket
        confidence_score = validation_result.confidence_score if validation_result else (analysis.confidence * 100)
        confidence_met = validation_result.confidence_met if validation_result else (confidence_score >= 75)
        
        await manager.send_message(user_id, WebSocketMessage(
            type="analysis_complete",
            user_id=user_id,
            payload={
                "error_type": detected_error.error_type,
                "root_cause": analysis.root_cause,
                "confidence": confidence_score,
                "confidence_met": confidence_met,
                "ast_trace_available": ast_trace is not None,
                "validation_iterations": len(validation_result.iterations) if validation_result else 0,
                "fix_proposals_count": len(fix_proposals),
                "fix_summary": fix_proposals[0].explanation[:100] if fix_proposals else "No fix proposal generated",
                "email_sent": bool(to_email and config.email.enable_notifications),
            },
        ))
        
        logger.info(f"Analysis complete for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in analysis pipeline: {e}")
        import traceback
        traceback.print_exc()
        
        # Notify user of failure
        await manager.send_message(user_id, WebSocketMessage(
            type="analysis_failed",
            user_id=user_id,
            payload={"error": str(e)},
        ))


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    config = get_config()
    
    logger.info("═" * 60)
    logger.info("   SELF-HEALING SOFTWARE SYSTEM v2.0 - STARTING")
    logger.info("═" * 60)
    logger.info(f"  Server: {config.server.host}:{config.server.port}")
    logger.info(f"  WebSocket Path: {config.server.websocket_path}")
    logger.info(f"  AI Provider: {config.ai.provider}")
    
    # Ensure directories exist
    config.logs_path.mkdir(parents=True, exist_ok=True)
    config.temp_path.mkdir(parents=True, exist_ok=True)
    config.github.repos_base_path.mkdir(parents=True, exist_ok=True)
    
    # Start background tasks
    # TODO: Start periodic git pull task
    # TODO: Start PR webhook listener
    
    yield
    
    # Cleanup
    logger.info("═" * 60)
    logger.info("   SELF-HEALING SYSTEM SHUTDOWN COMPLETE")
    logger.info("═" * 60)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Self-Healing Software System",
    description="WebSocket-based error detection and fix proposal system",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# WebSocket Endpoint - Log Streaming
# ============================================================================

@app.websocket("/ws/logs/{user_id}")
async def websocket_logs(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for receiving live logs from user services.
    
    User services connect here and stream their logs in real-time.
    When an error is detected, it triggers the analysis pipeline.
    """
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Receive log data from user's service
            data = await websocket.receive_json()
            
            try:
                # Parse log entry
                log_entry = LogEntry(**data)
                manager.add_log(user_id, log_entry)
                
                # Check if this is an error
                if log_entry.level.upper() in ["ERROR", "FATAL", "CRITICAL"]:
                    logger.warning(f"Error detected from user {user_id}: {log_entry.message[:100]}")
                    
                    # Trigger error analysis (in background)
                    asyncio.create_task(analyze_error(user_id, log_entry))
                    
                    # Acknowledge receipt
                    await manager.send_message(user_id, WebSocketMessage(
                        type="error_received",
                        user_id=user_id,
                        payload={"message": "Error logged and queued for analysis"},
                    ))
                    
            except ValidationError as e:
                logger.warning(f"Invalid log format from {user_id}: {e}")
                await manager.send_message(user_id, WebSocketMessage(
                    type="error",
                    user_id=user_id,
                    payload={"message": "Invalid log format", "details": str(e)},
                ))
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        manager.disconnect(user_id)


# ============================================================================
# REST API Endpoints - User Registration & Configuration
# ============================================================================

@app.post("/api/v1/register")
async def register_user(registration: UserRegistration):
    """
    Register a new user with their repository access.
    
    User provides:
    - GitHub/GitLab token (read-only access)
    - Repository URL
    - Base branch to monitor
    - Notification email
    """
    user_id = registration.user_id
    
    if user_id in user_registrations:
        raise HTTPException(status_code=409, detail="User already registered")
    
    user_registrations[user_id] = registration
    
    logger.info(f"✓ User registered: {user_id} - {registration.repo_url}")
    
    return {
        "status": "success",
        "user_id": user_id,
        "message": "Registration successful. Add the WebSocket client snippet to your service.",
        "websocket_url": f"ws://localhost:{config.server.port}/ws/logs/{user_id}",
    }


@app.get("/api/v1/user/{user_id}")
async def get_user(user_id: str):
    """Get user registration details."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    reg = user_registrations[user_id]
    return {
        "user_id": user_id,
        "repo_url": reg.repo_url,
        "base_branch": reg.base_branch,
        "registered_at": reg.registered_at.isoformat(),
        "connected": user_id in manager.active_connections and manager.active_connections[user_id].is_active,
    }


@app.delete("/api/v1/user/{user_id}")
async def unregister_user(user_id: str):
    """Unregister a user and clean up their data."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    del user_registrations[user_id]
    
    if user_id in user_repos:
        del user_repos[user_id]
        
    if user_id in manager.log_buffers:
        del manager.log_buffers[user_id]
        
    logger.info(f"✓ User unregistered: {user_id}")
    
    return {"status": "success", "message": "User unregistered successfully"}


# ============================================================================
# REST API Endpoints - Repository Management
# ============================================================================

@app.post("/api/v1/repo/{user_id}/sync")
async def sync_repository(user_id: str, background_tasks: BackgroundTasks):
    """
    Trigger a git pull to sync the user's repository.
    """
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Implement git clone/pull
    return {"status": "queued", "message": "Repository sync queued"}


@app.get("/api/v1/repo/{user_id}/status")
async def get_repo_status(user_id: str):
    """Get the status of the user's repository."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    repo_info = user_repos.get(user_id)
    
    if not repo_info:
        return {"status": "not_cloned", "message": "Repository not yet cloned"}
    
    return {
        "status": "ready",
        "local_path": str(repo_info.local_path),
        "last_pulled": repo_info.last_pulled.isoformat() if repo_info.last_pulled else None,
        "current_branch": repo_info.current_branch,
        "latest_commit": repo_info.latest_commit,
    }


# ============================================================================
# REST API Endpoints - Error Analysis
# ============================================================================

@app.get("/api/v1/logs/{user_id}")
async def get_logs(user_id: str, limit: int = 100):
    """Get recent logs for a user."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    logs = manager.log_buffers.get(user_id, [])
    return {
        "user_id": user_id,
        "total_logs": len(logs),
        "logs": [log.model_dump() for log in logs[-limit:]],
    }


@app.post("/api/v1/analyze/{user_id}")
async def trigger_analysis(user_id: str, background_tasks: BackgroundTasks):
    """Manually trigger error analysis for a user."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    logs = manager.log_buffers.get(user_id, [])
    errors = [log for log in logs if log.level.upper() in ["ERROR", "FATAL", "CRITICAL"]]
    
    if not errors:
        return {"status": "no_errors", "message": "No errors found in recent logs"}
    
    return {
        "status": "queued",
        "message": f"Analysis queued for {len(errors)} errors",
        "error_count": len(errors),
    }


# ============================================================================
# REST API Endpoints - Code Review
# ============================================================================

@app.post("/api/v1/review/{user_id}/pr")
async def review_pull_request(user_id: str, pr_info: PRInfo, background_tasks: BackgroundTasks):
    """Trigger a code review for a pull request."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "status": "queued",
        "message": f"Code review queued for PR #{pr_info.pr_number}",
        "pr_number": pr_info.pr_number,
    }


@app.post("/api/v1/webhook/github")
async def github_webhook(payload: dict, background_tasks: BackgroundTasks):
    """GitHub webhook endpoint for PR events."""
    event_type = payload.get("action", "")
    
    if event_type in ["opened", "synchronize", "reopened"]:
        pass
    
    return {"status": "received"}


# ============================================================================
# REST API Endpoints - Health & Status
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
    }


@app.get("/api/v1/status")
async def system_status():
    """Get system status and statistics."""
    return {
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "active_connections": len([c for c in manager.active_connections.values() if c.is_active]),
        "registered_users": len(user_registrations),
        "repositories_synced": len(user_repos),
        "ai_provider": config.ai.provider,
    }


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Entry point for the server."""
    print(r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║           ░█▀█░█░█░▀█▀░█▀█░░░░░█▀▀░█░█░█▀▄░█▀▀                ║    
    ║           ░█▀█░█░█░░█░░█░█░▄▄▄░█░░░█░█░█▀▄░█▀▀                ║
    ║           ░▀░▀░▀▀▀░░▀░░▀▀▀░░░░░▀▀▀░▀▀▀░▀░▀░▀▀▀                ║
    ║                                                               ║
    ║           AI-Driven AUTO-CURE Software System                 ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    config = get_config()
    
    uvicorn.run(
        "main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
