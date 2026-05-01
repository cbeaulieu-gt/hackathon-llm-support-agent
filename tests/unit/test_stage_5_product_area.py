"""Stage 5 product_area tests. Spec: docs/PLAN.md Rev 5 §3 (full replacement)."""
import pytest

from code.product_area import product_area


@pytest.mark.parametrize(
    "path,expected",
    [
        # Visa sub-doc heuristic
        ("data/visa/support/consumer/travelers-cheques.md", "travel_support"),
        ("data/visa/support/consumer/visa-rules.md", "general_support"),
        ("data/visa/support/consumer.md", "general_support"),
        ("data/visa/support/merchant.md", "general_support"),
        ("data/visa/support/consumer/travel-support/foo.md", "travel_support"),
        # Claude second-level subdir
        (
            "data/claude/claude/conversation-management/8230524-how-to-delete.md",
            "conversation_management",
        ),
        (
            "data/claude/claude/account-management/8325621-i-would-like.md",
            "account_management",
        ),
        # Claude first-level alias
        (
            "data/claude/safeguards/12119250-bug-bounty.md",
            "safeguards",
        ),
        ("data/claude/privacy-and-legal/foo.md", "privacy"),
        ("data/claude/claude-code/some-doc.md", "claude-code"),
        # HackerRank
        ("data/hackerrank/screen/foo.md", "screen"),
        ("data/hackerrank/hackerrank_community/foo.md", "community"),
        ("data/hackerrank/general-help/faq.md", "general_support"),
        # Index file at domain root
        ("data/hackerrank/index.md", "general_support"),
        ("data/visa/index.md", "general_support"),
        ("data/claude/index.md", "claude"),
        # Empty / None
        ("", ""),
        (None, ""),
    ],
)
def test_product_area(path, expected):
    assert product_area(path) == expected


def test_product_area_handles_windows_paths():
    """Backslashes get normalized to forward slashes."""
    assert (
        product_area(r"data\visa\support\consumer\travelers-cheques.md")
        == "travel_support"
    )
