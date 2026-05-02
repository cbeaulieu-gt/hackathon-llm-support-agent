"""Stage 7 — Response Generation.

Spec: docs/PLAN.md Rev 5 §11 (prompt) + Rev 5.1 §4 (defense-in-depth secret
redaction). Sends ``Issue_redacted`` to the LLM (DiD #1) and post-processes
``response`` through ``SECRET_PATTERNS`` before write (DiD #2).

Change B (safety-tuning): when ``justification`` contains
"action_impossible_with_corpus" a framing hint is prepended to the user
message so the LLM knows to acknowledge the impossible action and redirect
to the documented legitimate path, rather than simply refusing or hallucinating
that it performed the action.
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


def _build_user_msg(
    cleaned: dict,
    top_k_docs: list,
    action_impossible_context: bool = False,
) -> str:
    """Compose the Stage 7 user message: Subject + Issue + snippet blocks.

    Each snippet is preceded by ``[path: ...]`` so the LLM can cite paths
    that match the spec's "cited_doc_paths" rule.

    Args:
        cleaned: Pre-processed row dict with Issue/Subject/Company keys.
        top_k_docs: Ranked retrieval results from Stage 4.
        action_impossible_context: When True (Change B carve-out), prepend a
            framing hint telling the LLM to acknowledge the impossible action
            and redirect via the documented legitimate path.

    Returns:
        Formatted user-turn string for the Stage 7 LLM call.
    """
    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    parts = []
    if action_impossible_context:
        parts.append(
            "[FRAMING HINT: The user has requested an action that the "
            "support agent cannot perform directly (e.g. restoring account "
            "access, changing a score, banning a merchant). Frame your "
            "response as: 'I cannot perform [the action], but the "
            "documentation describes how you can [achieve it via the "
            "legitimate path]:…'. Use ONLY information from the snippets "
            "below.]"
        )
        parts.append("")
    parts += [
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
    justification: str = "",
) -> str:
    """Returns the final ``response`` string (already redacted).

    Args:
        cleaned: Pre-processed row dict.
        flags: Stage 1 + later flag dict.
        top_k_docs: Ranked retrieval results.
        status: Stage 6 decision ('replied' | 'escalated').
        request_type: Stage 3 classification.
        llm: LLM client for the completion call.
        budget: Per-row token budget tracker.
        justification: Stage 6 justification string; used to detect the
            ``action_impossible_with_corpus`` carve-out so the framing hint
            can be injected into the user message.
    """
    if status == "escalated":
        return "Escalate to a human"

    if request_type == "invalid":
        if flags.get("oos_pleasantry"):
            return "Happy to help"
        return "I am sorry, this is out of scope from my capabilities."

    action_ctx = "action_impossible_with_corpus" in justification
    user_msg = _build_user_msg(cleaned, top_k_docs, action_impossible_context=action_ctx)
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
