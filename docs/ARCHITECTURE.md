# Self-Healing Software System - Architecture Documentation

## System Overview

The Self-Healing Software System is an AI-driven automated error detection, analysis, and resolution platform. It monitors application logs in real-time, detects errors, traces them to source code, generates fixes using large language models, validates fixes through automated testing, and creates version-controlled branches for review.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SELF-HEALING SOFTWARE SYSTEM                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAIN ORCHESTRATOR                                  │
│                            (main.py)                                        │
│  • Manages all subprocesses                                                 │
│  • Coordinates healing workflow                                             │
│  • Handles graceful shutdown                                                │
└─────────────────────────────────────────────────────────────────────────────┘
          │                    │                    │                    │
          ▼                    ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  SUBPROCESS 1   │  │  SUBPROCESS 2   │  │  SUBPROCESS 3   │  │  SUBPROCESS 4   │
│  Log Watcher    │  │ Target Service  │  │ Error Processor │  │  Git Handler    │
│                 │  │                 │  │                 │  │                 │
│ • Monitor logs  │  │ • Node.js app   │  │ • Parse traces  │  │ • Create branch │
│ • Detect errors │  │ • Generate logs │  │ • Find origin   │  │ • Commit fixes  │
│ • Parse stack   │  │ • Error source  │  │ • Get context   │  │ • Push remote   │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │                    │
         └────────────────────┴─────────┬──────────┴────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │            AI HEALING AGENT             │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │         AI CLIENT               │   │
                    │  │  • Groq API (llama-3.3-70b)    │   │
                    │  │  • Cerebras API (llama3.1-8b)  │   │
                    │  │  • OpenAI-compatible endpoints │   │
                    │  └─────────────────────────────────┘   │
                    │                  │                      │
                    │                  ▼                      │
                    │  ┌─────────────────────────────────┐   │
                    │  │     FIX GENERATION LOOP        │   │
                    │  │                                 │   │
                    │  │  1. Analyze error context      │   │
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
