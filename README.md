# AutoCure — Self-Healing Software System v2.0

An AI-driven **error detection, root-cause analysis, and fix proposal** platform. AutoCure monitors your production applications via WebSocket, analyzes errors using multi-language AST parsing, validates findings through iterative confidence scoring, and delivers rich HTML reports with actionable fix proposals.

> **Note:** AutoCure **proposes fixes only** — it does not automatically apply changes to your codebase.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Dashboard](#dashboard)
- [AST Visualizer](#ast-visualizer)
- [Integrating with Your Application](#integrating-with-your-application)
- [API Reference](#api-reference)
- [GitHub Webhook Integration](#github-webhook-integration)
- [Email Reports](#email-reports)
- [Demo Service](#demo-service)
- [Project Structure](#project-structure)
- [Supported Languages](#supported-languages)
- [Security](#security)
- [License](#license)

---

## Features

- **Real-time Log Streaming** — WebSocket-based log ingestion from production applications with live dashboard feed.
- **Multi-Agent AI Analysis** — Microsoft AutoGen framework with `llama-3.3-70b` (via Groq or Cerebras) for intelligent error classification and root-cause analysis.
- **AST-Based Code Understanding** — Tree-sitter parsing across 26+ languages with cross-file reference resolution.
- **Interactive AST Visualization** — Browser-based React visualizer with drag, zoom, expand/collapse, and code-to-tree navigation.
- **Iterative Confidence Validation** — Multiple analysis passes with payload variation to score fix confidence.
- **Fix Proposals with Risk Assessment** — AI-generated code patches with risk level, side effects, and edge test cases.
- **PR Code Review** — Automated pull request review with per-file comments and overall assessment.
- **Rich HTML Reports** — Standalone dark-themed reports with interactive AST trees, confidence charts, and collapsible sections.
- **Email Notifications** — Detailed HTML email reports with AST trace, proposals, and direct links to full reports.
- **Web Dashboard** — FastAPI + Jinja2 dashboard with live connections, log viewer, report browser, and integration guides.
- **Multi-Tenant** — Per-user workspace isolation with storage quotas and JWT authentication.

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
| **AI** | Microsoft AutoGen 0.7+, llama-3.3-70b (Groq / Cerebras) |
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

### 3. Set up PostgreSQL

```bash
createdb selfhealer
psql selfhealer < src/database/schema.sql
```

### 4. Start Redis

```bash
redis-server
```

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values (see [Configuration](#configuration)).

### 6. (Optional) Install demo service

```bash
cd demo_service && npm install && cd ..
```

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
| `http://localhost:8000/` | Dashboard (login required) |
| `http://localhost:8000/login` | Authentication page |
| `http://localhost:8000/visualizer` | AST Visualizer (React SPA) |
| `http://localhost:8000/health` | Health check (JSON) |

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
# ~50 lines — see src/websocket_client/python_client.py
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
