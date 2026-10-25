"""
Module execution entry point for python -m src.healing
"""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
