"""Stage 3.5 — LLM Query Expansion.

Bridges the vocabulary gap between user tickets and corpus documents by
asking Claude Sonnet to map user phrasing onto corpus-vocabulary keywords.
The expansion is appended to (never replaces) the BM25 query so that any
failure is a silent no-op rather than a regression.
"""
from __future__ import annotations

import json

from .llm_client import LLMClient, RowBudget
from .prompts import STAGE_3_5_SYSTEM, build_stage_3_5_user_prompt

# Maximum characters kept in raw_response for trace logs.
_RAW_RESPONSE_MAX_CHARS = 500


def expand_query(
    subject: str,
    issue_redacted: str,
    domain: str,
    *,
    llm_client: LLMClient,
    budget: RowBudget,
) -> tuple[str, dict]:
    """Return (expansion_keywords, info_dict) for Stage 3.5 query expansion.

    Calls Claude Sonnet to map user vocabulary onto corpus vocabulary so that
    BM25 retrieval can find the right document even when the user's phrasing
    doesn't match the corpus directly.

    The returned ``expansion_keywords`` is a space-separated string ready to
    be concatenated onto the existing BM25 query.  An empty string is returned
    on any failure so the caller always gets a clean fall-through.

    Args:
        subject: Ticket subject line (may be empty).
        issue_redacted: PII-redacted issue body text.
        domain: Routed domain — one of 'hackerrank', 'claude', 'visa', 'none'.
            If 'none', no LLM call is made (routing already failed; expansion
            cannot help).
        llm_client: Injected LLMClient instance.
        budget: Shared per-row RowBudget.  One unit is consumed on success.

    Returns:
        A 2-tuple ``(expansion_keywords, info_dict)``.

        ``info_dict`` always contains:
        - ``source`` (str): one of 'llm', 'skipped-no-domain',
          'budget-exhausted', 'predict-failed', 'malformed'.
        - ``keywords`` (str): the expansion string (empty on failure).
        - ``confidence`` (float): model confidence (0.0 on failure).
        - ``raw_response`` (str): raw LLM text, truncated to 500 chars.
    """
    if domain == "none":
        return "", _make_info(
            source="skipped-no-domain",
            keywords="",
            confidence=0.0,
            raw="",
        )

    if budget.remaining <= 0:
        return "", _make_info(
            source="budget-exhausted",
            keywords="",
            confidence=0.0,
            raw="",
        )

    user_prompt = build_stage_3_5_user_prompt(subject, issue_redacted, domain)

    try:
        result = llm_client.complete_json(
            STAGE_3_5_SYSTEM,
            user_prompt,
            budget,
            max_tokens=128,
        )
    except Exception:
        return "", _make_info(
            source="predict-failed",
            keywords="",
            confidence=0.0,
            raw="",
        )

    if result is None:
        return "", _make_info(
            source="predict-failed",
            keywords="",
            confidence=0.0,
            raw="",
        )

    raw = _truncate(json.dumps(result), _RAW_RESPONSE_MAX_CHARS)

    if "keywords" not in result:
        return "", _make_info(
            source="malformed",
            keywords="",
            confidence=0.0,
            raw=raw,
        )

    keywords: str = str(result["keywords"]).strip()
    confidence: float = float(result.get("confidence", 0.0))

    return keywords, _make_info(
        source="llm",
        keywords=keywords,
        confidence=confidence,
        raw=raw,
    )


def _make_info(
    source: str,
    keywords: str,
    confidence: float,
    raw: str,
) -> dict:
    """Construct a canonical info_dict with all required keys."""
    return {
        "source": source,
        "keywords": keywords,
        "confidence": confidence,
        "raw_response": raw,
    }


def _truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to at most ``max_chars`` characters."""
    return text[:max_chars]
