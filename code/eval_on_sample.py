"""Run agent on sample_support_tickets.csv and compare against ground truth.

Spec: docs/PLAN.md Rev 5 §19 (tuning loop) + Verification §3.

Run: python -m code.eval_on_sample
"""
import csv
import sys
from pathlib import Path

from . import config
from .main import run_on_csv

SAMPLE_INPUT = config.SUPPORT_TICKETS_DIR / "sample_support_tickets.csv"
SAMPLE_OUTPUT = config.SUPPORT_TICKETS_DIR / "_sample_output.csv"
SAMPLE_TRACE = config.REPO_ROOT / "code" / "_sample_trace.jsonl"


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def diff_columns(produced_path: Path, golden_path: Path) -> dict:
    """Compare four scored columns case-insensitively, count row-perfect."""
    with open(produced_path, "r", encoding="utf-8") as f:
        produced = list(csv.DictReader(f))
    with open(golden_path, "r", encoding="utf-8") as f:
        golden = list(csv.DictReader(f))

    # Map produced column names → golden column names
    # Produced uses lowercase snake_case + 'justification'
    # Golden uses Title Case w/ spaces, no 'justification'
    cols = [
        ("status", "Status"),
        ("request_type", "Request Type"),
        ("product_area", "Product Area"),
        ("response", "Response"),
    ]

    n = min(len(produced), len(golden))
    per_col_correct = {p: 0 for p, _ in cols}
    row_perfect = 0
    issues: list[dict] = []

    for i in range(n):
        p_row = produced[i]
        g_row = golden[i]
        all_match = True
        row_diff: dict = {"row": i + 1}
        for p_col, g_col in cols:
            p_val = _normalize(p_row.get(p_col, ""))
            g_val = _normalize(g_row.get(g_col, ""))
            # 'response' is semantic — only count exact-empty-vs-nonempty parity
            if p_col == "response":
                p_empty = (p_val == "")
                g_empty = (g_val == "")
                ok = (p_empty == g_empty)
            else:
                ok = (p_val == g_val)
            if ok:
                per_col_correct[p_col] += 1
            else:
                all_match = False
                row_diff[p_col] = {
                    "produced": p_row.get(p_col, ""),
                    "golden": g_row.get(g_col, ""),
                }
        if all_match:
            row_perfect += 1
        elif len(row_diff) > 1:
            issues.append(row_diff)

    return {
        "rows": n,
        "row_perfect": row_perfect,
        "per_col": per_col_correct,
        "issues": issues,
    }


def main() -> int:
    n = run_on_csv(SAMPLE_INPUT, SAMPLE_OUTPUT, trace_path=SAMPLE_TRACE)
    print(f"\nWrote {n} rows to {SAMPLE_OUTPUT}")

    diff = diff_columns(SAMPLE_OUTPUT, SAMPLE_INPUT)
    print(f"\n=== Diff vs sample ground truth ===")
    print(f"Rows compared: {diff['rows']}")
    print(f"Row-perfect (status + request_type + product_area + response-presence): "
          f"{diff['row_perfect']}/{diff['rows']}")
    print(f"Per-column accuracy:")
    for col, correct in diff["per_col"].items():
        print(f"  {col}: {correct}/{diff['rows']}")
    if diff["issues"]:
        print(f"\n=== {len(diff['issues'])} rows with at least one mismatch ===")
        for issue in diff["issues"]:
            print(f"  Row {issue['row']}:")
            for k, v in issue.items():
                if k == "row":
                    continue
                print(f"    {k}: produced={v['produced']!r:30s} | golden={v['golden']!r}")

    threshold = 7
    if diff["row_perfect"] >= threshold:
        print(f"\nPASS: {diff['row_perfect']}/{diff['rows']} >= {threshold}")
        return 0
    print(f"\nFAIL: {diff['row_perfect']}/{diff['rows']} < {threshold}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
