"""
Data Models for Self-Healing System v2.0
WebSocket-based log streaming, AST analysis, and code review system.

Uses Pydantic for strict validation.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==========================================
# Enums
# ==========================================

class LogLevel(str, Enum):
    """Log level enumeration"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorSeverity(str, Enum):
    """Error severity classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnalysisStatus(str, Enum):
    """Status of analysis"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReplicationResult(str, Enum):
    """Result of API replication"""
    SAME_ERROR = "same_error"
    DIFFERENT_ERROR = "different_error"
    NO_ERROR = "no_error"
    TIMEOUT = "timeout"


# ==========================================
# User & Repository Models
# ==========================================

class UserRegistration(BaseModel):
    """User registration data"""
    user_id: str
    email: str = ""
    repo_url: str = ""
    repo_token: str = ""  # Read-only access token
    access_token: str = ""  # Alias for repo_token
    base_branch: str = "main"
    notification_email: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def model_post_init(self, __context):
        # Sync access_token and repo_token
        if self.repo_token and not self.access_token:
            self.access_token = self.repo_token
        elif self.access_token and not self.repo_token:
            self.repo_token = self.access_token


class RepositoryInfo(BaseModel):
    """Repository information"""
    repo_url: str = ""
    base_branch: str = "main"
    local_path: str = ""
    user_id: str = ""
    current_branch: str = ""
    latest_commit: str = ""
    last_pulled: Optional[datetime] = None
    file_count: int = 0
    languages: List[str] = Field(default_factory=list)


# ==========================================
# Log & Error Models
# ==========================================

class LogEntry(BaseModel):
    """A single log entry from user's service"""
    timestamp: datetime = Field(default_factory=datetime.now)
    level: LogLevel = LogLevel.INFO
    message: str = ""
    source: Optional[str] = None  # Service name from JS client
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    api_endpoint: Optional[str] = None
    http_method: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None  # Additional context from client
    response_status: Optional[int] = None
    is_autocure_try: bool = False  # Flag for our replication calls
    raw_line: str = ""
    user_id: Optional[str] = None


class DetectedError(BaseModel):
    """Error detected from logs"""
    model_config = {"extra": "ignore"}  # Ignore extra fields from log_analyzer
    
    error_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    error_type: str = "UnknownError"
    error_category: str = "runtime"  # e.g., "runtime", "syntax", "type", "reference"
    message: str = ""
    stack_trace: Optional[str] = ""
    source_file: Optional[str] = "unknown"
    line_number: Optional[int] = 0
    function_name: Optional[str] = None
    language: str = "unknown"  # e.g., "javascript", "python", "java"
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    api_endpoint: Optional[str] = None
    http_method: Optional[str] = None
    original_payload: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None  # Alias for original_payload
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str = ""


# ==========================================
# AST Models
# ==========================================

class ASTNode(BaseModel):
    """Represents a node in the Abstract Syntax Tree"""
    node_id: str
    node_type: str  # function, class, variable, import, etc.
    name: str
    file_path: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0
    code_snippet: str = ""
    children: List["ASTNode"] = Field(default_factory=list)
    parent_id: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ASTContext(BaseModel):
    """Context around an error node in AST"""
    error_node: Optional[ASTNode] = None
    parent_nodes: List[ASTNode] = Field(default_factory=list)
    child_nodes: List[ASTNode] = Field(default_factory=list)
    sibling_nodes: List[ASTNode] = Field(default_factory=list)
    dependencies: List[ASTNode] = Field(default_factory=list)
    file_imports: List[str] = Field(default_factory=list)
    related_files: List[str] = Field(default_factory=list)


class ASTVisualization(BaseModel):
    """Data for interactive AST visualization in emails"""
    svg_content: str = ""
    html_content: str = ""
    nodes_data: List[Dict[str, Any]] = Field(default_factory=list)
    tree_depth: int = 0
    total_nodes: int = 0


# ==========================================
# API Replication Models
# ==========================================

class APIReplicationRequest(BaseModel):
    """Request for replicating API call"""
    model_config = {"extra": "ignore"}

    url: str = ""
    endpoint: str = ""
    method: str = "GET"
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    original_payload: Dict[str, Any] = Field(default_factory=dict)
    modified_payload: Dict[str, Any] = Field(default_factory=dict)
    variation_type: str = "original"
    autocure_try: bool = True


class APIReplicationResult(BaseModel):
    """Result of an API replication attempt"""
    model_config = {"extra": "ignore"}

    request: APIReplicationRequest
    success: bool = False
    status_code: int = 0
    response_body: str = ""
    error_reproduced: bool = False
    error_message: Optional[str] = None
    response_time_ms: float = 0.0
    result: Optional[ReplicationResult] = None
    response_status: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorReplicationSummary(BaseModel):
    """Summary of all replication attempts for an error"""
    model_config = {"extra": "ignore"}

    error_id: str = ""
    error: Optional[Any] = None  # The DetectedError being replicated
    results: List[APIReplicationResult] = Field(default_factory=list)
    is_reproducible: bool = False
    reproduction_rate: float = 0.0
    error_patterns: List[str] = Field(default_factory=list)
    total_attempts: int = 0
    same_error_count: int = 0
    different_error_count: int = 0
    no_error_count: int = 0
    timeout_count: int = 0
    conclusion: str = ""


# ==========================================
# AI Analysis Models
# ==========================================

class RootCauseAnalysis(BaseModel):
    """AI-generated root cause analysis"""
    model_config = {"extra": "ignore"}
    
    error: Optional[Any] = None  # The DetectedError being analyzed
    root_cause: str = "Unable to determine root cause"
    error_category: str = "unknown"
    severity: str = "medium"
    affected_components: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    additional_context: str = ""
    analyzed_at: datetime = Field(default_factory=datetime.now)
    
    # Legacy fields for backward compatibility
    error_id: str = ""
    detailed_explanation: str = ""
    affected_code_paths: List[str] = Field(default_factory=list)
    suggested_fixes: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = 0.0
    references: List[str] = Field(default_factory=list)


class EdgeTestCase(BaseModel):
    """An edge test case that demonstrates the original bug."""
    test_name: str = ""
    description: str = ""
    test_code: str = ""
    expected_behavior: str = ""
    original_would_fail: bool = True  # Original code fails this test
    fix_would_pass: bool = True       # Proposed fix passes this test


class FixProposal(BaseModel):
    """A proposed fix (not applied, just suggested)"""
    model_config = {"extra": "ignore"}
    
    proposal_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    target_file: str = "unknown"
    line_number: int = 0
    original_code: str = ""
    suggested_code: str = ""
    explanation: str = "No specific fix available"
    risk_level: str = "medium"  # "low", "medium", "high"
    confidence: float = 0.0
    side_effects: List[str] = Field(default_factory=list)
    test_cases: List[EdgeTestCase] = Field(default_factory=list)  # Edge tests for this fix


# ==========================================
# Code Review Models
# ==========================================

class PRInfo(BaseModel):
    """Pull Request information"""
    pr_id: str
    pr_number: int
    title: str
    description: str = ""
    source_branch: str
    target_branch: str
    author: str
    created_at: datetime = Field(default_factory=datetime.now)
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    repo_url: str = ""


class CodeReviewComment(BaseModel):
    """A code review comment"""
    file_path: str
    line_number: int = 0
    comment_type: str = "suggestion"  # "suggestion", "issue", "question", "praise"
    severity: str = "info"  # "info", "warning", "error"
    message: str
    suggested_fix: Optional[str] = None
    code_snippet: str = ""  # Relevant original code snippet for context


class CodeReviewResult(BaseModel):
    """Complete code review result"""
    pr_info: PRInfo
    overall_score: float = 0.0  # 0-100
    overall_assessment: str = "comment"  # "approve", "request_changes", "comment"
    summary: str = ""
    comments: List[CodeReviewComment] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    issues_count: Dict[str, int] = Field(default_factory=dict)
    approved: bool = False
    ast_insights: str = ""  # AST-based analysis findings
    reviewed_at: datetime = Field(default_factory=datetime.now)


# ==========================================
# Email & Notification Models
# ==========================================

class AnalysisEmail(BaseModel):
    """Email with complete analysis"""
    recipient: str
    subject: str
    error_summary: str
    root_cause_analysis: Optional[RootCauseAnalysis] = None
    replication_summary: Optional[ErrorReplicationSummary] = None
    ast_visualization: Optional[ASTVisualization] = None
    fix_proposals: List[FixProposal] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class CodeReviewEmail(BaseModel):
    """Email with code review results"""
    recipient: str
    subject: str
    pr_info: PRInfo
    review_result: CodeReviewResult
    timestamp: datetime = Field(default_factory=datetime.now)


# ==========================================
# WebSocket Models
# ==========================================

class WebSocketMessage(BaseModel):
    """Message format for WebSocket communication"""
    type: str = "log"  # "log", "error", "heartbeat", "config"
    user_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class WebSocketConnection(BaseModel):
    """Active WebSocket connection info"""
    connection_id: str
    user_id: str
    connected_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    logs_received: int = 0
    errors_detected: int = 0


# Allow self-referencing for ASTNode
ASTNode.model_rebuild()
