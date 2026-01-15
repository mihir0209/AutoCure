"""
Quick Start Script for Self-Healing System
Run this script to quickly test the system.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def check_prerequisites():
    """Check if all prerequisites are met"""
    print("=" * 60)
    print("  Self-Healing System - Prerequisites Check")
    print("=" * 60)
    
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 10):
        issues.append(f"Python 3.10+ required, found {sys.version_info.major}.{sys.version_info.minor}")
    else:
        print(f"✓ Python version: {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check for Node.js
    try:
        import subprocess
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Node.js version: {result.stdout.strip()}")
        else:
            issues.append("Node.js not found")
    except FileNotFoundError:
        issues.append("Node.js not found - please install Node.js 18+")
    
    # Check for Git
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Git version: {result.stdout.strip()}")
        else:
            issues.append("Git not found")
    except FileNotFoundError:
        issues.append("Git not found - please install Git")
    
    # Check for .env file
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print("✓ .env file found")
    else:
        issues.append(".env file not found - copy .env.example to .env and configure")
    
    # Check for required packages
    required_packages = ["httpx", "aiofiles", "python-dotenv", "pydantic"]
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✓ Package {package} installed")
        except ImportError:
            issues.append(f"Package {package} not installed - run: pip install -r requirements.txt")
    
    print()
    
    if issues:
        print("⚠️  Issues found:")
        for issue in issues:
            print(f"   • {issue}")
        print()
        return False
    else:
        print("✓ All prerequisites met!")
        return True


async def run_demo():
    """Run the self-healing system"""
    print()
    print("=" * 60)
    print("  Starting Self-Healing System...")
    print("=" * 60)
    print()
    
    try:
        from main import main
        await main()
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"\nError: {e}")
        raise


async def main():
    """Main entry point"""
    print(r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███████╗███████╗██╗     ███████╗    ██╗  ██╗███████╗ █████╗ ║
    ║   ██╔════╝██╔════╝██║     ██╔════╝    ██║  ██║██╔════╝██╔══██╗║
    ║   ███████╗█████╗  ██║     █████╗█████╗███████║█████╗  ███████║║
    ║   ╚════██║██╔══╝  ██║     ██╔══╝╚════╝██╔══██║██╔══╝  ██╔══██║║
    ║   ███████║███████╗███████╗██║         ██║  ██║███████╗██║  ██║║
    ║   ╚══════╝╚══════╝╚══════╝╚═╝         ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝║
    ║                                                               ║
    ║           AI-Driven Self-Healing Software System              ║
    ║                     Quick Start Script                        ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Check prerequisites
    if not await check_prerequisites():
        print("\nPlease fix the issues above before running the system.")
        print("\nQuick setup commands:")
        print("  1. pip install -r requirements.txt")
        print("  2. cp .env.example .env")
        print("  3. Edit .env with your API keys")
        print("  4. python quickstart.py")
        return
    
    # Ask user to confirm
    print()
    response = input("Start the self-healing system? [Y/n]: ").strip().lower()
    if response in ("", "y", "yes"):
        await run_demo()
    else:
        print("Cancelled.")


if __name__ == "__main__":
    asyncio.run(main())
