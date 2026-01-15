# Self-Healing Software System

An AI-driven system for automated error detection, analysis, and resolution in software applications.

## 🚀 Features

- **Automatic Log Monitoring**: Watches application logs for errors and warnings
- **AI-Powered Analysis**: Uses Groq or Cerebras LLMs to analyze errors and generate fixes
- **Test-Driven Fixes**: Generates and runs tests to validate fixes before applying
- **Git Integration**: Creates branches with tested fixes for review
- **Email Notifications**: Sends detailed reports to administrators

## 📋 Prerequisites

- Python 3.10+
- Node.js 18+
- Git
- API key for Groq or Cerebras

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

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

4. **Initialize Git repository (if not already)**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

## ⚙️ Configuration

Edit the `.env` file with your settings:

```env
# AI Provider (groq or cerebras)
AI_PROVIDER=groq
GROQ_API_KEY=your_key_here

# Email settings (Gmail with App Password)
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_app_password
ADMIN_EMAIL=admin@example.com
```

## 🏃 Running the System

```bash
# Start the self-healing system
python src/main.py
```

The system will:
1. Start the demo Node.js service
2. Monitor logs for errors
3. Automatically detect and analyze errors
4. Generate and test fixes
5. Create git branches with working fixes
6. Send email notifications

## 📁 Project Structure

```
self-healing-system/
├── src/
│   ├── main.py              # Main orchestrator
│   ├── config.py            # Configuration management
│   ├── agents/
│   │   ├── ai_client.py     # AI API client (Groq/Cerebras)
│   │   └── healing_agent.py # Main healing logic
│   ├── subprocesses/
│   │   ├── log_watcher.py   # Log monitoring
│   │   ├── error_processor.py # Error analysis
│   │   ├── git_handler.py   # Git operations
│   │   └── email_notifier.py # Email notifications
│   └── utils/
│       ├── logger.py        # Logging utilities
│       └── models.py        # Data models
├── demo_service/
│   ├── server.js            # Demo Node.js server (with bugs)
│   └── tests/               # Test files
├── requirements.txt         # Python dependencies
├── .env.example            # Environment template
└── README.md               # This file
```

## 🔧 How It Works

1. **Log Watcher** monitors the target service's log file
2. When an error is detected, **Error Processor** traces it to source code
3. **Healing Agent** uses AI to:
   - Analyze the error and root cause
   - Generate a fix proposal
   - Create test cases for the fix
4. Tests are run in an isolated environment
5. If tests pass, **Git Handler** creates a branch with the fix
6. **Email Notifier** sends a report to the admin

## 🧪 Demo

The `demo_service/server.js` contains intentional bugs that trigger errors:
- Accessing properties of undefined
- Array index out of bounds
- Division by zero
- Undefined callbacks
- Invalid JSON parsing

Run the system and watch it automatically detect and fix these errors!

## 📊 Supported AI Providers

### Groq
- Models: llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768
- Get API key: https://console.groq.com/keys

### Cerebras
- Models: llama3.1-8b, llama3.1-70b
- Get API key: https://cloud.cerebras.ai/

## 🔐 Security Notes

- Use Gmail App Passwords, not your actual password
- Never commit `.env` files to version control
- API keys should be kept secure

## 📝 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Support

For issues and feature requests, please create a GitHub issue.
