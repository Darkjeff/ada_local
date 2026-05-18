"""Pytest configuration — ensures project root is on sys.path."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
