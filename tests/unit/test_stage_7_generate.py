"""Stage 7 generation tests."""
from code.generate import generate_response, redact_secrets
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
    assert "[REDACTED]" in out
