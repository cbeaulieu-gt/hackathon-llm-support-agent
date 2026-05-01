"""Stage 0 (preprocess) tests. Spec: docs/PLAN.md Rev 3 §Stage 0 + Rev 4 Stage 0 decision."""
from code.preprocess import preprocess


def test_company_trailing_whitespace():
    """`'None '` (with trailing space) → normalized to `'None'`."""
    cleaned, _ = preprocess(
        {"Issue": "x", "Subject": "y", "Company": "None "}
    )
    assert cleaned["Company"] == "None"


def test_company_case_insensitive():
    """`'hackerrank'` → normalized to canonical `'HackerRank'`."""
    cleaned, _ = preprocess(
        {"Issue": "x", "Subject": "y", "Company": "hackerrank"}
    )
    assert cleaned["Company"] == "HackerRank"


def test_company_unknown_becomes_none():
    """Unknown company → `'None'` (no fuzzy matching per Rev 4 Stage 0 decision)."""
    cleaned, flags = preprocess(
        {"Issue": "x", "Subject": "y", "Company": "Acme Corp"}
    )
    assert cleaned["Company"] == "None"
    assert flags["company_unknown"] is True


def test_empty_issue_short_circuit():
    cleaned, flags = preprocess(
        {"Issue": "   ", "Subject": "y", "Company": "Claude"}
    )
    assert flags["empty_issue"] is True


def test_secret_redaction_preserves_original():
    """Stripe-shaped token: redacted copy in `Issue_redacted`, original preserved in `Issue`, flag set."""
    raw = "my key is cs_live_abc123def456"
    cleaned, flags = preprocess(
        {"Issue": raw, "Subject": "y", "Company": "Visa"}
    )
    assert flags["contains_secret_shaped"] is True
    assert cleaned["Issue"] == raw
    assert cleaned["Issue_redacted"] == "my key is [REDACTED]"


def test_unicode_quotes_normalized():
    cleaned, _ = preprocess(
        {"Issue": "he said “hi”", "Subject": "y", "Company": "Claude"}
    )
    assert "“" not in cleaned["Issue"]
    assert '"' in cleaned["Issue"]


def test_crlf_normalized():
    cleaned, _ = preprocess(
        {"Issue": "line1\r\nline2", "Subject": "y", "Company": "Claude"}
    )
    assert "\r\n" not in cleaned["Issue"]
    assert "line1\nline2" == cleaned["Issue"]


def test_anthropic_api_key_redacted():
    raw = "key sk-ant-api03-XXXXXX please"
    cleaned, flags = preprocess(
        {"Issue": raw, "Subject": "y", "Company": "Claude"}
    )
    assert flags["contains_secret_shaped"] is True
    assert "[REDACTED]" in cleaned["Issue_redacted"]
