"""Entry-point shim for AGENTS.md §6.1 contract.

Real orchestration lives in code/main.py:run_on_csv().
"""
from .main import run_on_csv as run

__all__ = ["run"]
