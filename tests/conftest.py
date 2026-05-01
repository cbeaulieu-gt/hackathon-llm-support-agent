"""Shared test fixtures.

`fake_llm_default()` returns a MagicMock-backed LLMClient that returns
canned responses keyed by Stage system-prompt fingerprint.
"""
from unittest.mock import MagicMock

import pytest

from code.llm_client import LLMClient, RowBudget


def fake_llm_default(canned: dict | None = None) -> LLMClient:
    """Returns a LLMClient whose complete_json() returns canned responses
    or sensible defaults per Stage system prompt. Tests override via canned.

    canned keys: 'router', 'classifier', 'generator', 'default'.
    A None value short-circuits that stage to None (simulating LLM failure).
    """
    client = MagicMock(spec=LLMClient)
    canned = canned or {}

    def _complete_json(
        system: str, user: str, budget: RowBudget, max_tokens: int = 1024
    ):
        if not budget.consume():
            return None
        sys_low = system.lower()
        if "domain router" in sys_low:
            return canned.get(
                "router", {"domain": "claude", "confidence": 0.9}
            ) if "router" not in canned or canned.get("router") is not None else None
        if "request-type classifier" in sys_low:
            return canned.get(
                "classifier",
                {"request_type": "product_issue", "confidence": 0.9},
            ) if "classifier" not in canned or canned.get("classifier") is not None else None
        if "support-agent assistant" in sys_low:
            return canned.get(
                "generator",
                {
                    "response": "Mock answer.",
                    "cited_doc_paths": [],
                    "confidence": 0.9,
                    "refused": False,
                    "refusal_reason": "",
                },
            ) if "generator" not in canned or canned.get("generator") is not None else None
        return canned.get("default")

    client.complete_json.side_effect = _complete_json
    return client


@pytest.fixture
def fake_llm():
    return fake_llm_default()
