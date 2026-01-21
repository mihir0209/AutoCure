# Self-Healing Software System v2.0 - Architecture

## System Overview

The Self-Healing Software System v2.0 is an AI-powered **error detection and fix proposal** platform. It receives real-time logs via WebSocket from user production apps, detects errors, traces them through AST analysis, and **proposes fixes** (without applying them). The system also reviews PRs for code quality.

**Key Principle**: The system **proposes fixes only** - it does NOT automatically apply changes to user code.

## System Architecture Diagram

```mermaid
flowchart TB
    subgraph UserSpace["👤 User Space"]
        UserApp["User Production App<br/>(Python/Node.js/etc)"]
        ClientSnippet["WebSocket Client Snippet<br/>(~50 lines)"]
        UserApp --> ClientSnippet
    end

    subgraph SelfHealerSystem["🏥 Self-Healer System (Single VM)"]
        subgraph Gateway["WebSocket Gateway"]
            WSEndpoint["wss://service.com/ws/logs/{user_id}"]
            JWTAuth["JWT Authentication"]
            Encryption["TLS 1.3 + Encrypted Payloads"]
        end

        subgraph CoreServices["Core Backend Services (FastAPI + asyncio)"]
            LogGateway["Log Gateway Service<br/>• Receives log streams<br/>• Buffers in Redis<br/>• Filters autocure-try"]
            
            ErrorDetection["Error Detection Engine<br/>• Regex pattern matching<br/>• AI-powered classification<br/>• Stack trace parsing"]
            
            RepoSync["Repo Sync Service<br/>• Git clone on signup<br/>• Periodic git pull (5-15min)<br/>• Commit hash caching"]
            
            ASTParser["AST Codebase Parser<br/>• Tree-sitter (multi-lang)<br/>• Symbol table extraction<br/>• Cross-reference mapping"]
            
            RootCause["Root Cause Analyzer<br/>• Error replication<br/>• AST traversal<br/>• Context building<br/>• AI reasoning"]
            
            CodeReview["Code Review Engine<br/>• PR diff fetching<br/>• 3-dot diff analysis<br/>• Style/security checks"]
            
            EmailService["Email Service<br/>• Rich HTML reports<br/>• AST visualization<br/>• Fix proposals"]
        end

        subgraph DataLayer["Data Layer"]
            PostgreSQL[("PostgreSQL<br/>• users<br/>• repositories<br/>• error_logs<br/>• analysis_history<br/>• code_reviews")]
            
            Redis[("Redis<br/>• Sessions<br/>• Log buffers<br/>• AST cache (24h TTL)<br/>• Rate limiting<br/>• Pub/Sub")]
            
            FileSystem[("File System<br/>/workspaces/{user_id}/{repo}<br/>• Free: 100MB/repo, 5 repos<br/>• Pro: 1GB/repo, unlimited")]
        end
    end

    subgraph External["☁️ External Services"]
        GitHub["GitHub API<br/>• Repo cloning (PAT)<br/>• PR diff fetching<br/>• Webhooks (optional)"]
        
        AIProviders["AI Providers<br/>• Groq (free, fast)<br/>• Cerebras (free, fast)<br/>via OpenAI SDK"]
        
        SMTP["Google SMTP<br/>• App passwords<br/>• Admin sender<br/>• User recipients"]
    end

    %% Connections
    ClientSnippet -->|"JSON logs over WSS"| WSEndpoint
    WSEndpoint --> JWTAuth
    JWTAuth --> Encryption
    Encryption --> LogGateway
    
    LogGateway --> Redis
    LogGateway --> ErrorDetection
    
    ErrorDetection -->|"Error detected"| RepoSync
    ErrorDetection -->|"Classify severity"| AIProviders
    
    RepoSync --> GitHub
    RepoSync --> FileSystem
    RepoSync -->|"Files changed"| ASTParser
    
    ASTParser --> Redis
    ASTParser --> RootCause
    
    RootCause -->|"Build context"| AIProviders
    RootCause --> EmailService
    RootCause --> PostgreSQL
    
    CodeReview --> GitHub
    CodeReview --> AIProviders
    CodeReview --> EmailService
    
    EmailService --> SMTP
    EmailService --> PostgreSQL
    
    LogGateway --> PostgreSQL
    ErrorDetection --> PostgreSQL
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant App as User App
    participant WS as WebSocket Gateway
    participant Redis as Redis
    participant ED as Error Detection
    participant Git as Git/GitHub
    participant AST as AST Parser
    participant AI as AI (Groq/Cerebras)
    participant DB as PostgreSQL
    participant Email as Email Service

    App->>WS: Connect (JWT auth)
    WS->>Redis: Register session
    
    loop Real-time Logging
        App->>WS: Log entry (JSON)
        WS->>Redis: Buffer log
        WS->>ED: Process log
        
        alt Error Detected
            ED->>DB: Store error_log
            ED->>Git: git pull (if needed)
            Git->>AST: Parse changed files
            AST->>Redis: Cache AST (24h TTL)
            AST->>AI: Build context + analyze
            AI->>DB: Store analysis
            AI->>Email: Send report
            Email->>App: Notification to admin
        end
    end
```

## Database Schema (ERD)

```mermaid
erDiagram
    USERS ||--o{ REPOSITORIES : owns
    USERS ||--o{ WEBSOCKET_SESSIONS : has
    USERS ||--o{ AUDIT_LOGS : generates
    USERS ||--o{ RATE_LIMITS : subject_to
    
    REPOSITORIES ||--o{ ERROR_LOGS : contains
    REPOSITORIES ||--o{ ANALYSIS_HISTORY : has
    REPOSITORIES ||--o{ CODE_REVIEWS : receives
    
    ERROR_LOGS ||--o| ANALYSIS_HISTORY : analyzed_by

    USERS {
        uuid id PK
        string email UK
        string password_hash
        string name
        string tier "free|pro"
        int max_repos
        int max_storage_per_repo_mb
        string websocket_token
        boolean notifications_enabled
        boolean is_active
        timestamp created_at
    }

    REPOSITORIES {
        uuid id PK
        uuid user_id FK
        string repo_url
        string repo_name
        string repo_owner
        string base_branch
        bytea github_token_encrypted
        string workspace_path
        decimal current_storage_mb
        string last_commit_hash
        timestamp last_sync_at
        string sync_status
        string admin_email
    }

    ERROR_LOGS {
        uuid id PK
        uuid repo_id FK
        string error_type
        text error_message
        text stack_trace
        string file_path
        int line_number
        string api_endpoint
        jsonb request_payload
        string severity
        string status
        timestamp occurred_at
    }

    ANALYSIS_HISTORY {
        uuid id PK
        uuid error_log_id FK
        uuid repo_id FK
        text root_cause
        decimal confidence
        text fix_proposal
        text fix_diff
        jsonb affected_files
        string risk_level
        string ai_provider
        boolean email_sent
    }

    CODE_REVIEWS {
        uuid id PK
        uuid repo_id FK
        int pr_number
        string pr_title
        int overall_score
        text summary
        jsonb comments
        boolean has_security_issues
    }
```

## Component Responsibilities

### 1. WebSocket Client Snippet (~50 lines)
**Runs in user's production app**

- **Role**: Captures and forwards logs (does NOT trace errors)
- **Features**:
  - Captures stdout/stderr
  - Intercepts application logs
  - Captures error stack traces
  - Auto-reconnection with heartbeat (30s)
  - Adds metadata (timestamp, level)
- **Output**: JSON log entries over secure WebSocket

### 2. Error Detection Engine
**Our system traces the error**

- **Role**: Identifies errors from log streams
- **Features**:
  - Regex patterns for common errors
  - AI-powered classification (Groq/Cerebras)
  - Stack trace extraction and parsing
  - API endpoint correlation
  - Severity assessment
- **Filters out**: Logs with `autocure-try: true` flag

### 3. AST Codebase Parser
- **Role**: Builds searchable code structure
- **Features**:
  - Tree-sitter for multi-language support
  - Symbol table extraction
  - Cross-reference mapping
  - Cached in Redis (24h TTL)

### 4. Root Cause Analyzer
- **Role**: AI-powered error investigation
- **Pipeline**:
  1. Parse stack trace → identify file/line/function
  2. AST traversal → walk parents/children/dependencies
  3. Context building → compile {logs, ast, code, deps}
  4. AI reasoning → root cause + fix proposal
- **Output**: Proposal only (NOT applied)

### 5. Email Service
- **Role**: Delivers rich HTML reports
- **Sender**: Admin email (Google App Password)
- **Recipients**: Per-repo admin from `repositories.admin_email`

## Storage Tiers

| Feature | Free Tier | Pro Tier (Future) |
|---------|-----------|-------------------|
| Max Repositories | 5 | Unlimited |
| Storage per Repo | 100 MB | 1 GB |
| Rate Limit (logs/sec) | 100 | 500 |
| Rate Limit (PRs/hour) | 10 | 50 |

## Security Architecture

```mermaid
flowchart LR
    subgraph Transport["Transport Security"]
        TLS["TLS 1.3"]
        WSS["WSS (WebSocket Secure)"]
    end
    
    subgraph Auth["Authentication"]
        JWT["JWT Tokens"]
        HMAC["HMAC-SHA256 Signing"]
    end
    
    subgraph DataSec["Data Security"]
        Fernet["Fernet Encryption<br/>(GitHub tokens)"]
        PgCrypto["pgcrypto<br/>(DB encryption)"]
        Bcrypt["bcrypt<br/>(passwords)"]
    end
    
    subgraph Isolation["Tenant Isolation"]
        Workspace["Separate /workspaces/{user}"]
        RedisNS["Redis Namespaces"]
        DBRows["Row-level security"]
    end
```

## External Services

| Service | Purpose | Auth Method |
|---------|---------|-------------|
| **GitHub API** | Repo clone, PR diffs | User's PAT (read-only) |
| **Groq** | AI inference (free, fast) | API Key via OpenAI SDK |
| **Cerebras** | AI inference (free, fast) | API Key via OpenAI SDK |
| **Google SMTP** | Email delivery | App Password |

### About GitHub PAT Access

- User generates PAT with `repo:read` scope from their GitHub account
- PAT allows reading private repos **that the user owns/has access to**
- Token is encrypted at rest using pgcrypto
- Future: Can implement GitHub OAuth App for seamless authorization

## Deployment (Single VM)

```
┌─────────────────────────────────────────────────────────────┐
│                     Single VM (4+ vCPU, 8+ GB RAM)          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   Nginx         │  │   FastAPI       │                   │
│  │   (Reverse      │──│   (Uvicorn      │                   │
│  │    Proxy, SSL)  │  │    Workers)     │                   │
│  └─────────────────┘  └─────────────────┘                   │
│                              │                               │
│           ┌──────────────────┼──────────────────┐           │
│           │                  │                  │           │
│  ┌────────▼────────┐ ┌───────▼───────┐ ┌───────▼───────┐   │
│  │   PostgreSQL    │ │    Redis      │ │  File System  │   │
│  │   (Port 5432)   │ │   (Port 6379) │ │  /workspaces  │   │
│  └─────────────────┘ └───────────────┘ └───────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Future Enhancements (Not for MVP)

1. **Frontend Dashboard** (React/Next.js)
   - User registration/login
   - Repository management
   - Error reports viewer

2. **GitHub OAuth App**
   - Seamless repo authorization
   - No PAT copy-paste

3. **Cloud Storage** (S3/GCS)
   - Long-term report archives
   - AST visualization storage

4. **Horizontal Scaling**
   - Multiple FastAPI pods
   - Redis cluster
   - Load balancer   │
                    │  │  2. Generate fix proposal      │   │
                    │  │  3. Generate test cases        │   │
                    │  │  4. Run tests in sandbox       │   │
                    │  │  5. Pass? → Complete           │   │
                    │  │  6. Fail? → Improve & retry    │   │
                    │  └─────────────────────────────────┘   │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │          EMAIL NOTIFIER                 │
                    │                                         │
                    │  • SMTP with TLS                       │
                    │  • Gmail App Password auth             │
                    │  • HTML + Plain text reports           │
                    │  • Git branch links                    │
                    │  • Test results summary                │
                    └─────────────────────────────────────────┘
```

## Component Descriptions

### 1. Main Orchestrator (`src/main.py`)

The central coordinator that manages the entire self-healing workflow.

**Responsibilities:**
- Initialize all subprocess components
- Start and monitor the target service
- Listen for error events from the log watcher
- Trigger the healing workflow when errors are detected
- Coordinate between components
- Handle graceful shutdown

**Workflow:**
```python
async def run():
    1. Initialize all components
    2. Start target service (subprocess2)
    3. Start log watcher (subprocess1)
    4. Wait for error detection
    5. On error:
       a. Process error (subprocess3)
       b. Run AI healing agent
       c. Create git branch (subprocess4)
       d. Send email notification
    6. Continue monitoring
```

### 2. Log Watcher - Subprocess 1 (`src/subprocesses/log_watcher.py`)

Monitors log files for errors and warnings in real-time.

**Features:**
- Asynchronous file watching
- Pattern-based error detection
- Stack trace parsing
- Multiple error type recognition (TypeError, ReferenceError, etc.)
- Severity classification

**Detection Patterns:**
- `Error:`, `TypeError:`, `ReferenceError:`, `SyntaxError:`
- `[ERROR]`, `FATAL:`, `Exception:`
- Stack trace lines (`at function (file:line:column)`)

### 3. Target Service - Subprocess 2 (`demo_service/server.js`)

The application being monitored (demo Node.js server with intentional bugs).

**Intentional Error Zones:**
1. Undefined variable access
2. Array index out of bounds
3. Division by zero
4. Undefined callbacks
5. JSON parsing without error handling

### 4. Error Processor - Subprocess 3 (`src/subprocesses/error_processor.py`)

Traces errors to their origin in source code.

**Capabilities:**
- Stack trace parsing (JavaScript, Python patterns)
- Source file resolution
- Code context extraction (lines before/after error)
- Root cause analysis
- Related file discovery

### 5. Git Handler - Subprocess 4 (`src/subprocesses/git_handler.py`)

Manages version control operations for fix branches.

**Operations:**
- Create uniquely named fix branches (`ai-fix/error-type-timestamp-id`)
- Apply fixes to target files
- Generate descriptive commit messages
- Optional push to remote
- PR/MR information generation

### 6. AI Healing Agent (`src/agents/healing_agent.py`)

The core AI-powered healing logic.

**Process:**
```
┌─────────────────────────────────────────────────────────────┐
│                    HEALING AGENT WORKFLOW                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Receive Error   │
                    │ Info            │
                    └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Read Source     │
                    │ Code            │
                    └────────┬────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      FIX ATTEMPT LOOP         │
              │      (max 5 attempts)         │
              │                               │
              │   ┌─────────────────────┐    │
              │   │ Generate Fix (AI)   │    │
              │   └──────────┬──────────┘    │
              │              │               │
              │              ▼               │
              │   ┌─────────────────────┐    │
              │   │ Generate Tests (AI) │    │
              │   └──────────┬──────────┘    │
              │              │               │
              │              ▼               │
              │   ┌─────────────────────┐    │
              │   │ Run Tests in        │    │
              │   │ Sandbox             │    │
              │   └──────────┬──────────┘    │
              │              │               │
              │         ┌────┴────┐          │
              │         │ PASS?   │          │
              │         └────┬────┘          │
              │              │               │
              │     YES ─────┼───── NO       │
              │       │      │      │        │
              │       ▼      │      ▼        │
              │   Complete   │   Analyze     │
              │              │   Failure     │
              │              │      │        │
              │              │      ▼        │
              │              │   Improve     │
              │              │   Fix         │
              │              │      │        │
              │              └──────┘        │
              └───────────────────────────────┘
```

### 7. AI Client (`src/agents/ai_client.py`)

Unified interface for AI providers using OpenAI-compatible APIs.

**Supported Providers:**
| Provider | Base URL | Models |
|----------|----------|--------|
| Groq | `https://api.groq.com/openai/v1` | llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768 |
| Cerebras | `https://api.cerebras.ai/v1` | llama3.1-8b, llama3.1-70b |

**API Methods:**
- `chat_completion()` - General chat completions
- `generate_fix()` - Error-specific fix generation
- `generate_tests()` - Test case generation
- `analyze_test_failure()` - Failure analysis and fix improvement

### 8. Email Notifier (`src/subprocesses/email_notifier.py`)

Sends comprehensive email reports to administrators.

**Features:**
- SMTP with TLS encryption
- Gmail App Password authentication
- HTML formatted reports with styling
- Plain text fallback
- Report contents:
  - Error details and severity
  - Root cause analysis
  - Fix explanation
  - Test results
  - Git branch information

## Data Models (`src/utils/models.py`)

### LogEntry
Represents a single log entry with timestamp, level, message, source, and stack trace.

### ErrorInfo
Detailed error information including:
- Error type and message
- Stack trace
- Source file and line
- Severity level
- Code context
- Root cause analysis

### FixProposal
A proposed fix with:
- Original and fixed code
- Explanation
- Confidence score
- Status (pending, testing, passed, failed)
- Attempt number

### TestResult
Test execution results:
- Pass/fail status
- Test counts
- Output and error messages
- Execution time

### HealingReport
Complete healing operation report:
- All fix proposals
- All test results
- Final fix (if successful)
- Git information
- Summary generation

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_PROVIDER` | AI provider (groq/cerebras) | groq |
| `GROQ_API_KEY` | Groq API key | - |
| `CEREBRAS_API_KEY` | Cerebras API key | - |
| `SMTP_SERVER` | SMTP server address | smtp.gmail.com |
| `SMTP_PORT` | SMTP server port | 587 |
| `SENDER_EMAIL` | Email sender address | - |
| `SENDER_PASSWORD` | Email app password | - |
| `ADMIN_EMAIL` | Admin notification email | - |
| `MAX_FIX_ATTEMPTS` | Maximum fix attempts | 5 |
| `LOG_WATCH_INTERVAL` | Log check interval (seconds) | 1.0 |
| `TEST_TIMEOUT` | Test execution timeout (seconds) | 60 |

## Security Considerations

1. **API Keys**: Store in `.env` file, never commit to version control
2. **Email Credentials**: Use App Passwords, not actual passwords
3. **Git Operations**: Ensure proper SSH/HTTPS authentication
4. **Sandbox Testing**: Fixes are tested in isolated temporary directories

## Scalability

The system can be extended for:
- Multiple monitored services
- Different programming languages
- Custom error patterns
- Additional AI providers
- Distributed deployment with message queues
- Kubernetes integration (see full implementation plan)

## Error Handling

- Graceful degradation when AI fails
- Retry logic for API calls
- Timeout handling for tests
- Cleanup of temporary directories
- Signal handling for shutdown

## Future Enhancements

1. Web dashboard for monitoring and approvals
2. Slack/Teams integration
3. Custom plugin system for error handlers
4. Machine learning for error pattern recognition
5. Automated PR creation
6. Multi-language support (Python, Java, Go)
7. Container-based testing environments
8. Integration with CI/CD pipelines
