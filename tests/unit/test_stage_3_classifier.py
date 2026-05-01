"""Stage 3 classifier tests."""
from code.classifier import classify_request_type
from code.llm_client import RowBudget
from tests.conftest import fake_llm_default


def test_oos_pleasantry_short_circuit():
    cleaned = {"Issue": "thanks!", "Issue_redacted": "thanks!", "Subject": ""}
    flags = {"oos_pleasantry": True}
    rt, source = classify_request_type(cleaned, flags, fake_llm_default(), RowBudget())
    assert rt == "invalid"
    assert source == "short-circuit"


def test_empty_issue_short_circuit():
    cleaned = {"Issue": "", "Issue_redacted": "", "Subject": ""}
    flags = {"empty_issue": True}
    rt, _ = classify_request_type(cleaned, flags, fake_llm_default(), RowBudget())
    assert rt == "invalid"


def test_llm_classifies_bug():
    cleaned = {
        "Issue": "the API is failing",
        "Issue_redacted": "the API is failing",
        "Subject": "",
    }
    fake = fake_llm_default(
        canned={"classifier": {"request_type": "bug", "confidence": 0.9}}
    )
    rt, source = classify_request_type(cleaned, {}, fake, RowBudget())
    assert rt == "bug"
    assert source == "llm"


def test_llm_failure_falls_back_to_heuristic_bug():
    cleaned = {
        "Issue": "everything is broken and not working",
        "Issue_redacted": "everything is broken and not working",
        "Subject": "",
    }
    fake = fake_llm_default(canned={"classifier": None})
    rt, source = classify_request_type(cleaned, {}, fake, RowBudget())
    assert rt == "bug"
    assert source == "fallback"


def test_llm_failure_falls_back_to_heuristic_feature():
    cleaned = {
        "Issue": "would be nice to add support for dark mode",
        "Issue_redacted": "would be nice to add support for dark mode",
        "Subject": "",
    }
    fake = fake_llm_default(canned={"classifier": None})
    rt, _ = classify_request_type(cleaned, {}, fake, RowBudget())
    assert rt == "feature_request"


def test_llm_returns_invalid_label_falls_back():
    cleaned = {
        "Issue": "I can't log in",
        "Issue_redacted": "I can't log in",
        "Subject": "",
    }
    fake = fake_llm_default(
        canned={"classifier": {"request_type": "complaint", "confidence": 0.9}}
    )
    rt, source = classify_request_type(cleaned, {}, fake, RowBudget())
    # 'complaint' not in VALID_REQUEST_TYPES → fallback to keyword heuristic
    assert source == "fallback"
    assert rt == "product_issue"
