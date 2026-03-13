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
    UserRegistration, RepositoryInfo, PRInfo,
)

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
        
        self.websockets[user_id] = websocket
        self.active_connections[user_id] = WebSocketConnection(
            user_id=user_id,
            connected_at=datetime.utcnow(),
            is_active=True,
        )
        self.log_buffers[user_id] = []
        
        logger.info(f"✓ WebSocket connected: user={user_id}")
        
    def disconnect(self, user_id: str):
        """Handle WebSocket disconnection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].is_active = False
        if user_id in self.websockets:
            del self.websockets[user_id]
            
        logger.info(f"✗ WebSocket disconnected: user={user_id}")
        
    async def send_message(self, user_id: str, message: WebSocketMessage):
        """Send a message to a specific user's service."""
        if user_id in self.websockets:
            await self.websockets[user_id].send_json(message.model_dump())
            
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
    config.repos_base_path = config.github.repos_base_path
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
                    # TODO: Implement analyze_error function
                    # asyncio.create_task(analyze_error(user_id, log_entry))
                    
                    # Acknowledge receipt
                    await manager.send_message(user_id, WebSocketMessage(
                        type="error_received",
                        payload={"message": "Error logged and queued for analysis"},
                    ))
                    
            except ValidationError as e:
                logger.warning(f"Invalid log format from {user_id}: {e}")
                await manager.send_message(user_id, WebSocketMessage(
                    type="error",
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
    
    This is called:
    - After registration to clone the repo
    - Periodically by a background task
    - Manually by the user
    """
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Implement git clone/pull
    # background_tasks.add_task(sync_repo_task, user_id)
    
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
    """
    Manually trigger error analysis for a user.
    
    This analyzes recent error logs and generates fix proposals.
    """
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Find recent errors
    logs = manager.log_buffers.get(user_id, [])
    errors = [log for log in logs if log.level.upper() in ["ERROR", "FATAL", "CRITICAL"]]
    
    if not errors:
        return {"status": "no_errors", "message": "No errors found in recent logs"}
    
    # TODO: Implement analyze_errors_task
    # background_tasks.add_task(analyze_errors_task, user_id, errors)
    
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
    """
    Trigger a code review for a pull request.
    
    Analyzes the PR diff using the three-dot diff method and provides
    AI-powered code review comments.
    """
    if user_id not in user_registrations:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Implement code_review_task
    # background_tasks.add_task(code_review_task, user_id, pr_info)
    
    return {
        "status": "queued",
        "message": f"Code review queued for PR #{pr_info.pr_number}",
        "pr_number": pr_info.pr_number,
    }


# ============================================================================
# REST API Endpoints - Webhooks
# ============================================================================

@app.post("/api/v1/webhook/github")
async def github_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    GitHub webhook endpoint for PR events.
    
    Automatically triggers code review when a PR is opened or updated.
    """
    event_type = payload.get("action", "")
    
    if event_type in ["opened", "synchronize", "reopened"]:
        # TODO: Extract PR info and trigger review
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
        reload_dirs=["src"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
