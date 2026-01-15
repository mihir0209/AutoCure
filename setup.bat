@echo off
REM Self-Healing System - Windows Setup Script
REM Run this script to set up the development environment

echo ===============================================
echo   Self-Healing System - Windows Setup
echo ===============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python found

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+
    pause
    exit /b 1
)
echo [OK] Node.js found

REM Check Git
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not found. Please install Git
    pause
    exit /b 1
)
echo [OK] Git found

echo.
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Creating .env file from template...
if not exist .env (
    copy .env.example .env
    echo [OK] .env file created - please edit it with your API keys
) else (
    echo [SKIP] .env file already exists
)

echo.
echo Initializing Git repository...
if not exist .git (
    git init
    git add .
    git commit -m "Initial commit"
    echo [OK] Git repository initialized
) else (
    echo [SKIP] Git repository already exists
)

echo.
echo ===============================================
echo   Setup Complete!
echo ===============================================
echo.
echo Next steps:
echo   1. Edit .env with your Groq/Cerebras API key
echo   2. Configure email settings in .env
echo   3. Run: python quickstart.py
echo.
pause
