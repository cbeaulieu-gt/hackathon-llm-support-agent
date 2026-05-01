"""Stage 3.5 spot-check: verify query expansion improves recall on 4 target tickets.

Runs baseline BM25 (Subject+Subject+Issue) vs. expansion-augmented query for
tickets #11, #13, #20, #27 and prints a verdict table.

Usage:
    uv run --directory <worktree> python scripts/spot_check_expansion.py

Requires ANTHROPIC_API_KEY in the worktree's .env.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add worktree root to sys.path so `code.*` imports resolve.
# ---------------------------------------------------------------------------
WORKTREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from code.llm_client import LLMClient, RowBudget  # noqa: E402
from code.query_expansion import expand_query  # noqa: E402
from code.retrieval import build_index, retrieve  # noqa: E402

# ---------------------------------------------------------------------------
# Target-ticket definitions
# ---------------------------------------------------------------------------
# (ticket_number, goal_basenames, goal_description)
TARGETS: list[tuple[int, list[str], str]] = [
    (
        11,
        ["1151935613-using-virtual-lobby-in-hackerrank-interviews.md"],
        "virtual-lobby in top-3",
    ),
    (
        13,
        [
            "2203617737-manage-team-members.md",
            "6534774997-locking-user-access-from-hackerrank.md",
            # additional siblings if they exist
        ],
        "manage-team-members or sibling in top-3",
    ),
    (
        20,
        [
            "12119250-model-safety-bug-bounty-program.md",
            "11427875-public-vulnerability-reporting.md",
        ],
        "bug-bounty or vuln-reporting stays top-1 (no regression)",
    ),
    (
        27,
        [
            "2203617737-manage-team-members.md",
            "6534774997-locking-user-access-from-hackerrank.md",
        ],
        "manage-team-members or sibling in top-3",
    ),
]

# Map ticket number → (top_k_cutoff, require_rank_1)
# #20 only needs top-1 (regression guard); the rest need top-3.
TOP_K_GOAL: dict[int, int] = {11: 3, 13: 3, 20: 1, 27: 3}


def _load_tickets(csv_path: Path) -> dict[int, dict]:
    """Return {row_number: row_dict} for the 4 target tickets (1-indexed)."""
    target_nums = {t[0] for t in TARGETS}
    found: dict[int, dict] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh), 1):
            if i in target_nums:
                found[i] = row
            if len(found) == len(target_nums):
                break
    return found


def _basenames(hits: list[dict]) -> list[str]:
    """Extract Path.name from each hit path."""
    return [Path(h["path"]).name for h in hits]


def _hit_in_top_k(
    hits: list[dict],
    goal_basenames: list[str],
    top_k: int,
) -> bool:
    """Return True if any goal basename appears in hits[:top_k]."""
    top_names = set(_basenames(hits[:top_k]))
    return bool(top_names & set(goal_basenames))


def _fmt_hits(hits: list[dict]) -> str:
    """Format top-5 hits as 'basename (score)' lines."""
    lines = []
    for rank, h in enumerate(hits[:5], 1):
        name = Path(h["path"]).name
        lines.append(f"  {rank}. {name} ({h['score']:.3f})")
    return "\n".join(lines) if lines else "  (no hits)"


def main() -> None:
    """Run the spot-check and print a verdict table."""
    csv_path = WORKTREE_ROOT / "support_tickets" / "support_tickets.csv"
    data_root = WORKTREE_ROOT / "data"

    if not csv_path.exists():
        sys.exit(f"ERROR: CSV not found at {csv_path}")
    if not data_root.exists():
        sys.exit(f"ERROR: data/ not found at {data_root}")

    print("Building BM25 index … ", end="", flush=True)
    index = build_index(data_root)
    print(f"done ({len(index['paths'])} docs)\n")

    tickets = _load_tickets(csv_path)
    llm = LLMClient.from_env()

    passed = 0
    total = len(TARGETS)

    for ticket_num, goal_basenames, goal_desc in TARGETS:
        row = tickets.get(ticket_num)
        if row is None:
            print(f"[#{ ticket_num}] ERROR: ticket not found in CSV\n")
            continue

        subject = row.get("Subject", "").strip()
        issue = row.get("Issue", "").strip()
        company = row.get("Company", "").strip().lower()

        # Baseline query: Subject + Subject + Issue (matches main.py Stage 4)
        base_query = f"{subject} {subject} {issue}".strip()

        # Domain filter = company name (hackerrank / claude / visa)
        domain_filter: str | None = company if company != "none" else None

        # --- Baseline retrieval (no expansion) ---
        baseline_hits = retrieve(
            base_query, index, top_k=5, domain_filter=domain_filter
        )

        # --- Expansion retrieval ---
        budget = RowBudget(max_attempts=5)
        expansion, exp_info = expand_query(
            subject=subject,
            issue_redacted=issue,
            domain=company,
            llm_client=llm,
            budget=budget,
        )
        expanded_query = (
            f"{base_query} {expansion}".strip() if expansion else base_query
        )
        expanded_hits = retrieve(
            expanded_query, index, top_k=5, domain_filter=domain_filter
        )

        # --- Verdict ---
        cutoff = TOP_K_GOAL[ticket_num]
        met = _hit_in_top_k(expanded_hits, goal_basenames, cutoff)
        if met:
            passed += 1
        verdict = "PASS" if met else "FAIL"

        # --- Print ---
        print(f"{'=' * 70}")
        print(f"Ticket #{ticket_num}: {subject[:60]}")
        print(f"Domain: {company}  |  Goal: {goal_desc}")
        print(f"Expansion keywords: {expansion!r}  (source={exp_info['source']}, conf={exp_info['confidence']:.2f})")
        print()
        print("Baseline top-5:")
        print(_fmt_hits(baseline_hits))
        print()
        print("With-expansion top-5:")
        print(_fmt_hits(expanded_hits))
        print()
        print(f"Verdict: [{verdict}]  (target in top-{cutoff}? {met})")
        print()

    print("=" * 70)
    print(f"SUMMARY: {passed} of {total} tickets met the goal")
    if passed >= 3:
        print("GREEN LIGHT — proceed to full 29-row run.")
    else:
        print("RED FLAG — iterate on the expansion prompt before full run.")


if __name__ == "__main__":
    main()
