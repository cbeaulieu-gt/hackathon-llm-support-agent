"""Project-wide constants. Reads from environment with sensible defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# LLM
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
LLM_MAX_ATTEMPTS_PER_ROW = int(os.environ.get("LLM_MAX_ATTEMPTS_PER_ROW", "5"))
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_S", "30"))

# BM25
BM25_K1 = float(os.environ.get("BM25_K1", "1.5"))
BM25_B = float(os.environ.get("BM25_B", "0.75"))
BM25_TOP_K = int(os.environ.get("BM25_TOP_K", "5"))
BM25_SCORE_THRESHOLD = float(os.environ.get("BM25_SCORE_THRESHOLD", "2.0"))

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"
SUPPORT_TICKETS_DIR = REPO_ROOT / "support_tickets"


def require_api_key() -> str:
    """Fail-fast at startup if the API key is missing."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY env var is required. "
            "Copy .env.example to .env and set it."
        )
    return ANTHROPIC_API_KEY
