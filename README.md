# Self-Healing Software System v2.0

An AI-powered **error detection and fix proposal** platform that monitors your production applications via WebSocket, analyzes errors using AST parsing, and proposes fixes using LLMs.

> ⚠️ **Important**: This system **proposes fixes only** - it does NOT automatically apply changes to your code.

## 🚀 Features

- **Real-time Log Streaming**: WebSocket-based log ingestion from your production apps
- **AI-Powered Error Detection**: Groq/Cerebras LLMs for intelligent error classification
- **AST-Based Analysis**: Tree-sitter parsing for multi-language code understanding
- **Root Cause Analysis**: Traces errors through code dependencies
- **Fix Proposals**: AI-generated fix suggestions with risk assessment
- **PR Code Review**: Automated code review for pull requests
- **Rich Email Reports**: HTML reports with interactive AST visualizations
- **Multi-Tenant**: Secure isolation per user with storage quotas

## 📋 Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 7+
- Node.js 18+ (for demo service)
- API key for Groq or Cerebras (free tiers available)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/self-healing-system.git
   cd self-healing-system
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set up PostgreSQL**
   ```bash
   # Create database
   createdb selfhealer
   
   # Run schema
   psql selfhealer < src/database/schema.sql
   ```

4. **Set up Redis**
   ```bash
   # Start Redis (varies by OS)
   redis-server
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

## ⚙️ Configuration

Edit the `.env` file:

```env
# AI Provider (groq or cerebras - both have free tiers)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=selfhealer
DB_USER=postgres
DB_PASSWORD=your_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Email (Gmail with App Password)
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
ADMIN_EMAIL=admin@example.com

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
JWT_SECRET=change-this-in-production
```

## 🏃 Running the System

```bash
# Start the FastAPI server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

The server will start with:
- WebSocket endpoint: `ws://localhost:8000/ws/logs/{user_id}`
- REST API: `http://localhost:8000/api/v1/`
- Health check: `http://localhost:8000/health`

## 📡 Integrating with Your App

Add the WebSocket client snippet to your production app:

### Python (~50 lines)
```python
# See src/websocket_client/python_client.py
from selfhealer_client import SelfHealerClient

client = SelfHealerClient(
    server_url="wss://your-server.com/ws/logs",
    user_id="your-user-id",
    auth_token="your-jwt-token"
)
client.start()

# Your app logs are now streamed to Self-Healer
```

### JavaScript/Node.js (~50 lines)
```javascript
// See src/websocket_client/js_client.js
const { SelfHealerClient } = require('./selfhealer_client');

const client = new SelfHealerClient({
    serverUrl: 'wss://your-server.com/ws/logs',
    userId: 'your-user-id',
    authToken: 'your-jwt-token'
});

app.use(client.expressMiddleware());
```

## 📁 Project Structure

```
self-healing-system/
├── src/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration management
│   ├── database/
│   │   ├── schema.sql          # PostgreSQL schema
│   │   ├── db_service.py       # Async database operations
│   │   └── redis_service.py    # Redis caching/sessions
│   ├── services/
│   │   ├── log_analyzer.py     # Error detection engine
│   │   ├── ast_service.py      # AST parsing and analysis
│   │   ├── github_service.py   # Git/GitHub operations
│   │   ├── error_replicator.py # Error replication
│   │   ├── ai_analyzer.py      # Root cause analysis
│   │   └── email_service.py    # Email notifications
│   ├── websocket_client/
│   │   ├── python_client.py    # Python client snippet
│   │   └── js_client.js        # JavaScript client snippet
│   └── utils/
│       └── models.py           # Pydantic data models
├── demo_service/
│   └── server.js               # Demo Node.js server
├── docs/
│   └── ARCHITECTURE.md         # System architecture
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
└── README.md                  # This file
```

## 🔧 How It Works

1. **Your app** sends logs via WebSocket to Self-Healer
2. **Error Detection Engine** identifies errors using patterns + AI
3. **Repo Sync** pulls latest code from your GitHub repo
4. **AST Parser** builds a searchable code structure
5. **Root Cause Analyzer** traces the error through AST
6. **AI (Groq/Cerebras)** generates fix proposals
7. **Email Service** sends rich HTML report with proposed fixes

```
Your App → WebSocket → Error Detection → AST Analysis → AI → Email Report
                              ↓
                         PostgreSQL/Redis
```

## 💾 Storage Tiers

| Feature | Free Tier | Pro Tier (Future) |
|---------|-----------|-------------------|
| Max Repositories | 5 | Unlimited |
| Storage per Repo | 100 MB | 1 GB |
| Logs per Second | 100 | 500 |
| PRs per Hour | 10 | 50 |

## 📊 Supported AI Providers

### Groq (Recommended)
- Free tier: 6,000 requests/day
- Models: `llama-3.3-70b-versatile`
- Get API key: https://console.groq.com/keys

### Cerebras
- Free tier: 10,000 requests/day
- Models: `llama-3.3-70b`
- Get API key: https://cloud.cerebras.ai/

## 🔐 Security

- **Transport**: TLS 1.3 / WSS for all connections
- **Auth**: JWT tokens with HMAC-SHA256 signing
- **Passwords**: bcrypt hashing
- **GitHub Tokens**: Encrypted at rest with pgcrypto
- **Tenant Isolation**: Separate workspaces, Redis namespaces
- **Rate Limiting**: Per-user limits enforced

## 🧪 Demo Service

The `demo_service/server.js` contains intentional bugs:
- POST `/api/user` - undefined property access
- POST `/api/items` - array index out of bounds
- POST `/api/calculate` - division by zero
- POST `/api/profile` - null property access
- POST `/api/config` - JSON parse error

```bash
# Run demo service
cd demo_service
npm install
node server.js
```

## 📝 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws/logs/{user_id}` | WS | Log streaming WebSocket |
| `/api/v1/auth/register` | POST | User registration |
| `/api/v1/auth/login` | POST | User login |
| `/api/v1/repos` | GET/POST | Repository management |
| `/api/v1/repos/{id}/analyze` | POST | Trigger analysis |
| `/api/v1/repos/{id}/review-pr` | POST | Review a PR |
| `/health` | GET | Health check |

## 📧 Support

For issues and feature requests, please create a GitHub issue.

## 📝 License

MIT License - see LICENSE file for details.
