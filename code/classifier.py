"""Stage 3 — Request-Type Classification.

Short-circuits to ``invalid`` for OOS pleasantries and empty issues; otherwise
asks the LLM with structured output; falls back to keyword heuristics on
failure or invalid labels.
"""
from .llm_client import LLMClient, RowBudget
from .prompts import STAGE_3_SYSTEM

VALID_REQUEST_TYPES = {"bug", "product_issue", "feature_request", "invalid"}


def _keyword_heuristic(text: str) -> str:
    """Last-resort request-type classifier."""
    low = text.lower()
    if any(
        kw in low
        for kw in (
            "down", "broken", "failing", "not working", "stopped", "crashed",
            "error", "bug",
        )
    ):
        return "bug"
    if any(
        kw in low
        for kw in (
            "feature", "would be nice", "add support", "please add", "wishlist",
        )
    ):
        return "feature_request"
    if any(kw in low for kw in ("thanks", "hello ", "hi ", "help me find")) and len(low) < 50:
        return "invalid"
    return "product_issue"


def classify_request_type(
    cleaned: dict, flags: dict, llm: LLMClient, budget: RowBudget
) -> tuple[str, str]:
    """Returns ``(request_type, source)`` where source ∈ {'short-circuit', 'llm', 'fallback'}."""
    if flags.get("oos_pleasantry") or flags.get("empty_issue"):
        return "invalid", "short-circuit"

    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    user_msg = f"Subject: {cleaned.get('Subject', '')}\nIssue: {issue}"
    result = llm.complete_json(STAGE_3_SYSTEM, user_msg, budget, max_tokens=128)
    if result and result.get("request_type") in VALID_REQUEST_TYPES:
        return result["request_type"], "llm"

    text = cleaned.get("Subject", "") + " " + cleaned.get("Issue", "")
    return _keyword_heuristic(text), "fallback"
