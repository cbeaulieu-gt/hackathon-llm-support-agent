"""Stage 2 — Domain Routing.

Trusts the Company field when set; otherwise calls the LLM with structured
output; falls back to keyword heuristics on LLM failure or low confidence.
"""
from .llm_client import LLMClient, RowBudget
from .prompts import STAGE_2_SYSTEM

VALID_DOMAINS = {"hackerrank", "claude", "visa", "none"}
MIN_CONFIDENCE = 0.6


def _keyword_heuristic(text: str) -> str:
    """Last-resort domain classifier. Counts brand keywords; ties → 'none'."""
    low = text.lower()
    counts = {
        "hackerrank": (
            low.count("hackerrank") + low.count("interview") + low.count("test ")
            + low.count("score") + low.count("leaderboard")
        ),
        "claude": (
            low.count("claude") + low.count("anthropic") + low.count("chatbot")
        ),
        "visa": (
            low.count("visa") + low.count(" card ") + low.count("payment")
            + low.count("merchant")
        ),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "none"


def route_domain(
    cleaned: dict, flags: dict, llm: LLMClient, budget: RowBudget
) -> tuple[str, str]:
    """Returns ``(domain, source)`` where source ∈ {'company-field', 'llm', 'fallback'}."""
    company = cleaned.get("Company", "").strip().lower()
    if company in {"hackerrank", "claude", "visa"}:
        return company, "company-field"

    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    user_msg = f"Subject: {cleaned.get('Subject', '')}\nIssue: {issue}"
    result = llm.complete_json(STAGE_2_SYSTEM, user_msg, budget, max_tokens=128)
    if result and result.get("domain") in VALID_DOMAINS:
        if result.get("confidence", 0) >= MIN_CONFIDENCE:
            return result["domain"], "llm"
        # Low confidence — escalate via 'none'
        return "none", "llm-low-confidence"

    # Fallback: keyword heuristic
    text = cleaned.get("Subject", "") + " " + cleaned.get("Issue", "")
    return _keyword_heuristic(text), "fallback"
