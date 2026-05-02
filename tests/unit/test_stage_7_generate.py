"""Stage 7 generation tests."""
from code.generate import (
    TEMPLATED_OOS_RESPONSE,
    finalize_justification,
    generate_response,
    redact_secrets,
)
from code.llm_client import RowBudget
from tests.conftest import fake_llm_default


def test_escalated_short_circuit():
    out = generate_response(
        {"Issue": "x", "Issue_redacted": "x", "Subject": ""},
        {}, [], "escalated", "bug",
        fake_llm_default(), RowBudget(),
    )
    assert out == "Escalate to a human"


def test_invalid_pleasantry_template():
    out = generate_response(
        {"Issue": "thanks", "Issue_redacted": "thanks", "Subject": ""},
        {"oos_pleasantry": True}, [], "replied", "invalid",
        fake_llm_default(), RowBudget(),
    )
    assert "Happy to help" in out


def test_invalid_oos_template():
    out = generate_response(
        {"Issue": "weather?", "Issue_redacted": "weather?", "Subject": ""},
        {}, [], "replied", "invalid",
        fake_llm_default(), RowBudget(),
    )
    assert "out of scope" in out.lower()


def test_grounded_response_returned():
    docs = [
        {
            "path": "data/claude/screen/foo.md",
            "score": 5.0,
            "snippet": "Snippet content.",
        }
    ]
    fake = fake_llm_default(
        canned={
            "generator": {
                "response": "Use feature X.",
                "cited_doc_paths": ["data/claude/screen/foo.md"],
                "confidence": 0.9,
                "refused": False,
                "refusal_reason": "",
            }
        }
    )
    out = generate_response(
        {"Issue": "how do I X?", "Issue_redacted": "how do I X?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert "Use feature X" in out


def test_refused_escalates():
    docs = [{"path": "data/claude/screen/foo.md", "score": 5.0, "snippet": ""}]
    fake = fake_llm_default(
        canned={
            "generator": {
                "response": "",
                "cited_doc_paths": [],
                "confidence": 0.5,
                "refused": True,
                "refusal_reason": "no relevant docs",
            }
        }
    )
    out = generate_response(
        {"Issue": "?", "Issue_redacted": "?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert out == "Escalate to a human"


def test_low_confidence_escalates():
    docs = [{"path": "data/claude/screen/foo.md", "score": 5.0, "snippet": ""}]
    fake = fake_llm_default(
        canned={
            "generator": {
                "response": "Maybe try this.",
                "cited_doc_paths": ["data/claude/screen/foo.md"],
                "confidence": 0.4,  # below 0.6 threshold
                "refused": False,
                "refusal_reason": "",
            }
        }
    )
    out = generate_response(
        {"Issue": "?", "Issue_redacted": "?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert out == "Escalate to a human"


def test_hallucinated_citation_escalates():
    docs = [{"path": "data/claude/screen/foo.md", "score": 5.0, "snippet": ""}]
    fake = fake_llm_default(
        canned={
            "generator": {
                "response": "Some answer.",
                "cited_doc_paths": ["data/claude/screen/HALLUCINATED.md"],
                "confidence": 0.9,
                "refused": False,
                "refusal_reason": "",
            }
        }
    )
    out = generate_response(
        {"Issue": "?", "Issue_redacted": "?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert out == "Escalate to a human"


def test_llm_failure_escalates():
    docs = [{"path": "data/claude/screen/foo.md", "score": 5.0, "snippet": ""}]
    fake = fake_llm_default(canned={"generator": None})
    out = generate_response(
        {"Issue": "?", "Issue_redacted": "?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert out == "Escalate to a human"


def test_redact_secrets_in_response():
    assert redact_secrets("token cs_live_abc123") == "token [REDACTED]"
    assert (
        redact_secrets("Use sk-ant-api03-XXXXXXXX as your key")
        == "Use [REDACTED] as your key"
    )
    assert (
        redact_secrets("AWS key AKIA1234567890ABCDEF here")
        == "AWS key [REDACTED] here"
    )
    assert redact_secrets("normal text") == "normal text"


def test_response_post_processed_for_secrets():
    """Defense-in-depth #2 (Rev 5.1 §4): Stage 7 output runs through redact."""
    docs = [{"path": "data/claude/screen/foo.md", "score": 5.0, "snippet": ""}]
    fake = fake_llm_default(
        canned={
            "generator": {
                "response": "Your key is cs_live_abc123, please rotate.",
                "cited_doc_paths": ["data/claude/screen/foo.md"],
                "confidence": 0.9,
                "refused": False,
                "refusal_reason": "",
            }
        }
    )
    out = generate_response(
        {"Issue": "?", "Issue_redacted": "?", "Subject": ""},
        {}, docs, "replied", "bug", fake, RowBudget(),
    )
    assert "cs_live_abc123" not in out


# --- Change 1: templated OOS justification override ---
# When the final response equals the templated OOS string, the justification
# must be overridden regardless of what Stage 6 produced. This makes rows 2,
# 3, 12 reproducible: they were manually edited to carry
# "Replied: templated out-of-scope response for invalid request type" but
# a fresh run would have produced "Replied: action_impossible_with_corpus"
# or "Replied: grounded by ..." — both inaccurate.


def test_finalize_justification_overrides_for_templated_oos():
    """OOS response + any Stage 6 justification → override to templated string.

    This is the core contract for Change 1: if the response equals the
    templated OOS phrase, the justification must describe that, not
    whatever Stage 6 inferred.
    """
    result = finalize_justification(
        response=TEMPLATED_OOS_RESPONSE,
        justification="Replied: grounded by foo.md",
    )
    assert result == "Replied: templated out-of-scope response for invalid request type"


def test_finalize_justification_overrides_action_impossible_case():
    """action_impossible_with_corpus justification is also overridden.

    Rows 2 and 3 fire action_impossible and retrieval has docs, so Stage 6
    returns "Replied: action_impossible_with_corpus". But generate_response
    emits the templated OOS string (request_type=invalid), so the
    justification must be corrected.
    """
    result = finalize_justification(
        response=TEMPLATED_OOS_RESPONSE,
        justification="Replied: action_impossible_with_corpus",
    )
    assert result == "Replied: templated out-of-scope response for invalid request type"


def test_finalize_justification_leaves_non_oos_unchanged():
    """Non-OOS responses must not have their justification changed."""
    result = finalize_justification(
        response="Use feature X.",
        justification="Replied: grounded by foo.md",
    )
    assert result == "Replied: grounded by foo.md"


def test_finalize_justification_leaves_escalated_unchanged():
    """Escalated rows are not OOS — justification must not be overridden."""
    result = finalize_justification(
        response="Escalate to a human",
        justification="Escalated: high_risk",
    )
    assert result == "Escalated: high_risk"


def test_generate_response_returns_corrected_justification_for_invalid():
    """End-to-end: invalid request type produces OOS response.

    Even though Stage 6 returned "Replied: action_impossible_with_corpus",
    generate_response must produce the OOS string, and main.py calls
    finalize_justification to update the justification afterwards.
    This test verifies the OOS response is produced (justification correction
    is the caller's responsibility per Change 1 design).
    """
    out = generate_response(
        {"Issue": "weather?", "Issue_redacted": "weather?", "Subject": ""},
        {},
        [],
        "replied",
        "invalid",
        fake_llm_default(),
        RowBudget(),
        justification="Replied: action_impossible_with_corpus",
    )
    assert out == TEMPLATED_OOS_RESPONSE
