"""Stage 7 — Response Generation.

Spec: docs/PLAN.md Rev 5 §11 (prompt) + Rev 5.1 §4 (defense-in-depth secret
redaction). Sends ``Issue_redacted`` to the LLM (DiD #1) and post-processes
``response`` through ``SECRET_PATTERNS`` before write (DiD #2).
"""
import re

from .llm_client import LLMClient, RowBudget
from .prompts import STAGE_7_SYSTEM

SECRET_PATTERNS = [
    re.compile(r"sk-ant-api03-[A-Za-z0-9_-]+"),
    re.compile(r"cs_live_\w+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_.+\-/=]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]

MIN_CONFIDENCE = 0.6


def redact_secrets(text: str) -> str:
    """Replace secret-shaped tokens with ``[REDACTED]``."""
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def _build_user_msg(cleaned: dict, top_k_docs: list) -> str:
    """Compose the Stage 7 user message: Subject + Issue + snippet blocks.

    Each snippet is preceded by ``[path: ...]`` so the LLM can cite paths
    that match the spec's "cited_doc_paths" rule.
    """
    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    parts = [
        f"Subject: {cleaned.get('Subject', '')}",
        f"Issue: {issue}",
        "",
        "Documentation snippets:",
    ]
    for d in top_k_docs:
        parts.append(f"[path: {d['path']}]")
        parts.append(d.get("snippet", ""))
        parts.append("")
    return "\n".join(parts)


def generate_response(
    cleaned: dict,
    flags: dict,
    top_k_docs: list,
    status: str,
    request_type: str,
    llm: LLMClient,
    budget: RowBudget,
) -> str:
    """Returns the final ``response`` string (already redacted)."""
    if status == "escalated":
        return "Escalate to a human"

    if request_type == "invalid":
        if flags.get("oos_pleasantry"):
            return "Happy to help"
        return "I am sorry, this is out of scope from my capabilities."

    user_msg = _build_user_msg(cleaned, top_k_docs)
    result = llm.complete_json(STAGE_7_SYSTEM, user_msg, budget, max_tokens=1024)
    if not result:
        return "Escalate to a human"
    if result.get("refused"):
        return "Escalate to a human"
    if result.get("confidence", 0) < MIN_CONFIDENCE:
        return "Escalate to a human"

    response = (result.get("response") or "").strip()
    if not response:
        return "Escalate to a human"

    cited = set(result.get("cited_doc_paths") or [])
    valid_paths = {d["path"] for d in top_k_docs}
    if cited and not cited.issubset(valid_paths):
        # Hallucinated citation — escalate per Rev 4 §1 Stage 7 row
        return "Escalate to a human"

    return redact_secrets(response)
