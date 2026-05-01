"""Stage 5 product_area tests.

Spec: docs/PLAN.md Rev 5 §3 (full replacement) + Stage 5 specificity fix
(low-specificity subdir avoidance and invalid+no-domain short-circuit).
"""
import pytest

from code.product_area import product_area


def _doc(path: str, score: float = 1.0) -> dict:
    """Build a minimal top-K doc dict as returned by retrieval."""
    return {"path": path, "score": score}


# ---------------------------------------------------------------------------
# Existing single-path tests (updated to new signature)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path,domain,expected",
    [
        # Visa sub-doc heuristic
        (
            "data/visa/support/consumer/travelers-cheques.md",
            "visa",
            "travel_support",
        ),
        ("data/visa/support/consumer/visa-rules.md", "visa", "general_support"),
        ("data/visa/support/consumer.md", "visa", "general_support"),
        ("data/visa/support/merchant.md", "visa", "general_support"),
        (
            "data/visa/support/consumer/travel-support/foo.md",
            "visa",
            "travel_support",
        ),
        # Claude second-level subdir
        (
            "data/claude/claude/conversation-management/8230524-how-to-delete.md",
            "claude",
            "conversation_management",
        ),
        (
            "data/claude/claude/account-management/8325621-i-would-like.md",
            "claude",
            "account_management",
        ),
        # Claude first-level alias
        (
            "data/claude/safeguards/12119250-bug-bounty.md",
            "claude",
            "safeguards",
        ),
        ("data/claude/privacy-and-legal/foo.md", "claude", "privacy"),
        ("data/claude/claude-code/some-doc.md", "claude", "claude-code"),
        # HackerRank
        ("data/hackerrank/screen/foo.md", "hackerrank", "screen"),
        (
            "data/hackerrank/hackerrank_community/foo.md",
            "hackerrank",
            "community",
        ),
        (
            "data/hackerrank/general-help/faq.md",
            "hackerrank",
            "general_support",
        ),
        # Index file at domain root
        ("data/hackerrank/index.md", "hackerrank", "general_support"),
        ("data/visa/index.md", "visa", "general_support"),
        ("data/claude/index.md", "claude", "claude"),
    ],
)
def test_product_area_single_doc(path: str, domain: str, expected: str) -> None:
    """Single-doc top-K list falls through to normal derivation logic."""
    assert product_area([_doc(path)], domain) == expected


def test_product_area_empty_list() -> None:
    """Empty top-K list returns empty string."""
    assert product_area([], "hackerrank") == ""


def test_product_area_handles_windows_paths() -> None:
    """Backslashes get normalized to forward slashes."""
    assert (
        product_area(
            [_doc(r"data\visa\support\consumer\travelers-cheques.md")],
            "visa",
        )
        == "travel_support"
    )


# ---------------------------------------------------------------------------
# Fix 1: low-specificity subdir avoidance
# ---------------------------------------------------------------------------
def test_low_specificity_top1_prefers_higher_specificity_in_topk() -> None:
    """When top-1 is in a low-specificity subdir but top-K has a better doc,
    the result should be derived from the higher-specificity doc."""
    docs = [
        _doc("data/hackerrank/general-help/release-notes/january-2026.md", 2.5),
        _doc("data/hackerrank/screen/managing-tests/modify-test-expiration.md", 2.1),
    ]
    # top-1 is general-help → general_support; we should prefer screen
    assert product_area(docs, "hackerrank") == "screen"


def test_low_specificity_top1_keeps_top1_when_all_topk_low() -> None:
    """When every top-K doc is in a low-specificity subdir, keep top-1's area."""
    docs = [
        _doc("data/hackerrank/general-help/release-notes/foo.md", 3.0),
        _doc("data/hackerrank/uncategorized/onboarding-candidates.md", 2.0),
        _doc("data/hackerrank/general-help/faq.md", 1.5),
    ]
    # All are low-specificity → fall back to top-1 → general_support
    assert product_area(docs, "hackerrank") == "general_support"


def test_high_specificity_top1_uses_top1() -> None:
    """When top-1 is already in a high-specificity subdir, no override occurs."""
    docs = [
        _doc("data/hackerrank/screen/managing-tests/add-time.md", 3.0),
        _doc("data/hackerrank/general-help/release-notes/foo.md", 2.5),
    ]
    assert product_area(docs, "hackerrank") == "screen"


def test_low_specificity_top1_uncategorized_prefers_topk() -> None:
    """Uncategorized top-1 also triggers the low-specificity override."""
    docs = [
        _doc("data/hackerrank/uncategorized/onboarding-candidates.md", 3.0),
        _doc("data/hackerrank/screen/managing-tests/adding-extra-time.md", 2.5),
    ]
    assert product_area(docs, "hackerrank") == "screen"


# ---------------------------------------------------------------------------
# Fix 2: request_type=invalid + domain=none → empty product_area
# ---------------------------------------------------------------------------
def test_invalid_no_domain_returns_empty() -> None:
    """When request_type is 'invalid' and domain is 'none', Stage 5 must
    return empty string regardless of what retrieval returned (the retrieved
    docs are noise for OOS queries with no routed domain)."""
    docs = [
        _doc("data/claude/claude-in-chrome/iron-man-actor.md", 5.0),
    ]
    assert product_area(docs, "none", request_type="invalid") == ""
