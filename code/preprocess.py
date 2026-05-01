"""Stage 0 — Preprocess.

Normalizes input row, sets stage-0 flags. Never raises.

Spec: docs/PLAN.md Rev 3 §Stage 0 + Rev 4 §"Decision: no fuzzy matching".
"""
import re

CANONICAL_COMPANIES = {
    "hackerrank": "HackerRank",
    "claude": "Claude",
    "visa": "Visa",
    "none": "None",
    "": "",
}

# Order matters: try the most specific patterns first so the generic
# `sk-...` rule doesn't shadow `sk-ant-api03-...`.
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-api03-[A-Za-z0-9_-]+"), "[REDACTED]"),
    (re.compile(r"cs_live_\w+"), "[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.+\-/=]+"), "[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "[REDACTED]"),
]


def _normalize_company(raw: str) -> str:
    key = raw.strip().lower()
    return CANONICAL_COMPANIES.get(key, "None")


def _normalize_text(text: str) -> str:
    """Strip + replace curly quotes + collapse `\\r\\n` to `\\n`."""
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _redact_secrets(text: str) -> tuple[str, bool]:
    contains = False
    for pat, repl in SECRET_PATTERNS:
        if pat.search(text):
            contains = True
            text = pat.sub(repl, text)
    return text, contains


def preprocess(row: dict) -> tuple[dict, dict]:
    """Returns ``(cleaned_row, flags)``. Stage 0 of the pipeline.

    The cleaned row carries both ``Issue`` (original-with-text-normalize) and
    ``Issue_redacted`` (with secret-shaped tokens replaced by ``[REDACTED]``).
    Downstream LLM stages MUST send only ``Issue_redacted`` to the API.
    """
    flags: dict = {
        "empty_issue": False,
        "contains_secret_shaped": False,
        "company_unknown": False,
    }
    issue_raw = row.get("Issue", "") or ""
    subject_raw = row.get("Subject", "") or ""
    company_raw = row.get("Company", "") or ""

    issue_norm = _normalize_text(issue_raw)
    subject_norm = _normalize_text(subject_raw)

    if not issue_norm.strip():
        flags["empty_issue"] = True

    issue_redacted, contains = _redact_secrets(issue_norm)
    flags["contains_secret_shaped"] = contains

    company = _normalize_company(company_raw)
    company_key = company_raw.strip().lower()
    if company == "None" and company_key not in ("", "none"):
        flags["company_unknown"] = True

    return (
        {
            "Issue": issue_norm,
            "Issue_redacted": issue_redacted,
            "Subject": subject_norm,
            "Company": company,
        },
        flags,
    )
