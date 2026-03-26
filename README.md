# AutoCure — Self-Healing Software System v2.0

**An AI-powered end-to-end error analysis & fix proposal platform** that detects runtime errors, performs deep root-cause analysis using AST parsing and multi-agent AI, validates findings through iterative confidence scoring, and delivers rich HTML reports with actionable fix proposals and PR code reviews.

> **What AutoCure Does**
> - 🚨 **Detects errors** in real-time via WebSocket-enabled log streaming from production applications
> - 🔍 **Analyzes root causes** using AST parsing (tree-sitter, 26+ languages), error replication, and multi-agent AI (via Groq/Cerebras)
> - 📋 **Proposes fixes** with confidence scoring, risk assessment, and side-effect analysis  
> - 📨 **Sends reports** via email with interactive AST trees and proposal recommendations
> - 🎨 **Provides a dashboard** for live connection monitoring, log viewing, and report browsing
> - 🌳 **Visualizes ASTs** in a browser-based React UI with drag/zoom, code-to-tree navigation, and cross-file reference resolution

> **What AutoCure Does NOT Do**
> - Does NOT automatically commit or push fixes to the production branch (human review required)
> - Does NOT modify your codebase directly (a new branch is created for the fix)
> - Does NOT replace developer judgment — it provides recommendations

---

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Complete Usage Guide](#complete-usage-guide)
- [SDK & Client Libraries](#sdk--client-libraries)
- [Dashboard Features](#dashboard-features)
- [AST Visualizer](#ast-visualizer)
- [API Reference](#api-reference)
- [GitHub Webhook Integration](#github-webhook-integration)
- [End-to-End Testing](#end-to-end-testing)
- [Demo Service](#demo-service)
- [Project Structure](#project-structure)
- [Supported Languages](#supported-languages)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)

---

## Quick Start

**Get AutoCure running in 5 minutes:**

```bash
# 1. Clone & setup
git clone https://github.com/mihir0209/Self-Healer.git
cd Self-Healer
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your Groq/Cerebras API key and database details

# 3. Start server
python src/main.py
# Or: uvicorn src.main:app --host 0.0.0.0 --port 9292 --reload

# 4. Open dashboard
# http://localhost:9292 (default login: demo/demo)
```

That's it! Your AutoCure server is now running. See [Complete Usage Guide](#complete-usage-guide) for the next steps.

---

## Features

- **Real-time Error Detection** — WebSocket-based log streaming from production with live dashboard feed
- **Multi-Agent AI Analysis** — Microsoft AutoGen with `llama-3.3-70b` (Groq/Cerebras) for intelligent classification and RCA
- **AST-Based Code Understanding** — tree-sitter parsing (26+ languages) with cross-file reference resolution
- **Interactive AST Visualization** — Browser React UI with drag, zoom, expand/collapse, code-to-tree linking
- **Iterative Confidence Scoring** — Multiple analysis passes to validate and score fix confidence
- **Intelligent Fix Proposals** — AI-generated patches with risk level, side effects, test cases
- **AI Code Review for PRs** — Automated review with per-file comments and overall assessment
- **Rich HTML Reports** — Dark-themed standalone reports with interactive AST trees, charts, collapsible sections
- **Email Notifications** — Detailed HTML emails with findings, proposals, and direct report links
- **Modern Web Dashboard** — FastAPI + Jinja2 with live connections, logs, reports, integration guides
- **Multi-Tenant Isolation** — Per-user workspace with storage quotas and JWT authentication
- **GitHub Integration** — Webhook receiver for automatic PR reviews and push-triggered analysis

---

## Architecture Overview

```
┌──────────────┐     WebSocket      ┌──────────────────────────────────────────┐
│  Your App    │ ──────────────────► │  AutoCure Server (FastAPI)               │
│  (any lang)  │   live log stream   │                                          │
└──────────────┘                     │  ┌─────────────┐   ┌──────────────────┐  │
                                     │  │ Log Analyzer│──►│ Error Replicator │  │
                                     │  └──────┬──────┘   └──────────────────┘  │
                                     │         │                                │
                                     │         ▼                                │
                                     │  ┌─────────────┐   ┌──────────────────┐  │
                                     │  │ GitHub Svc  │──►│ AST Service      │  │
                                     │  │ (repo sync) │   │ (tree-sitter)    │  │
                                     │  └──────┬──────┘   └────────┬─────────┘  │
                                     │         │                   │            │
                                     │         ▼                   ▼            │
                                     │  ┌──────────────────────────────────┐    │
                                     │  │  AutoGen AI Analyzer             │    │
                                     │  │  (multi-agent, llama-3.3-70b)    │    │
                                     │  └──────────────┬───────────────────┘    │
                                     │                 │                        │
                                     │                 ▼                        │
                                     │  ┌─────────────┐   ┌──────────────────┐  │
                                     │  │ Confidence  │   │  Email Service   │  │
                                     │  │ Validator   │   │  (SMTP reports)  │  │
                                     │  └─────────────┘   └──────────────────┘  │
                                     │                                          │
                                     │  ┌─────────────┐   ┌──────────────────┐  │
                                     │  │ PostgreSQL  │   │  Redis           │  │
                                     │  │ (reports)   │   │  (sessions/cache)│  │
                                     │  └─────────────┘   └──────────────────┘  │
                                     └──────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Server** | FastAPI, Uvicorn, Jinja2 templates |
| **AI** | Microsoft AutoGen 0.7+, llama-3.3-70b (Groq / Cerebras), other BYOK providers to be introduced. |
| **AST Parsing** | tree-sitter 0.21+, tree-sitter-languages (26 languages) |
| **Frontend** | React 19, Vite 7, Tailwind CSS, Phosphor Icons |
| **Database** | PostgreSQL 14+ (reports, users), Redis 7+ (sessions, cache) |
| **Auth** | JWT (python-jose), bcrypt password hashing |
| **Email** | SMTP (Gmail App Passwords), HTML report templates |
| **VCS** | Git CLI integration, GitHub webhook receiver |

---

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 7+
- Node.js 18+ (for the demo service)
- Git
- An API key for **Groq** or **Cerebras** (both offer free tiers)

---

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd SelfHealer
```

### 2. Set up Python environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Set up PostgreSQL / SQLite directly into codebase (default if not created)

```bash
createdb selfhealer
psql selfhealer < src/database/schema.sql
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values (see [Configuration](#configuration)).


---

## Configuration

Create a `.env` file in the project root:

```env
# ── AI Provider ──────────────────────────────────────────────
AI_PROVIDER=cerebras              # "groq" or "cerebras"
GROQ_API_KEY=gsk_...              # https://console.groq.com/keys
CEREBRAS_API_KEY=csk-...          # https://cloud.cerebras.ai/

# ── Database ─────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=selfhealer
DB_USER=postgres
DB_PASSWORD=your_password

# ── Redis ────────────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379

# ── Email Notifications ─────────────────────────────────────
SENDER_EMAIL=you@gmail.com
SENDER_PASSWORD=xxxx-xxxx-xxxx    # Gmail App Password
ADMIN_EMAIL=admin@example.com

# ── Server ───────────────────────────────────────────────────
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
JWT_SECRET=change-this-in-production

# ── GitHub (optional) ────────────────────────────────────────
GITHUB_TOKEN=ghp_...              # For private repos
GITHUB_WEBHOOK_SECRET=your-secret
```

### AI Provider Notes

| Provider | Free Tier | Model | API Key |
|----------|-----------|-------|---------|
| **Groq** | 6,000 req/day | `llama-3.3-70b-versatile` | [console.groq.com/keys](https://console.groq.com/keys) |
| **Cerebras** | 10,000 req/day | `llama-3.3-70b` | [cloud.cerebras.ai](https://cloud.cerebras.ai/) |

---

## Running the System

```bash
# Start the FastAPI server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Or via the shortcut:

```bash
python src/main.py
```

Once running, open:

| URL | Description |
|-----|-------------|
| `http://localhost:9292/` | Dashboard (login required) |
| `http://localhost:9292/login` | Authentication page |
| `http://localhost:9292/visualizer` | AST Visualizer (React SPA) |
| `http://localhost:9292/health` | Health check (JSON) |
| `http://localhost:9292/languages` | Languages Supported (JSON) |

---

## Dashboard

The web dashboard provides a complete operational overview:

- **Home** — System summary: active connections, registered repos, recent reports, error counts.
- **Connections** — Live WebSocket connections with per-user status and uptime.
- **Logs** — Searchable log viewer with severity filtering and real-time updates.
- **Reports** — Browse, filter, and view all generated analysis reports. Click to open the full interactive HTML report.
- **Integration** — Copy-paste WebSocket client snippets for Python, JavaScript, and other languages.
- **AST Visualizer** — Select a registered repository, browse its files, and parse any file into an interactive AST tree.

The dashboard uses server-sent WebSocket events for live data — no polling required.

---

## AST Visualizer

The dedicated visualizer at `/visualizer` is a React single-page application for exploring Abstract Syntax Trees:

- **Upload** a `.zip` project archive or a single source file.
- **Browse** files in the uploaded project via the sidebar.
- **Parse** any file to generate a full AST with tree-sitter.
- **Navigate** the tree: click nodes to expand/collapse, drag to pan, scroll to zoom.
- **Code Panel** shows the original source with line highlighting — click a tree node to jump to its source line, click a source line to locate it in the tree.
- **Cross-file references** are resolved and displayed as navigable links.

Supported input: Any of the 26+ languages supported by tree-sitter-languages.

---

## Integrating with Your Application

Add the lightweight WebSocket client to your application. It captures console output, exceptions, and log events, then streams them to AutoCure in real time.

### Python

```python
# see src/websocket_client/python_client.py
import asyncio, websockets, json, sys, traceback

async def stream_logs(server_url, user_id):
    async with websockets.connect(f"{server_url}/{user_id}") as ws:
        # Send log entries as JSON
        await ws.send(json.dumps({
            "level": "error",
            "message": "Something went wrong",
            "source": "app.py",
            "line": 42,
            "stack_trace": traceback.format_exc()
        }))
```

### JavaScript / Node.js

```javascript
// ~50 lines — see src/websocket_client/js_client.js
const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:8000/ws/logs/my-service');

// Express error middleware
app.use((err, req, res, next) => {
    ws.send(JSON.stringify({
        level: 'error',
        message: err.message,
        source: err.stack?.split('\n')[1]?.trim(),
        stack_trace: err.stack
    }));
    next(err);
});
```

Full client examples with reconnection, heartbeat, and authentication are in `src/websocket_client/`.

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/login` | Dashboard login (form) |
| GET | `/logout` | Clear session |

### User & Repository Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/register` | Register user + repository (clone repo) |
| GET | `/api/v1/user/{user_id}` | Get user registration details |
| DELETE | `/api/v1/user/{user_id}` | Unregister user, clean up data |
| POST | `/api/v1/repo/{user_id}/sync` | Git pull to sync repository |
| GET | `/api/v1/repo/{user_id}/status` | Repository sync status |
| GET | `/api/v1/repo/{user_id}/files` | List source files (optional `?ext=` filter) |
| POST | `/api/v1/repo/{user_id}/ast` | Parse a repo file → AST JSON |
| GET | `/api/v1/repos/registered` | List all registered users/repos |

### Analysis & Review

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze/{user_id}` | Trigger error analysis for a user |
| POST | `/api/v1/review/{user_id}/pr` | AI code review for a pull request |
| POST | `/api/v1/webhook/github` | GitHub webhook receiver (PR, push) |

### Logs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/logs` | Recent logs (all users) |
| GET | `/api/v1/logs/{user_id}` | Recent logs for a user |
| DELETE | `/api/v1/logs/{user_id}` | Clear cached logs |

### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reports` | List reports (filter by `?user_id=`, `?severity=`, `?limit=`) |
| GET | `/api/v1/reports/stats` | Report statistics |
| GET | `/api/v1/reports/{id}` | Report metadata (JSON) |
| GET | `/api/v1/reports/{id}/view` | Full HTML report in browser |
| DELETE | `/api/v1/reports/{id}` | Delete a report |

### AST Parsing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/parse/code` | Parse a code snippet → AST |
| POST | `/api/v1/parse/file` | Parse a repo file → AST |
| GET | `/api/v1/languages` | Supported languages + extensions |
| POST | `/api/v1/visualize/repo` | Parse all files in a registered repo |
| POST | `/upload/zip` | Upload ZIP project for visualization |
| POST | `/upload/file` | Upload single file for visualization |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/status` | System status and statistics |
| GET | `/api/v1/users` | Dashboard user list |
| GET | `/api/v1/connections` | Active WebSocket connections |
| GET | `/api/v1/dashboard/summary` | Dashboard summary state |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `ws://host/ws/logs/{user_id}` | Log streaming from user apps |
| `ws://host/ws/dashboard` | Dashboard live event broadcast |

---

## SDK & Client Libraries

AutoCure provides lightweight, language-agnostic client libraries for streaming logs and receiving real-time fix proposals. Choose the integration approach that best fits your architecture.

### Python WebSocket Client (Basic)

File: `src/websocket_client/python_client.py` (~50 lines)

```python
import asyncio, websockets, json, sys, traceback
from websocket_client.python_client import WebSocketClient

async def on_message(msg):
    print(f"[{msg['timestamp']}] {msg['type']}: {msg.get('content', '')}")

client = WebSocketClient(
    server_url="ws://localhost:9292",
    token="your_jwt_token_here"
)
client.on_message += on_message

# Or integrate into your error handler:
try:
    risky_operation()
except Exception as e:
    await client.send({
        'type': 'error',
        'error_type': type(e).__name__,
        'message': str(e),
        'traceback': traceback.format_exc(),
        'source': 'app.py'
    })
```

### Python Advanced Handler (Recommended)

File: `src/websocket_client/autocure_handler.py` (~150 lines)

Adds auto-reconnect, heartbeat, decorator-based callbacks, and command queuing:

```python
from src.websocket_client.autocure_handler import AutoCureHandler

handler = AutoCureHandler(
    server_url="ws://localhost:9292",
    token="your_jwt_token_here",
    reconnect_interval=3,      # seconds
    heartbeat_interval=10,     # seconds
    max_queue_size=1000
)

@handler.on('log')
def on_log(msg):
    """Called when a log message is received."""
    print(f"Log: {msg['content']}")

@handler.on('analysis_complete')
async def on_analysis(report):
    """Called when AI analysis is complete."""
    print(f"Fix ready (confidence: {report['confidence_score']}%)")
    print(f"Proposed code:\n{report['fix_code']}")

@handler.on('error')
def on_error(error):
    """Called on connection errors."""
    print(f"Error: {error}")

# Start handler (runs in background)
await handler.connect()

# In your error handler:
await handler.send({
    'type': 'error',
    'error_type': 'ZeroDivisionError',
    'message': 'division by zero',
    'traceback': traceback.format_exc(),
    'context': {'user_id': 123}
})

# Graceful shutdown
await handler.disconnect()
```

### JavaScript / Node.js Client

File: `src/websocket_client/js_client.js` (~50 lines)

Simple WebSocket wrapper:

```javascript
const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:9292/ws/logs/my-user-id');

ws.on('open', () => {
    console.log('Connected to AutoCure');
    
    // Send an error event
    ws.send(JSON.stringify({
        type: 'error',
        error_type: 'TypeError',
        message: 'Cannot read property "name" of undefined',
        source: 'app.js',
        line: 45,
        stack_trace: new Error().stack
    }));
});

ws.on('message', (data) => {
    const msg = JSON.parse(data);
    if (msg.type === 'analysis_complete') {
        console.log('Fix proposal:', msg.fix_code);
    }
});

ws.on('error', (err) => {
    console.error('WebSocket error:', err);
});
```

### JavaScript Advanced Handler

File: `src/websocket_client/autocure_handler.js` (~150 lines)

Class-based handler with decorators, reconnect logic, and heartbeat:

```javascript
const { AutoCureHandler } = require('./src/websocket_client/autocure_handler.js');

const handler = new AutoCureHandler({
    serverUrl: 'ws://localhost:9292',
    token: 'your_jwt_token_here',
    reconnectInterval: 3000,
    heartbeatInterval: 10000
});

// Register event listeners using decorators
handler.on('log', (msg) => {
    console.log(`[${msg.timestamp}] ${msg.type}: ${msg.content}`);
});

handler.on('analysis_complete', async (report) => {
    console.log('Fix proposal:', report.fix_code);
    console.log('Confidence:', report.confidence_score);
});

// For Express error middleware:
app.use((err, req, res, next) => {
    handler.send({
        type: 'error',
        error_type: err.name,
        message: err.message,
        source: err.stack?.split('\n')[1]?.trim(),
        stack_trace: err.stack
    }).catch(e => console.error('Failed to send error:', e));
    
    res.status(500).json({ error: err.message });
});

await handler.connect();
```

### Example Integration (Full App)

File: `demo_services/autocure_client.py`

Complete example of integrating AutoCure into a production application:

```python
import asyncio
import logging
from src.websocket_client.autocure_handler import AutoCureHandler

# Initialize handler
handler = AutoCureHandler(
    server_url="ws://localhost:9292",
    token="your_jwt_token",
    reconnect_interval=3
)

@handler.on('analysis_complete')
async def on_fix_ready(report):
    """
    When a fix is ready:
    1. Log the proposal
    2. Run test suite
    3. If tests pass, create PR
    4. Assign for review
    """
    logging.info(f"Fix ready (confidence: {report['confidence_score']}%)")
    
    # Optional: trigger auto-PR creation
    if report['confidence_score'] >= 80:
        create_pull_request(
            branch_name=report['branch_name'],
            fix_code=report['fix_code'],
            description=report['analysis_summary']
        )

# Start handler at app startup
asyncio.create_task(handler.connect())

# In your exception handler:
# await handler.send({...error details...})
```

### Event Protocol

Both handlers send/receive JSON messages with this schema:

**Client → Server (Error Event):**
```json
{
  "type": "error",
  "error_type": "ZeroDivisionError",
  "message": "float division by zero",
  "traceback": "Traceback (most recent call last):\n...",
  "source": "app.py",
  "line": 42,
  "context": {
    "user_id": 123,
    "request_id": "abc-def-ghi",
    "environment": "production"
  }
}
```

**Server → Client (Analysis Result):**
```json
{
  "type": "analysis_complete",
  "report_id": "report-uuid",
  "error_type": "ZeroDivisionError",
  "confidence_score": 87.5,
  "fix_code": "if denominator != 0:\n    result = numerator / denominator",
  "risk_level": "low",
  "analysis_summary": "Division by zero due to unvalidated input...",
  "branch_name": "fix/zero-division-123",
  "side_effects": []
}
```

See [HANDLER_INTEGRATION.md](docs/HANDLER_INTEGRATION.md) for complete protocol specification and advanced configuration.

---

## Complete Usage Guide

### 1. First-Time Setup (5 minutes)

#### 1.1 Start the Server

```bash
# Activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Start the server
python src/main.py
# Server starts on http://localhost:9292
```

#### 1.2 Create an Account

1. Open your browser to `http://localhost:9292`
2. Click **Sign Up** (or login with demo/demo credentials)
3. Enter username and password
4. Click Submit

You are now registered!

#### 1.3 Connect Your First Repository

1. In the dashboard, navigate to the **Connections** tab
2. Click **+ Register Repository**
3. Paste the GitHub repository URL (can be private or public)
4. Click Submit

AutoCure clones the repository to a workspace. You're ready for error analysis!

### 2. Sending Errors from Your Application (10 minutes)

Choose one of these integration methods:

#### Option A: WebSocket Direct (Real-time, Recommended)

For Python:
```python
import asyncio
from src.websocket_client.autocure_handler import AutoCureHandler
import traceback

handler = AutoCureHandler(
    server_url="ws://localhost:9292",
    token="your_jwt_token_from_dashboard"
)

@handler.on('analysis_complete')
async def on_fix(report):
    print(f"Fix ready! Confidence: {report['confidence_score']}%")

await handler.connect()

# In your error handler:
try:
    result = 1 / 0
except Exception as e:
    await handler.send({
        'type': 'error',
        'error_type': type(e).__name__,
        'message': str(e),
        'traceback': traceback.format_exc(),
        'source': 'app.py'
    })
```

For JavaScript:
```javascript
const { AutoCureHandler } = require('./src/websocket_client/autocure_handler.js');

const handler = new AutoCureHandler({
    serverUrl: 'ws://localhost:9292',
    token: 'your_jwt_token_from_dashboard'
});

handler.on('analysis_complete', (report) => {
    console.log(`Fix ready! Confidence: ${report.confidence_score}%`);
});

await handler.connect();

// In your Express error handler:
app.use((err, req, res, next) => {
    handler.send({
        type: 'error',
        error_type: err.name,
        message: err.message,
        source: err.stack.split('\n')[1].trim(),
        stack_trace: err.stack
    });
});
```

#### Option B: Demo Service (Testing)

```bash
cd demo_service
npm install
node server.js
# Server on http://localhost:4000
# POST http://localhost:4000/api/calculate with {"a": 5, "b": 0}
# This triggers a division-by-zero error
```

#### Option C: Manual Testing (Curl)

```bash
curl -X POST http://localhost:9292/api/error \
  -H "Authorization: Bearer your_jwt_token" \
  -H "Content-Type: application/json" \
  -d '{
    "error_type": "TypeError",
    "message": "Cannot read property x of undefined",
    "traceback": "at line 42 in app.js",
    "source": "app.js"
  }'
```

### 3. Monitor Analysis in Real-time

Once logs start flowing:

1. **Dashboard Home** — See live connection indicator (green = connected)
2. **Logs Tab** — All incoming errors appear in real-time
3. **Notice the "Analyzer Running" badge** — AutoCure is analyzing your error
4. **Reports Tab** — As analysis completes, reports appear here with confidence scores

### 4. Review the Full Report

Click any report in the **Reports** tab:

- **Summary** — Error type, message, and confidence score
- **Root Cause** — AI's analysis with AST trace showing path to error
- **AST Visualization** — Interactive tree of the error location
- **Proposed Fix** — Code patch with risk level and test cases
- **Side Effects** — Potential impacts of the fix
- **Source Code** — Original code side-by-side with fix

### 5. Email Notifications

Configure SMTP in `.env` for email reports:

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # NOT your Gmail password; use app-specific password
RECIPIENT_EMAIL=team@example.com
```

Each completed analysis sends:
- HTML email with error summary + fix proposal
- Link to interactive report dashboard
- Confidence score and risk assessment

### 7. Advanced: Multi-Turn Analysis Conversation

For complex errors, AutoCure can run multiple analysis passes with adjusted parameters:

```python
# This happens automatically if confidence < 75%
# Second pass increases:
# - Error replication iterations
# - Code exploration depth
# - Multi-agent discussion rounds
# Result: Higher confidence or more detailed explanation
```

See [WORKFLOW.md](docs/WORKFLOW.md) for detailed workflow diagrams.

### 8. Troubleshooting

| Issue | Solution |
|-------|----------|
| WebSocket connection refused | Check server is running (`python src/main.py`) and port 9292 is open |
| "Unauthorized" on send | Verify JWT token is current; re-login to get fresh token |
| Analysis takes too long | Large codebases take longer (2-5 min typical); check AI provider rate limits |
| Email not sending | Verify SMTP credentials, check console logs for detailed error |
| Report shows low confidence | Error may be rare; multi-agent discussion will run automatically |

---

## GitHub Webhook Integration

AutoCure can receive GitHub webhook events for automatic PR reviews and push-triggered analysis.

### Setup

1. In your GitHub repository, go to **Settings > Webhooks > Add webhook**.
2. Set the payload URL to `https://your-server.com/api/v1/webhook/github`.
3. Set content type to `application/json`.
4. Set the webhook secret (must match `GITHUB_WEBHOOK_SECRET` in `.env`).
5. Select events: **Pull requests** and **Pushes**.

### Behavior

- **Pull Request opened/synchronized** — Triggers AI code review. Results are posted as PR review comments and sent via email.
- **Push to default branch** — Triggers repository sync and optional re-analysis.

---

## Email Reports

AutoCure sends two types of HTML email reports:

### High Confidence Report (score >= 75%)
Contains error summary, root-cause analysis with AST trace, fix proposals with code diffs, edge test cases, and a link to the full interactive report.

### Low Confidence Report (score < 75%)
Contains the same analysis with a warning banner and recommendation for manual investigation, plus divergent findings from the multi-agent analysis.

### Code Review Report
Sent after PR review — includes per-file comments, overall assessment (approve / request changes / comment), and AST analysis insights.

All standalone reports (viewed in browser) use **Phosphor Icons** and a dark theme with interactive collapsible AST trees. Email versions use inline HTML entities for maximum compatibility.

---

## Demo Service

The `demo_service/` directory contains a Node.js Express server with intentional bugs for testing:

| Endpoint | Bug |
|----------|-----|
| `POST /api/user` | Undefined property access |
| `POST /api/items` | Array index out of bounds |
| `POST /api/calculate` | Division by zero |
| `POST /api/profile` | Null property access |
| `POST /api/config` | JSON parse error |

```bash
cd demo_service
npm install
node server.js    # Starts on port 4000, auto-connects to AutoCure
```

---

## Project Structure

```
SelfHealer/
├── src/
│   ├── main.py                    # FastAPI application (routes, WebSocket, middleware)
│   ├── config.py                  # Pydantic configuration models
│   ├── database/
│   │   ├── schema.sql             # PostgreSQL schema (users, reports, repos)
│   │   ├── db_service.py          # Async PostgreSQL operations
│   │   └── redis_service.py       # Redis caching and sessions
│   ├── services/
│   │   ├── ai_analyzer.py         # AutoGen multi-agent AI analyzer
│   │   ├── ast_service.py         # Tree-sitter AST parsing service
│   │   ├── ast_trace_service.py   # AST error path tracing + cross-file refs
│   │   ├── confidence_validator.py# Iterative confidence scoring
│   │   ├── email_service.py       # HTML email + standalone report generation
│   │   ├── error_replicator.py    # Error reproduction engine
│   │   ├── github_service.py      # Git clone/pull, PR diff fetching
│   │   └── log_analyzer.py        # Log pattern matching + error extraction
│   ├── templates/                 # Jinja2 HTML templates (dashboard pages)
│   ├── static/                    # CSS, JS, and built React visualizer
│   ├── utils/
│   │   ├── models.py              # Pydantic data models (AnalysisResult, etc.)
│   │   └── logger.py              # Logging configuration
│   └── websocket_client/          # Client snippets (Python, JS)
├── Visualizer/
│   └── AiHealingSystem/           # React 19 + Vite AST visualizer source
│       ├── src/
│       │   ├── App.jsx            # Main app (file browser, AST viewer, code panel)
│       │   └── components/        # TreeVisualization, CodePanel, AstTree
│       └── package.json
├── demo_service/                  # Node.js demo with intentional bugs
│   ├── server.js
│   └── tests/
├── docs/
│   ├── ARCHITECTURE.md
│   └── WORKFLOW.md
├── requirements.txt               # Python dependencies
├── package.json                   # Root package scripts
└── README.md
```

---

## Supported Languages

AutoCure uses tree-sitter-languages for AST parsing. The following languages are supported:

| Language | Extensions |
|----------|-----------|
| Python | `.py` |
| JavaScript | `.js`, `.mjs`, `.cjs` |
| TypeScript | `.ts` |
| TSX | `.tsx` |
| JSX | `.jsx` |
| Java | `.java` |
| C | `.c`, `.h` |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp` |
| C# | `.cs` |
| Go | `.go` |
| Rust | `.rs` |
| Ruby | `.rb` |
| PHP | `.php` |
| Swift | `.swift` |
| Kotlin | `.kt`, `.kts` |
| Scala | `.scala` |
| R | `.r`, `.R` |
| Lua | `.lua` |
| Bash | `.sh`, `.bash` |
| HTML | `.html`, `.htm` |
| CSS | `.css` |
| SQL | `.sql` |
| YAML | `.yaml`, `.yml` |
| TOML | `.toml` |
| Haskell | `.hs` |
| Elixir | `.ex`, `.exs` |

---

## End-to-End Testing

A complete E2E test validates the entire AutoCure workflow from error detection to fix proposal:

### Prerequisites

- Python 3.10+ with virtual environment activated
- Node.js 18+ installed
- `.env` configured with AI provider credentials

### Test Scenario

1. **Register a test user** on the dashboard
2. **Connect a demo repository**
3. **Trigger an intentional error** via the demo service
4. **Monitor real-time analysis** on the dashboard
5. **Verify fix proposal** is generated and shown in reports
6. **Check email report** (if SMTP configured)
7. **Validate GitHub branch** creation (if GitHub token configured)

### Running the Test (Terminal 1: Server)

```bash
# Activate venv
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Start AutoCure server
python src/main.py
# Server running on http://localhost:9292
```

### Running the Test (Terminal 2: Demo Service)

```bash
cd demo_service
npm install
node server.js
# Demo service on http://localhost:4000
```

### Running the Test (Terminal 3: Client / Automation)

#### Manual Test

1. **Register User**:
   - Open `http://localhost:9292/signup`
   - Create account (e.g., username: `testuser`, password: `test123`)

2. **Register Repository**:
   - Go to Dashboard → Connections tab
   - Paste repository URL: `https://github.com/mihir0209/Self-Healer.git`
   - Submit

3. **Trigger Error**:
   ```bash
   # Terminal 3: Trigger division-by-zero error
   curl -X POST http://localhost:4000/api/calculate \
     -H "Content-Type: application/json" \
     -d '{"a": 10, "b": 0}'
   ```

4. **Monitor Dashboard**:
   - Go to `http://localhost:9292`
   - Watch **Logs** tab for the error
   - Watch **Reports** tab for analysis result (takes 1-3 minutes)

5. **Inspect Report**:
   - Click the report in **Reports** tab
   - Verify:
     - Error type is `ZeroDivisionError`
     - Confidence score > 75%
     - Fix proposal shows proper validation check
     - AST visualization highlights the error line

### What the Test Validates

| Step | Validates |
|------|-----------|
| **Registration** | User auth, workspace creation |
| **Repository** | Git clone, file parsing, language detection |
| **Error Trigger** | WebSocket connection, log ingestion |
| **Analysis** | AST parsing, AI analyzer, multi-agent discussion |
| **Report Gen** | HTML rendering, confidence scoring |
| **Email** | SMTP configuration, HTML template |
| **Git Branch** | GitHub API, branch creation, commit |

### Debugging Failed Test

| Issue | Check |
|-------|-------|
| Server won't start | Port 9292 already in use? Check `netstat` or restart computer |
| Demo service error | Node.js 18+ installed? Run `node --version` |
| Analysis times out | AI provider rate limit? Check Groq/Cerebras console, try reducing requests |
| WebSocket connection fails | Firewall blocking localhost:9292? Check Windows Defender |
| Email not sent | SMTP credentials correct? Check `.env` has `SMTP_PASSWORD` (not Gmail password) |
| GitHub branch not created | Is `GITHUB_TOKEN` in `.env`? Is the test repo your own? |

---

## Security

- **Transport** — TLS 1.3 / WSS for all connections in production.
- **Authentication** — JWT tokens (HMAC-SHA256) with configurable expiry.
- **Password Storage** — bcrypt hashing with automatic salt.
- **GitHub Tokens** — Encrypted at rest (pgcrypto).
- **Tenant Isolation** — Separate file system workspaces and Redis namespaces per user.
- **Rate Limiting** — Per-user limits on log ingestion, PR reviews, and analysis triggers.
- **Input Validation** — Pydantic models for all API inputs; file size limits on uploads.

---

## License

MIT License — see `LICENSE` for details.
