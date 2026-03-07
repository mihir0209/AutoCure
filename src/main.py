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
import hmac
import hashlib
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Query, Request, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from database.report_store import get_report_store, REPORTS_DIR
from auth import get_auth_manager
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
        # Track whether each user buffer contains errors (prevents auto-flush)
        self._has_errors: Dict[str, bool] = {}
        
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
        # Also forward to dashboard watchers
        await self.broadcast_dashboard(message.model_dump(mode='json'))

    # ──── Dashboard watchers ────
    def __init_dashboard__(self):
        if not hasattr(self, 'dashboard_sockets'):
            self.dashboard_sockets: list[WebSocket] = []

    async def add_dashboard(self, ws: WebSocket):
        self.__init_dashboard__()
        await ws.accept()
        self.dashboard_sockets.append(ws)

    def remove_dashboard(self, ws: WebSocket):
        self.__init_dashboard__()
        if ws in self.dashboard_sockets:
            self.dashboard_sockets.remove(ws)

    async def broadcast_dashboard(self, data: dict):
        """Send an event to all dashboard UI watchers."""
        self.__init_dashboard__()
        dead = []
        for ws in self.dashboard_sockets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.dashboard_sockets.remove(ws)

    def add_log(self, user_id: str, log_entry: LogEntry):
        """Add a log entry to the user's buffer."""
        if user_id not in self.log_buffers:
            self.log_buffers[user_id] = []
        self.log_buffers[user_id].append(log_entry)

        # Track error presence (prevents auto-flush)
        if log_entry.level.upper() in ("ERROR", "FATAL", "CRITICAL"):
            self._has_errors[user_id] = True
        
        # Keep only last 2000 logs
        if len(self.log_buffers[user_id]) > 2000:
            self.log_buffers[user_id] = self.log_buffers[user_id][-2000:]

    def flush_logs(self, user_id: str, force: bool = False):
        """Flush (discard) cached logs for a user.

        If *force* is False the buffer is only cleared when it contains
        no error-level entries.  When *force* is True the buffer is
        cleared unconditionally (manual clear by the user).
        """
        if user_id not in self.log_buffers:
            return
        if force:
            self.log_buffers[user_id] = []
            self._has_errors[user_id] = False
            return
        # Auto-flush: skip if the buffer contains errors
        if self._has_errors.get(user_id, False):
            return
        self.log_buffers[user_id] = []

    def periodic_flush_all(self):
        """Auto-flush every user buffer that has NO errors."""
        for uid in list(self.log_buffers.keys()):
            self.flush_logs(uid, force=False)


# Global connection manager
manager = ConnectionManager()

# User registrations: user_id -> UserRegistration
user_registrations: Dict[str, UserRegistration] = {}

# Repository info: user_id -> RepositoryInfo
user_repos: Dict[str, RepositoryInfo] = {}

# Persistent registration storage
_REGISTRATIONS_FILE = Path(__file__).parent.parent / "data" / "registrations.json"


def _save_registrations():
    """Persist user registrations to JSON file."""
    _REGISTRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for uid, reg in user_registrations.items():
        data[uid] = {
            "user_id": reg.user_id,
            "email": reg.email,
            "repo_url": reg.repo_url,
            "repo_token": reg.repo_token,
            "base_branch": reg.base_branch,
            "notification_email": reg.notification_email,
        }
    _REGISTRATIONS_FILE.write_text(json.dumps(data, indent=2))


def _load_registrations():
    """Load persisted user registrations from JSON file."""
    if not _REGISTRATIONS_FILE.exists():
        return
    try:
        data = json.loads(_REGISTRATIONS_FILE.read_text())
        for uid, info in data.items():
            user_registrations[uid] = UserRegistration(**info)
        logger.info(f"Loaded {len(data)} persisted registrations")
    except Exception as e:
        logger.warning(f"Failed to load registrations: {e}")


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

        # Broadcast to dashboard watchers
        asyncio.create_task(manager.broadcast_dashboard({
            "type": "error",
            "message": f"[{user_id}] {detected_error.error_type}: {detected_error.message[:120]}",
            "user_id": user_id,
        }))
        
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
            user_id=user_id,
        )
        
        logger.info(f"AI Analysis complete - Initial Confidence: {analysis.confidence:.0%}")

        # Broadcast analysis progress to dashboard
        asyncio.create_task(manager.broadcast_dashboard({
            "type": "analysis",
            "message": f"[{user_id}] Root cause: {analysis.root_cause[:120]} (confidence {analysis.confidence:.0%})",
            "user_id": user_id,
        }))
        
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
                user_id=user_id,
            )
            
            if fix_proposals:
                logger.info(f"Generated {len(fix_proposals)} fix proposal(s)")
                asyncio.create_task(manager.broadcast_dashboard({
                    "type": "fix",
                    "message": f"[{user_id}] {len(fix_proposals)} fix proposal(s) generated",
                    "user_id": user_id,
                }))
            else:
                logger.info("No specific fix proposals generated")
        else:
            logger.info("Skipping fix proposal generation due to low confidence")
        
        # 6. Determine recipient email
        registration = user_registrations.get(user_id)
        to_email = config.email.admin_email or ""
        if registration and hasattr(registration, 'notification_email') and registration.notification_email:
            to_email = registration.notification_email
        
        # 7. Send email notification with AST trace and validation results
        #    Also saves HTML report to disk + SQLite index
        email_result = await email_service.send_analysis_email(
            to_email=to_email,
            analysis=analysis,
            proposals=fix_proposals,
            ast_trace=ast_trace,
            validation_result=validation_result,
            user_id=user_id,
        )
        report_id = email_result.get("report_id", "")
        report_url = email_result.get("report_url", "")
        email_sent = email_result.get("email_sent", False)

        if email_sent:
            logger.info(f"Email sent to {to_email}")
        else:
            logger.info(f"Report saved (email {'disabled' if not config.email.enable_notifications else 'skipped'})")
        
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
                "email_sent": email_sent,
                "report_id": report_id,
                "report_url": report_url,
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
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize SQLite report store
    _store = get_report_store()
    logger.info(f"  Report store: {_store.db_path} ({_store.count()} reports)")

    # Load persisted registrations and re-attach repos
    _load_registrations()
    if user_registrations:
        github_service = get_github_service()
        for uid, reg in user_registrations.items():
            try:
                result = await github_service.clone_repository(reg)
                if result:
                    user_repos[uid] = result
                    logger.info(f"  Repo ready: {uid} -> {result.local_path}")
            except Exception as e:
                logger.warning(f"  Repo unavailable for {uid}: {e}")

    # Periodic log-cache flush (every 10 minutes)
    async def _flush_loop():
        while True:
            await asyncio.sleep(600)  # 10 minutes
            manager.periodic_flush_all()
            logger.debug("Periodic log cache flush completed")

    flush_task = asyncio.create_task(_flush_loop())
    
    yield

    flush_task.cancel()
    
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

# Jinja2 templates and auth
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"
_tpl = Jinja2Templates(directory=str(_TEMPLATE_DIR))
_auth = get_auth_manager()


def _get_user(request: Request):
    """Return the authenticated User or None."""
    token = request.cookies.get("session_token")
    if token:
        return _auth.get_session(token)
    return None


# ============================================================================
# Page Routes (HTML dashboard served by FastAPI)
# ============================================================================

@app.get("/login", include_in_schema=False)
async def page_login(request: Request):
    if _get_user(request):
        return RedirectResponse("/")
    return _tpl.TemplateResponse("login.html", {"request": request})


@app.post("/login", include_in_schema=False)
async def page_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = _auth.verify_user(username, password)
    if not user:
        return _tpl.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})
    token = _auth.create_session(user)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return resp


@app.get("/logout", include_in_schema=False)
async def page_logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        _auth.delete_session(token)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_token")
    return resp


@app.get("/", include_in_schema=False)
async def page_dashboard(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    return _tpl.TemplateResponse("dashboard.html", {"request": request, "user": user, "page": "dashboard"})


@app.get("/connections", include_in_schema=False)
async def page_connections(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    return _tpl.TemplateResponse("connections.html", {"request": request, "user": user, "page": "connections"})


@app.get("/logs", include_in_schema=False)
async def page_logs(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    return _tpl.TemplateResponse("logs.html", {"request": request, "user": user, "page": "logs"})


@app.get("/reports", include_in_schema=False)
async def page_reports(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    return _tpl.TemplateResponse("reports.html", {"request": request, "user": user, "page": "reports"})


@app.get("/integration", include_in_schema=False)
async def page_integration(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    scheme = request.url.scheme
    ws_scheme = "wss" if scheme == "https" else "ws"
    server_url = f"{scheme}://{request.url.netloc}"
    ws_url = f"{ws_scheme}://{request.url.netloc}"
    return _tpl.TemplateResponse("integration.html", {
        "request": request, "user": user, "page": "integration",
        "server_url": server_url, "ws_url": ws_url,
    })


@app.get("/visualizer", include_in_schema=False)
async def page_visualizer(request: Request):
    """Serve the React-based AST Visualizer SPA."""
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    # Try static copy first, then original dist
    static_index = _STATIC_DIR / "visualizer" / "index.html"
    react_index = Path(__file__).parent.parent / "Visualizer" / "AiHealingSystem" / "dist" / "index.html"
    for idx in (static_index, react_index):
        if idx.exists():
            return FileResponse(str(idx), media_type="text/html")
    # Fallback to template-based visualizer
    visualizer_url = "http://localhost:5173"
    return _tpl.TemplateResponse("visualizer.html", {
        "request": request, "user": user, "page": "visualizer",
        "visualizer_url": visualizer_url,
    })


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

    # Broadcast connection event to dashboard watchers
    asyncio.create_task(manager.broadcast_dashboard({
        "type": "connection",
        "message": f"Service connected: {user_id}",
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat(),
    }))

    try:
        while True:
            # Receive log data from user's service
            data = await websocket.receive_json()
            
            try:
                # Parse log entry
                log_entry = LogEntry(**data)
                manager.add_log(user_id, log_entry)

                # Broadcast ALL logs to dashboard so the Logs page shows live data
                asyncio.create_task(manager.broadcast_dashboard({
                    "type": "log",
                    "user_id": user_id,
                    "level": log_entry.level,
                    "message": log_entry.message[:300],
                    "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else datetime.utcnow().isoformat(),
                    "source_file": log_entry.source_file or "",
                }))
                
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
        asyncio.create_task(manager.broadcast_dashboard({
            "type": "disconnection",
            "message": f"Service disconnected: {user_id}",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }))
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        manager.disconnect(user_id)
        asyncio.create_task(manager.broadcast_dashboard({
            "type": "disconnection",
            "message": f"Service disconnected: {user_id}",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }))


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for the dashboard UI.
    Receives broadcast events about errors, analyses, fixes, and PRs.
    """
    await manager.add_dashboard(websocket)
    logger.info("Dashboard watcher connected")
    try:
        while True:
            # Keep alive – dashboard only receives, but we read to detect disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.remove_dashboard(websocket)
        logger.info("Dashboard watcher disconnected")
    except Exception:
        manager.remove_dashboard(websocket)


# ============================================================================
# REST API Endpoints - User Registration & Configuration
# ============================================================================

@app.post("/api/v1/register")
async def register_user(registration: UserRegistration, background_tasks: BackgroundTasks):
    """
    Register a new user with their repository access.
    
    User provides:
    - GitHub/GitLab token (read-only access)
    - Repository URL
    - Base branch to monitor
    - Notification email
    
    On registration:
    - Stores registration in memory
    - Creates a viewer account in auth DB
    - Clones the repository in background
    - Returns the WebSocket URL for log streaming
    """
    user_id = registration.user_id
    
    if not registration.repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required. GitHub repository URL must be provided.")

    if user_id in user_registrations:
        raise HTTPException(status_code=409, detail="User already registered")
    
    user_registrations[user_id] = registration
    _save_registrations()  # Persist to disk
    
    # Create a viewer account in auth DB so the user appears in the logs filter
    try:
        _auth.create_user(user_id, user_id, role="viewer")
        logger.info(f"Auth account created for {user_id}")
    except Exception:
        # May already exist
        pass
    
    # Clone the repository in the background
    github_service = get_github_service()

    async def _clone():
        try:
            result = await github_service.clone_repository(registration)
            if result:
                user_repos[user_id] = result
                logger.info(f"Repository cloned for {user_id}: {result.local_path}")
                # Broadcast to dashboard
                await manager.broadcast_dashboard({
                    "type": "connection",
                    "message": f"Repository cloned for {user_id}",
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            else:
                logger.warning(f"Repository clone failed for {user_id} (no token or invalid URL)")
        except Exception as e:
            logger.error(f"Clone failed for {user_id}: {e}")

    background_tasks.add_task(_clone)
    
    ws_url = f"ws://localhost:{config.server.port}/ws/logs/{user_id}"
    
    logger.info(f"User registered: {user_id} - {registration.repo_url}")
    
    return {
        "status": "success",
        "user_id": user_id,
        "message": "Registration successful. Repository clone started. Add the WebSocket client snippet to your service.",
        "websocket_url": ws_url,
        "repo_url": registration.repo_url,
        "base_branch": registration.base_branch,
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
        "registered_at": reg.created_at.isoformat(),
        "connected": user_id in manager.active_connections,
    }


@app.delete("/api/v1/user/{user_id}")
async def unregister_user(user_id: str):
    """Unregister a user and clean up their data."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    del user_registrations[user_id]
    _save_registrations()  # Persist to disk

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
    Trigger a git clone/pull to sync the user's repository.
    """
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")

    registration = user_registrations[user_id]
    github_service = get_github_service()

    async def _sync():
        try:
            repo_info = user_repos.get(user_id)
            if repo_info and repo_info.local_path:
                # Pull existing repo
                success = await github_service.pull_repository(user_id)
                if success:
                    logger.info(f"Repository pulled for {user_id}")
                else:
                    logger.warning(f"Pull failed for {user_id}, trying fresh clone")
                    result = await github_service.clone_repository(registration, force=True)
                    if result:
                        user_repos[user_id] = result
            else:
                # Fresh clone
                result = await github_service.clone_repository(registration)
                if result:
                    user_repos[user_id] = result
                    logger.info(f"Repository cloned for {user_id}: {result.local_path}")
                else:
                    logger.error(f"Clone failed for {user_id}")
        except Exception as e:
            logger.error(f"Sync failed for {user_id}: {e}")

    background_tasks.add_task(_sync)
    return {"status": "queued", "message": "Repository sync started in background"}


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


@app.get("/api/v1/repo/{user_id}/files")
async def list_repo_files(user_id: str, ext: Optional[str] = Query(None)):
    """List source files in a user's repo, optionally filtered by extension."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    repo_info = user_repos.get(user_id)
    if not repo_info:
        raise HTTPException(status_code=404, detail="Repository not cloned yet")
    local = Path(repo_info.local_path)
    if not local.exists():
        raise HTTPException(status_code=404, detail="Repository path not found on disk")
    # Discover repo subdirectory (repos/{user_id}/{owner}_{repo_name}/...)
    sub = local
    children = [p for p in local.iterdir() if p.is_dir() and not p.name.startswith('.')]
    if len(children) == 1 and any(children[0].iterdir()):
        sub = children[0]
    from services.ast_service import EXTENSION_TO_LANGUAGE
    exts = {f".{e}" for e in (ext.split(",") if ext else [])}
    result = []
    for f in sorted(sub.rglob("*")):
        if not f.is_file():
            continue
        if any(part.startswith('.') or part in ('node_modules', '__pycache__', 'dist', 'build', '.git')
               for part in f.parts):
            continue
        rel = str(f.relative_to(sub)).replace("\\", "/")
        if ext and f.suffix not in exts:
            continue
        lang = EXTENSION_TO_LANGUAGE.get(f.suffix)
        if lang:
            result.append({"path": rel, "language": lang, "size": f.stat().st_size})
    return {"user_id": user_id, "repo_root": str(sub), "files": result[:500]}


@app.post("/api/v1/repo/{user_id}/ast")
async def get_repo_file_ast(user_id: str, request: Request):
    """Parse a file from a user's repo and return AST for the interactive visualizer."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found. Register the service first.")
    repo_info = user_repos.get(user_id)
    if not repo_info:
        raise HTTPException(status_code=404, detail=f"Repository for '{user_id}' not cloned yet")
    local = Path(repo_info.local_path)
    if not local.exists():
        raise HTTPException(status_code=404, detail="Repository path not found on disk")
    # Discover repo subdirectory
    children = [p for p in local.iterdir() if p.is_dir() and not p.name.startswith('.')]
    if len(children) == 1 and any(children[0].iterdir()):
        local = children[0]
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON with {\"file_path\": \"...\"}")
    file_path = body.get("file_path", "") if isinstance(body, dict) else ""
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required in request body")
    target = (local / file_path).resolve()
    # Safety check
    if not str(target).startswith(str(local.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    from services.ast_visualizer import get_ast_visualizer
    viz = get_ast_visualizer()
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""
    result = viz.parse_single_file(str(target), content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    result["source"] = content
    result["file_path"] = file_path
    return result


@app.get("/api/v1/repos/registered")
async def list_registered_repos():
    """List all registered users and their repos for the dashboard."""
    repos = []
    for uid, reg in user_registrations.items():
        repo_info = user_repos.get(uid)
        repos.append({
            "user_id": uid,
            "repo_url": reg.repo_url,
            "email": reg.email,
            "status": "ready" if repo_info else "not_cloned",
            "local_path": str(repo_info.local_path) if repo_info else None,
            "current_branch": repo_info.current_branch if repo_info else None,
            "latest_commit": repo_info.latest_commit if repo_info else None,
        })
    return {"repos": repos}


# ============================================================================
# REST API Endpoints - Error Analysis
# ============================================================================

# ── Server log file endpoint (reads logs/app.log) — MUST be before {user_id} routes ──

import re as _re

_ANSI_ESCAPE = _re.compile(r"\x1b\[[0-9;]*m")

_SERVER_LOG_RE = _re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"  # timestamp
    r" \| (\S+)"                                  # logger name
    r" \| (\w+)"                                  # level
    r" \| (.*)$"                                   # message
)
_APP_LOG_PATH = Path(__file__).parent.parent / "logs" / "app.log"

@app.get("/api/v1/logs/server")
async def get_server_logs(limit: int = 200, level: Optional[str] = None):
    """Read the last N lines from logs/app.log and return parsed entries."""
    if not _APP_LOG_PATH.exists():
        return {"logs": [], "total": 0}
    try:
        raw = _APP_LOG_PATH.read_text(encoding="utf-8", errors="replace")
        lines = raw.strip().splitlines()
    except Exception:
        return {"logs": [], "total": 0}

    entries = []
    for line in lines:
        clean = _ANSI_ESCAPE.sub("", line)
        m = _SERVER_LOG_RE.match(clean)
        if m:
            ts, name, lvl, msg = m.groups()
            if level and lvl.upper() != level.upper():
                continue
            entries.append({
                "timestamp": ts,
                "logger": name,
                "level": lvl,
                "message": msg.strip(),
                "user_id": "server",
            })
        elif entries:
            # Continuation line (traceback, etc.) — append to last entry
            entries[-1]["message"] += "\n" + line

    # Return last N entries
    total = len(entries)
    entries = entries[-limit:]
    return {"logs": entries, "total": total}


@app.get("/api/v1/logs")
async def get_all_logs(limit: int = 200):
    """Get recent logs from ALL connected users."""
    all_logs = []
    for uid, logs in manager.log_buffers.items():
        for log in logs[-limit:]:
            d = log.model_dump(mode="json")
            d["user_id"] = uid
            all_logs.append(d)
    all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"logs": all_logs[:limit]}


@app.get("/api/v1/logs/{user_id}")
async def get_logs(user_id: str, limit: int = 100):
    """Get recent logs for a user."""
    logs = manager.log_buffers.get(user_id, [])
    return {
        "user_id": user_id,
        "total_logs": len(logs),
        "has_errors": manager._has_errors.get(user_id, False),
        "logs": [log.model_dump() for log in logs[-limit:]],
    }


@app.delete("/api/v1/logs/{user_id}")
async def clear_user_logs(user_id: str):
    """Manually clear cached logs for a user (including error logs)."""
    manager.flush_logs(user_id, force=True)
    return {"status": "cleared", "user_id": user_id}


@app.post("/api/v1/analyze/{user_id}")
async def trigger_analysis(user_id: str, background_tasks: BackgroundTasks):
    """Manually trigger error analysis for a user."""
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    logs = manager.log_buffers.get(user_id, [])
    errors = [log for log in logs if log.level.upper() in ["ERROR", "FATAL", "CRITICAL"]]
    
    if not errors:
        return {"status": "no_errors", "message": "No errors found in recent logs"}
    
    # Queue analysis for each error in background
    for error_log in errors[-5:]:  # Analyse last 5 errors
        background_tasks.add_task(analyze_error, user_id, error_log)

    return {
        "status": "queued",
        "message": f"Analysis started for {min(len(errors), 5)} error(s)",
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

    registration = user_registrations[user_id]
    github_service = get_github_service()
    ai_analyzer = get_ai_analyzer()
    email_service = get_email_service()

    async def _review():
        try:
            # Fetch the PR diff from GitHub
            pr_diff = await github_service.get_pr_diff(registration, pr_info.pr_number)
            if not pr_diff:
                logger.error(f"Failed to fetch PR diff for #{pr_info.pr_number}")
                return

            # Run AI code review
            review_result = await ai_analyzer.review_pull_request(pr_diff, pr_info, user_id=user_id)
            logger.info(f"PR #{pr_info.pr_number} reviewed: score={review_result.overall_score}")

            # Send review email
            cfg = get_config()
            to_email = registration.notification_email or registration.email or cfg.email.admin_email
            if cfg.email.enable_notifications and to_email:
                await email_service.send_code_review_email(
                    to_email=to_email,
                    review=review_result,
                )
                logger.info(f"Review email sent to {to_email}")

            # Notify via WebSocket
            await manager.send_message(user_id, WebSocketMessage(
                type="review_complete",
                user_id=user_id,
                payload={
                    "pr_number": pr_info.pr_number,
                    "score": review_result.overall_score,
                    "approved": review_result.approved,
                    "comments_count": len(review_result.comments),
                    "summary": review_result.summary[:200],
                },
            ))
        except Exception as e:
            logger.error(f"PR review failed: {e}")
            import traceback
            traceback.print_exc()

    background_tasks.add_task(_review)
    return {
        "status": "queued",
        "message": f"Code review started for PR #{pr_info.pr_number}",
        "pr_number": pr_info.pr_number,
    }


def _normalize_repo_url(url: str) -> str:
    """Normalize a GitHub repo URL for comparison.
    Strips protocol, trailing slashes, and .git suffix.
    Returns lowercase 'github.com/owner/repo'."""
    url = url.strip().lower()
    for prefix in ("https://", "http://", "git://", "ssh://git@", "git@"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    url = url.replace(":", "/", 1) if ":" in url.split("/", 1)[0] else url
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _find_user_by_repo_url(repo_url: str) -> Optional[str]:
    """Find a registered user_id whose repo_url matches the given URL.
    Prefers users that have a non-empty repo_token so diffs can be fetched."""
    needle = _normalize_repo_url(repo_url)
    matches: list[str] = []
    for uid, reg in user_registrations.items():
        if _normalize_repo_url(reg.repo_url) == needle:
            matches.append(uid)
    if not matches:
        return None
    # Prefer a user that actually has a token
    for uid in matches:
        reg = user_registrations[uid]
        if reg.repo_token or reg.access_token:
            return uid
    return matches[0]  # fallback to first match


@app.post("/api/v1/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """GitHub webhook endpoint for PR and push events."""
    # Direct stderr print — guaranteed to appear even if logging is broken
    import sys as _sys
    print(f"[WEBHOOK HIT] {datetime.utcnow().isoformat()} - /api/v1/webhook/github", file=_sys.stderr, flush=True)

    body = await request.body()

    # ── Verify HMAC signature if webhook secret is configured ──
    cfg = get_config()
    webhook_secret = cfg.github.pr_webhook_secret
    if webhook_secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        if not sig_header:
            logger.warning("Webhook rejected: missing X-Hub-Signature-256 header")
            raise HTTPException(status_code=401, detail="Missing signature header")
        expected = "sha256=" + hmac.new(
            webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            logger.warning("Webhook rejected: invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    event_type = request.headers.get("X-GitHub-Event", "")
    action = payload.get("action", "")
    repo_name_from_payload = payload.get("repository", {}).get("full_name", "")

    print(f"[WEBHOOK] event={event_type}, action={action}, repo={repo_name_from_payload}", file=_sys.stderr, flush=True)
    logger.info(f"Webhook received: event={event_type}, action={action}, repo={repo_name_from_payload}")

    # ── Handle Push events (commit review) ──
    if event_type == "push":
        repo_url = payload.get("repository", {}).get("html_url", "")
        commits = payload.get("commits", [])
        ref = payload.get("ref", "")  # e.g. refs/heads/main

        # Find user by repo URL (exact match after normalisation)
        target_user = _find_user_by_repo_url(repo_url)
        if not target_user:
            logger.warning(f"Webhook push: no registered user matches repo {repo_url}")

        if target_user and commits:
            registration = user_registrations[target_user]
            github_service = get_github_service()
            ai_analyzer = get_ai_analyzer()
            email_service = get_email_service()
            logger.info(f"Webhook push: matched user '{target_user}', {len(commits)} commit(s), ref={ref}")

            async def _review_commit():
                try:
                    # 1. Pull latest code
                    repo_info = user_repos.get(target_user)
                    if repo_info and repo_info.local_path:
                        await github_service.pull_repository(target_user)
                        logger.info(f"Webhook: pulled latest for {target_user}")
                    else:
                        result = await github_service.clone_repository(registration)
                        if result:
                            user_repos[target_user] = result
                            logger.info(f"Webhook: cloned repo for {target_user}")

                    # 2. Get diff for the latest commit
                    latest_commit = commits[-1]  # Most recent commit in the push
                    commit_sha = latest_commit.get("id", "")
                    commit_msg = latest_commit.get("message", "")
                    logger.info(f"Webhook: reviewing commit {commit_sha[:8]} - {commit_msg[:80]}")

                    # Parse owner/repo from URL
                    owner, repo_name = "", ""
                    parts = repo_url.rstrip("/").split("/")
                    if len(parts) >= 2:
                        owner, repo_name = parts[-2], parts[-1].replace(".git", "")

                    token = (registration.access_token or registration.repo_token
                             or github_service.default_token or "")

                    # Reject obvious placeholder tokens
                    _placeholders = {"your_github_token_here", "your_token_here", "changeme", ""}
                    if not token or token.strip().lower() in _placeholders:
                        logger.error(f"Webhook: no valid token for {target_user} — cannot fetch commit diff. "
                                     f"Set repo_token on registration or GITHUB_TOKEN in .env")
                        return

                    logger.info(f"Webhook: fetching diff from github.com/{owner}/{repo_name}/commit/{commit_sha[:8]}")
                    commit_diff = None
                    if owner and repo_name:
                        commit_diff = await github_service.get_commit_diff(
                            owner, repo_name, commit_sha, token
                        )

                    if not commit_diff:
                        logger.warning(f"Webhook: could not fetch commit diff for {commit_sha[:8]}")
                        return

                    # 3. Build a PRInfo-like object for the AI review
                    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
                    pr_info = PRInfo(
                        pr_id=commit_sha[:8],
                        pr_number=0,
                        title=f"Commit: {commit_msg[:80]}",
                        description=commit_msg,
                        source_branch=branch,
                        target_branch=branch,
                        author=latest_commit.get("author", {}).get("name", ""),
                        repo_url=repo_url,
                    )

                    # 4. Run AI code review on the commit
                    logger.info(f"Webhook: sending commit diff to AI analyzer ({len(commit_diff.get('files', []))} files changed)...")
                    review_result = await ai_analyzer.review_pull_request(commit_diff, pr_info, user_id=target_user)
                    logger.info(f"Webhook: commit {commit_sha[:8]} reviewed, score={review_result.overall_score}, "
                                f"comments={len(review_result.comments)}, assessment={review_result.overall_assessment}")

                    # 5. Save review report to report store
                    report_html = email_service._build_review_email(review_result)
                    store = get_report_store()
                    import uuid as _uuid
                    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    rpt_filename = f"review_{ts}_{commit_sha[:8]}_{_uuid.uuid4().hex[:6]}.html"
                    rpt_path = REPORTS_DIR / rpt_filename
                    rpt_path.write_text(report_html, encoding="utf-8")
                    report_id = store.insert(
                        file_path=str(rpt_path),
                        file_name=rpt_filename,
                        report_type="review",
                        user_id=target_user,
                        error_type=f"Code Review: {commit_msg[:60]}",
                        severity=review_result.overall_assessment or "comment",
                        confidence=review_result.overall_score / 10.0 if review_result.overall_score else 0.0,
                        root_cause=review_result.summary[:500] if review_result.summary else "",
                        source_file=f"{owner}/{repo_name}",
                        line_number=0,
                        proposals_count=len(review_result.comments),
                    )
                    logger.info(f"Webhook: review report saved -> {rpt_filename} (id={report_id})")

                    # 6. Send review email
                    cfg = get_config()
                    to_email = registration.notification_email or registration.email or cfg.email.admin_email
                    if cfg.email.enable_notifications and to_email:
                        await email_service.send_code_review_email(
                            to_email=to_email,
                            review=review_result,
                        )
                        logger.info(f"Webhook: commit review email sent to {to_email}")

                    # 7. Notify via WebSocket
                    await manager.broadcast_dashboard({
                        "type": "review_complete",
                        "message": f"[{target_user}] Commit review: {commit_msg[:80]} (score: {review_result.overall_score})",
                        "user_id": target_user,
                        "report_id": report_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                except Exception as e:
                    logger.error(f"Webhook commit review failed: {e}")
                    import traceback
                    traceback.print_exc()

            background_tasks.add_task(_review_commit)
            logger.info(f"Webhook: push review queued for {len(commits)} commit(s) on {target_user}")

        return {"status": "received", "event": "push", "commits": len(commits),
                "matched_user": target_user or None}

    # ── Handle PR events ──
    if event_type == "pull_request" and action in ("opened", "synchronize", "reopened"):
        pr_data = payload.get("pull_request", {})
        repo_url = payload.get("repository", {}).get("html_url", "")

        # Find user by repo URL (exact match after normalisation)
        target_user = _find_user_by_repo_url(repo_url)
        if not target_user:
            logger.warning(f"Webhook PR: no registered user matches repo {repo_url}")

        if target_user and pr_data:
            pr_info = PRInfo(
                pr_id=str(pr_data.get("id", "")),
                pr_number=pr_data.get("number", 0),
                title=pr_data.get("title", ""),
                description=pr_data.get("body", "") or "",
                source_branch=pr_data.get("head", {}).get("ref", ""),
                target_branch=pr_data.get("base", {}).get("ref", ""),
                author=pr_data.get("user", {}).get("login", ""),
                repo_url=repo_url,
            )
            # Trigger auto-review
            background_tasks.add_task(
                review_pull_request, target_user, pr_info, background_tasks
            )
            logger.info(f"Webhook: auto-review queued for PR #{pr_info.pr_number} ({target_user})")

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
        "active_connections": len(manager.active_connections),
        "registered_users": len(user_registrations),
        "repositories_synced": len(user_repos),
        "ai_provider": config.ai.provider,
    }


# ============================================================================
# REST API Endpoints - AST Visualization (replaces Node.js Visualizer/server.js)
# Endpoints match the format expected by the React frontend (AiHealingSystem)
# ============================================================================

@app.post("/upload/zip")
async def upload_zip_project(file: UploadFile = File(...)):
    """Upload a ZIP file and get complete project visualization with cross-file references."""
    from services.ast_visualizer import get_ast_visualizer
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        buffer = await file.read()
        visualizer = get_ast_visualizer()
        project_name = file.filename.replace(".zip", "")
        result = visualizer.parse_zip_project(buffer, project_name)
        
        if "error" in result and result["error"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"ZIP parsed: {result['summary']['totalFiles']} files, "
                    f"{result['summary']['totalReferences']} refs, "
                    f"languages: {result['summary']['languages']}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/file")
async def upload_single_file(file: UploadFile = File(...)):
    """Upload a single file for AST visualization."""
    from services.ast_visualizer import get_ast_visualizer
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        content = (await file.read()).decode("utf-8", errors="replace")
        visualizer = get_ast_visualizer()
        result = visualizer.parse_single_file(file.filename, content)
        
        if result.get("error"):
            logger.warning(f"File parse warning: {result['error']}")
        
        return result
    except Exception as e:
        logger.error(f"File processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/parse/code")
async def parse_code_visualizer(body: dict):
    """Parse a code snippet for AST visualization (matches Node.js format)."""
    from services.ast_visualizer import get_ast_visualizer
    
    code = body.get("code", "")
    error_line = body.get("errorLine")
    filename = body.get("filename", "code.js")
    
    if not code:
        raise HTTPException(status_code=400, detail="Code is required")
    
    try:
        visualizer = get_ast_visualizer()
        result = visualizer.parse_code_snippet(code, filename, error_line)
        
        if "error" in result and result["error"] and "tree" not in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/languages")
async def get_languages_visualizer():
    """Get supported languages with extensions (matches Node.js format)."""
    from services.ast_visualizer import get_languages_info
    return get_languages_info()


# Upload a repo directory for visualization (bonus - for registered repos)
@app.post("/api/v1/visualize/repo")
async def visualize_repo(body: dict):
    """Parse all files in a user's registered repo for project visualization."""
    from services.ast_visualizer import get_ast_visualizer
    
    user_id = body.get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    repo_info = user_repos.get(user_id)
    if not repo_info or not repo_info.local_path:
        raise HTTPException(status_code=404, detail="Repository not found for user")
    
    visualizer = get_ast_visualizer()
    result = visualizer.parse_repo_directory(
        str(repo_info.local_path),
        project_name=user_id,
    )
    
    if "error" in result and result["error"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


# Keep the original API-prefixed endpoints for backward compatibility
@app.post("/api/v1/parse/code")
async def parse_code_snippet(body: dict):
    """Parse a code snippet and return its AST."""
    code = body.get("code", "")
    language = body.get("language", "javascript")
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    ast_service = get_ast_service()
    root = ast_service.parse_code(code, language)
    if not root:
        raise HTTPException(status_code=422, detail="Failed to parse code")

    from services.ast_service import ASTService
    return {
        "language": language,
        "ast": ASTService.ast_to_dict(root),
    }


@app.post("/api/v1/parse/file")
async def parse_file_endpoint(body: dict):
    """Parse a file from a user's repo and return its AST."""
    user_id = body.get("user_id", "")
    file_path = body.get("file_path", "")
    if not user_id or not file_path:
        raise HTTPException(status_code=400, detail="user_id and file_path required")

    repo_info = user_repos.get(user_id)
    if not repo_info or not repo_info.local_path:
        raise HTTPException(status_code=404, detail="Repository not found for user")

    import os
    full_path = os.path.join(repo_info.local_path, file_path)
    ast_service = get_ast_service()
    root = ast_service.parse_file(full_path)
    if not root:
        raise HTTPException(status_code=422, detail="Failed to parse file")

    from services.ast_service import ASTService
    return {
        "file": file_path,
        "language": ast_service.detect_language(file_path),
        "ast": ASTService.ast_to_dict(root),
    }


@app.get("/api/v1/languages")
async def get_supported_languages():
    """Get list of supported languages for AST parsing."""
    from services.ast_service import EXTENSION_TO_LANGUAGE, LANGUAGE_DISPLAY
    ast_service = get_ast_service()
    return {
        "languages": LANGUAGE_DISPLAY,
        "extensions": EXTENSION_TO_LANGUAGE,
        "tree_sitter_available": bool(ast_service._parsers),
        "loaded_parsers": list(ast_service._parsers.keys()),
    }


@app.get("/api/v1/users")
async def list_dashboard_users():
    """List all dashboard users (auth DB)."""
    users = _auth.list_users()
    return {
        "users": [
            {"id": u.id, "username": u.username, "role": u.role, "created_at": u.created_at}
            for u in users
        ]
    }


@app.get("/api/v1/connections")
async def get_connections():
    """Get all active WebSocket connections."""
    return {
        "connections": [
            {
                "user_id": conn.user_id,
                "connected_at": conn.connected_at.isoformat(),
                "last_heartbeat": conn.last_heartbeat.isoformat(),
                "logs_received": conn.logs_received,
                "errors_detected": conn.errors_detected,
            }
            for conn in manager.active_connections.values()
        ]
    }


@app.get("/api/v1/dashboard/summary")
async def dashboard_summary():
    """Get a summary of the system state for the dashboard."""
    total_logs = sum(len(logs) for logs in manager.log_buffers.values())
    total_errors = sum(
        sum(1 for log in logs if log.level.upper() in ("ERROR", "FATAL", "CRITICAL"))
        for logs in manager.log_buffers.values()
    )
    store = get_report_store()
    report_stats = store.stats()
    return {
        "active_connections": len(manager.active_connections),
        "registered_users": len(user_registrations),
        "repositories_synced": len(user_repos),
        "total_logs": total_logs,
        "total_errors": total_errors,
        "total_reports": report_stats.get("total", 0),
        "ai_provider": config.ai.provider,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# REST API Endpoints - Reports (SQLite-backed HTML report store)
# ============================================================================

@app.get("/api/v1/reports")
async def list_reports(
    user_id: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List reports with optional filtering."""
    store = get_report_store()
    reports = store.list_reports(
        user_id=user_id,
        report_type=report_type,
        error_type=error_type,
        limit=limit,
        offset=offset,
    )
    total = store.count(user_id=user_id, report_type=report_type)
    return {
        "reports": [
            {
                "report_id": r.report_id,
                "user_id": r.user_id,
                "error_type": r.error_type,
                "severity": r.severity,
                "confidence": r.confidence,
                "root_cause": r.root_cause,
                "source_file": r.source_file,
                "line_number": r.line_number,
                "report_type": r.report_type,
                "proposals_count": r.proposals_count,
                "created_at": r.created_at,
                "view_url": f"/api/v1/reports/{r.report_id}/view",
            }
            for r in reports
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/reports/stats")
async def report_stats():
    """Get report statistics."""
    store = get_report_store()
    return store.stats()


@app.get("/api/v1/reports/{report_id}")
async def get_report_meta(report_id: str):
    """Get report metadata (JSON)."""
    store = get_report_store()
    rec = store.get(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id": rec.report_id,
        "user_id": rec.user_id,
        "error_type": rec.error_type,
        "severity": rec.severity,
        "confidence": rec.confidence,
        "root_cause": rec.root_cause,
        "source_file": rec.source_file,
        "line_number": rec.line_number,
        "file_name": rec.file_name,
        "report_type": rec.report_type,
        "proposals_count": rec.proposals_count,
        "created_at": rec.created_at,
        "view_url": f"/api/v1/reports/{rec.report_id}/view",
    }


@app.get("/api/v1/reports/{report_id}/view")
async def view_report(report_id: str):
    """Serve the full HTML report for browser viewing."""
    store = get_report_store()
    rec = store.get(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")

    file_path = Path(rec.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="Report file has been deleted from disk")

    html = file_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.delete("/api/v1/reports/{report_id}")
async def delete_report(report_id: str):
    """Delete a report (metadata + file)."""
    store = get_report_store()
    rec = store.get(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")

    store.delete_with_file(report_id)
    return {"status": "deleted", "report_id": report_id}


# ============================================================================
# Static Files (must come after all route definitions)
# ============================================================================

# React Visualizer built assets
_REACT_DIST = Path(__file__).parent.parent / "Visualizer" / "AiHealingSystem" / "dist"
_REACT_ASSETS = _REACT_DIST / "assets"
_STATIC_VIZ_ASSETS = _STATIC_DIR / "visualizer" / "assets"
# Prefer static copy, fallback to original dist
_viz_assets = _STATIC_VIZ_ASSETS if _STATIC_VIZ_ASSETS.exists() else _REACT_ASSETS
if _viz_assets.exists():
    app.mount("/assets", StaticFiles(directory=str(_viz_assets)), name="react_assets")

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


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
        access_log=True,
        use_colors=True,
    )


if __name__ == "__main__":
    main()
