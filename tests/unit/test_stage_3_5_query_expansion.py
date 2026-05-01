"""Stage 3.5 — LLM Query Expansion unit tests.

Tests follow TDD order: each test targets one behaviour, watches it fail
before implementation, then implementation makes it green.
"""
from unittest.mock import MagicMock

import pytest

from code.llm_client import LLMClient, RowBudget


# ---------------------------------------------------------------------------
# Helper — build a mock LLMClient whose complete_json() returns ``response``.
# Pass response=None to simulate API failure (returns None).
# ---------------------------------------------------------------------------

def _mock_llm(response: dict | None) -> LLMClient:
    """Return a MagicMock LLMClient whose complete_json() returns ``response``."""
    client = MagicMock(spec=LLMClient)
    client.complete_json.return_value = response
    return client


# ---------------------------------------------------------------------------
# 1. domain == 'none' → no LLM call, empty expansion, source = skipped-no-domain
# ---------------------------------------------------------------------------

def test_domain_none_skips_llm_and_returns_empty():
    """When domain is 'none', expand_query must not call the LLM at all."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"keywords": "team member deactivate", "confidence": 0.9})
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Employee leaving",
        issue_redacted="An employee left, remove their account",
        domain="none",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == ""
    assert info["source"] == "skipped-no-domain"
    mock_client.complete_json.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Budget exhausted → empty expansion, source = budget-exhausted
# ---------------------------------------------------------------------------

def test_budget_exhausted_returns_empty():
    """When RowBudget is empty, expand_query must not call LLM."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"keywords": "team member", "confidence": 0.9})
    budget = RowBudget(max_attempts=0)

    expansion, info = expand_query(
        subject="Employee leaving",
        issue_redacted="Remove employee access",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == ""
    assert info["source"] == "budget-exhausted"
    mock_client.complete_json.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Successful LLM call → keywords returned, source = llm
# ---------------------------------------------------------------------------

def test_successful_llm_returns_keywords():
    """Happy path: LLM returns valid JSON with keywords."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"keywords": "team member deactivate user", "confidence": 0.9})
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Employee leaving",
        issue_redacted="An employee left. How do I remove their access?",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == "team member deactivate user"
    assert info["source"] == "llm"
    assert info["keywords"] == "team member deactivate user"
    assert info["confidence"] == 0.9
    mock_client.complete_json.assert_called_once()


# ---------------------------------------------------------------------------
# 4. LLM returns None (timeout / API error) → empty expansion, source shows error
# ---------------------------------------------------------------------------

def test_llm_none_returns_empty_predict_failed():
    """When LLM returns None (any error), expand_query must not raise."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm(None)
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Remove user",
        issue_redacted="Remove interviewer from account",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == ""
    assert info["source"] in ("predict-failed", "load-failed", "malformed")


# ---------------------------------------------------------------------------
# 5. LLM raises APITimeoutError → empty expansion, no exception propagated
# ---------------------------------------------------------------------------

def test_llm_timeout_returns_empty():
    """APITimeoutError must be caught; expand_query returns empty string."""
    from anthropic import APITimeoutError
    from code.query_expansion import expand_query

    mock_client = MagicMock(spec=LLMClient)
    mock_client.complete_json.side_effect = APITimeoutError(request=MagicMock())
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Interview candidate inactive",
        issue_redacted="Candidate hasn't responded",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == ""
    assert info["source"] in ("predict-failed", "load-failed")


# ---------------------------------------------------------------------------
# 6. LLM returns JSON without 'keywords' field → empty expansion, malformed
# ---------------------------------------------------------------------------

def test_missing_keywords_field_returns_empty():
    """Response missing 'keywords' key should yield empty expansion."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"confidence": 0.9})  # no 'keywords' key
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Remove user",
        issue_redacted="Remove interviewer",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == ""
    assert info["source"] == "malformed"


# ---------------------------------------------------------------------------
# 7. Confidence < 0.5 still returns keywords (BM25 weighs; we don't gate)
# ---------------------------------------------------------------------------

def test_low_confidence_still_returns_keywords():
    """Low confidence does not suppress the expansion string."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"keywords": "user team deactivate", "confidence": 0.3})
    budget = RowBudget(max_attempts=5)

    expansion, info = expand_query(
        subject="Remove employee",
        issue_redacted="Employee left the company",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert expansion == "user team deactivate"
    assert info["confidence"] == 0.3
    assert info["source"] == "llm"


# ---------------------------------------------------------------------------
# 8. raw_response in info_dict is truncated to ≤ 500 chars for trace safety
# ---------------------------------------------------------------------------

def test_raw_response_truncated_to_500():
    """info_dict['raw_response'] must be ≤ 500 chars (for trace logs)."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm({"keywords": "user team", "confidence": 0.8})
    budget = RowBudget(max_attempts=5)

    _, info = expand_query(
        subject="Remove user",
        issue_redacted="Employee left",
        domain="hackerrank",
        llm_client=mock_client,
        budget=budget,
    )

    assert "raw_response" in info
    assert len(info["raw_response"]) <= 500


# ---------------------------------------------------------------------------
# 9. info_dict always contains all required keys regardless of outcome
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("domain,llm_response,budget_attempts", [
    ("none", {"keywords": "ignored", "confidence": 0.9}, 5),
    ("hackerrank", None, 5),
    ("hackerrank", {"keywords": "team member", "confidence": 0.9}, 0),
])
def test_info_dict_always_has_required_keys(domain, llm_response, budget_attempts):
    """info_dict must always have source, keywords, confidence, raw_response."""
    from code.query_expansion import expand_query

    mock_client = _mock_llm(llm_response)
    budget = RowBudget(max_attempts=budget_attempts)

    _, info = expand_query(
        subject="Test",
        issue_redacted="Test issue",
        domain=domain,
        llm_client=mock_client,
        budget=budget,
    )

    for key in ("source", "keywords", "confidence", "raw_response"):
        assert key in info, f"Missing key '{key}' in info_dict"
