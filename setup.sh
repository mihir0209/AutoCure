#!/bin/bash
# Self-Healing System - Unix/Mac Setup Script
# Run this script to set up the development environment

echo "==============================================="
echo "  Self-Healing System - Setup"
echo "==============================================="
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python not found. Please install Python 3.10+"
    exit 1
fi
echo "[OK] Python found: $(python3 --version)"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Please install Node.js 18+"
    exit 1
fi
echo "[OK] Node.js found: $(node --version)"

# Check Git
if ! command -v git &> /dev/null; then
    echo "[ERROR] Git not found. Please install Git"
    exit 1
fi
echo "[OK] Git found: $(git --version)"

echo
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo
echo "Creating .env file from template..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[OK] .env file created - please edit it with your API keys"
else
    echo "[SKIP] .env file already exists"
fi

echo
echo "Initializing Git repository..."
if [ ! -d .git ]; then
    git init
    git add .
    git commit -m "Initial commit"
    echo "[OK] Git repository initialized"
else
    echo "[SKIP] Git repository already exists"
fi

echo
echo "==============================================="
echo "  Setup Complete!"
echo "==============================================="
echo
echo "Next steps:"
echo "  1. Edit .env with your Groq/Cerebras API key"
echo "  2. Configure email settings in .env"
echo "  3. Run: source venv/bin/activate"
echo "  4. Run: python quickstart.py"
echo
