"""Root conftest.py - adds project root to sys.path so tests can import core.*"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
