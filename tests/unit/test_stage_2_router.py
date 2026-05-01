"""Stage 2 router tests."""
from code.llm_client import RowBudget
from code.router import route_domain
from tests.conftest import fake_llm_default


def test_company_field_skips_llm():
    """Company set → trust it, no LLM call."""
    cleaned = {"Issue": "anything", "Subject": "", "Company": "Claude"}
    domain, source = route_domain(cleaned, {}, fake_llm_default(), RowBudget())
    assert domain == "claude"
    assert source == "company-field"


def test_company_visa_passes_through():
    cleaned = {"Issue": "x", "Subject": "y", "Company": "Visa"}
    domain, _ = route_domain(cleaned, {}, fake_llm_default(), RowBudget())
    assert domain == "visa"


def test_company_none_calls_llm():
    cleaned = {
        "Issue": "x",
        "Issue_redacted": "x",
        "Subject": "y",
        "Company": "None",
    }
    fake = fake_llm_default(
        canned={"router": {"domain": "hackerrank", "confidence": 0.9}}
    )
    domain, source = route_domain(cleaned, {}, fake, RowBudget())
    assert domain == "hackerrank"
    assert source == "llm"


def test_low_confidence_returns_none():
    cleaned = {
        "Issue": "x",
        "Issue_redacted": "x",
        "Subject": "y",
        "Company": "None",
    }
    fake = fake_llm_default(
        canned={"router": {"domain": "claude", "confidence": 0.3}}
    )
    domain, _ = route_domain(cleaned, {}, fake, RowBudget())
    assert domain == "none"


def test_llm_failure_falls_back_to_keyword_heuristic():
    cleaned = {
        "Issue": "i love hackerrank challenges and interview tests",
        "Issue_redacted": "i love hackerrank challenges and interview tests",
        "Subject": "",
        "Company": "None",
    }
    fake = fake_llm_default(canned={"router": None})
    domain, source = route_domain(cleaned, {}, fake, RowBudget())
    assert domain == "hackerrank"
    assert source == "fallback"


def test_llm_returns_invalid_domain_falls_back():
    cleaned = {
        "Issue": "claude is great",
        "Issue_redacted": "claude is great",
        "Subject": "",
        "Company": "None",
    }
    fake = fake_llm_default(
        canned={"router": {"domain": "openai", "confidence": 0.9}}
    )
    domain, source = route_domain(cleaned, {}, fake, RowBudget())
    # 'openai' not in VALID_DOMAINS → fallback heuristic
    assert source == "fallback"
    assert domain in {"claude", "none"}  # heuristic counts 'claude' keyword
