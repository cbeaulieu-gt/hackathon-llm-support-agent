"""Anthropic SDK wrapper with retry, timeout, and structured-output parsing.

Spec: docs/PLAN.md Rev 5 §12 (RowBudget) + Rev 5.1 §1 (DI).
"""
import json

from anthropic import Anthropic, APIError, APITimeoutError, RateLimitError

from . import config


class RowBudget:
    """Per-row LLM call budget shared across Stages 2/3/7. (Rev 5 §12)"""

    def __init__(self, max_attempts: int | None = None):
        if max_attempts is None:
            max_attempts = config.LLM_MAX_ATTEMPTS_PER_ROW
        self.remaining = max_attempts

    def consume(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


class LLMClient:
    """Thin wrapper. .complete_json() returns parsed dict or None on failure."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = Anthropic(api_key=api_key or config.require_api_key())
        self.model = model or config.ANTHROPIC_MODEL

    @classmethod
    def from_env(cls) -> "LLMClient":
        return cls()

    def complete_json(
        self,
        system: str,
        user: str,
        budget: RowBudget,
        max_tokens: int = 1024,
    ) -> dict | None:
        """Single attempt; consumes one budget unit. Returns parsed dict or None.

        On any API error, malformed JSON, or budget exhaustion, returns None
        so the caller can fall back to keyword heuristics or escalate.
        """
        if not budget.consume():
            return None
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user}],
                timeout=config.LLM_TIMEOUT_S,
            )
        except (APITimeoutError, APIError, RateLimitError):
            return None
        text = resp.content[0].text if resp.content else ""
        # Find first {...} block — the model may add prose around the JSON
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
