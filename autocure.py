#!/usr/bin/env python3
"""
AutoCure CLI Top-Level Dispatcher
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from healing.cli import main

if __name__ == "__main__":
    sys.exit(main())
