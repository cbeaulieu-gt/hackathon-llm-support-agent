"""Main orchestrator. Spec: docs/PLAN.md Rev 5.1 §1 (run_pipeline DI signature).

Entry points:
  python -m code.main [<input.csv> [<output.csv>]]
  from code.main import run_pipeline, run_on_csv
"""
import csv
import sys
from pathlib import Path

from . import config
from .abstain import stage_6_decide
from .classifier import classify_request_type
from .generate import generate_response, redact_secrets
from .llm_client import LLMClient, RowBudget
from .preprocess import preprocess
from .product_area import product_area
from .retrieval import build_index, retrieve
from .router import route_domain
from .safety import safety_triage
from .trace import TraceWriter

HEADERS = [
    "issue",
    "subject",
    "company",
    "response",
    "product_area",
    "status",
    "request_type",
    "justification",
]

_INDEX_CACHE: dict | None = None


def get_index() -> dict:
    """Lazy-build the production BM25 index over data/. Cached for the session."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = build_index(config.DATA_ROOT)
    return _INDEX_CACHE


def run_pipeline(
    row: dict,
    llm_client: LLMClient | None = None,
    index: dict | None = None,
) -> dict:
    """Run all 8 stages on a single input row. Returns the output row dict.

    Args:
        row: Input row with keys 'Issue', 'Subject', 'Company'.
        llm_client: Optional injected LLMClient. If None, constructs the
            default Anthropic-backed client. Tests pass a mock here.
        index: Optional injected BM25 index. If None, uses the cached
            production index over ``data/``. Tests pass a fixture index.
    """
    if llm_client is None:
        llm_client = LLMClient.from_env()
    if index is None:
        index = get_index()
    budget = RowBudget()

    # Stage 0
    cleaned, flags_0 = preprocess(row)
    # Stage 1
    flags = safety_triage(cleaned, flags_0)

    # Stage 2
    routed_domain, route_source = route_domain(cleaned, flags, llm_client, budget)
    # Per Rev 4 Stage 2 table: domain_routing_failed fires when LLM retries
    # are exhausted AND the keyword heuristic also returns 'none'.
    if routed_domain == "none" and route_source == "fallback":
        flags["domain_routing_failed"] = True
    else:
        flags.setdefault("domain_routing_failed", False)

    # Stage 3
    request_type, _ = classify_request_type(cleaned, flags, llm_client, budget)
    flags.setdefault("request_type_classification_failed", False)

    # Stage 4 — runs for ALL rows per Rev 5 §14 (Q3 user choice).
    # Domain-filter when known so e.g. HackerRank tickets don't pull Claude docs.
    # If domain == 'none', search across full corpus (e.g. invalid rows).
    # Subject is duplicated in the query: it's typically a focused topic
    # whereas Issue is verbose, so BM25 should weight it more heavily.
    subject = cleaned.get("Subject", "")
    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    query = (subject + " " + subject + " " + issue).strip()
    domain_filter = routed_domain if routed_domain != "none" else None
    top_k_docs: list = retrieve(query, index, domain_filter=domain_filter)

    # Stage 5
    pa = product_area(top_k_docs[0]["path"] if top_k_docs else None)

    # Stage 6
    status, justification = stage_6_decide(
        flags, len(top_k_docs), top_k_docs, request_type
    )

    # Tuning iteration 3: empty product_area for escalated and pleasantry
    # rows. The sample's golden labels follow this convention — escalated
    # rows have no rubric-relevant product area (the user is being handed
    # to a human anyway), and pleasantries are genuinely OOS.
    if status == "escalated" or flags.get("oos_pleasantry"):
        pa = ""

    # Stage 7
    response = generate_response(
        cleaned, flags, top_k_docs, status, request_type, llm_client, budget
    )

    return {
        "issue": redact_secrets(cleaned["Issue"]),
        "subject": redact_secrets(cleaned["Subject"]),
        "company": cleaned["Company"],
        "response": redact_secrets(response),
        "product_area": pa,
        "status": status,
        "request_type": request_type,
        "justification": redact_secrets(justification),
    }


def run_on_csv(
    input_csv: Path,
    output_csv: Path,
    trace_path: Path | None = None,
) -> int:
    """Read input CSV, run pipeline on each row, write output CSV.

    Returns the number of rows written.
    """
    config.require_api_key()
    llm = LLMClient.from_env()
    index = get_index()
    trace = TraceWriter(trace_path or (config.REPO_ROOT / "code" / "run_trace.jsonl"))

    with open(input_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for i, row in enumerate(rows, 1):
            out = run_pipeline(row, llm, index)
            w.writerow(out)
            trace.write(i, **out)
            print(
                f"[{i}/{len(rows)}] {out['status']:>9} {out['request_type']:>15} "
                f"{out['product_area']}"
            )

    return len(rows)


if __name__ == "__main__":
    inp = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else config.SUPPORT_TICKETS_DIR / "support_tickets.csv"
    )
    out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else config.SUPPORT_TICKETS_DIR / "output.csv"
    )
    n = run_on_csv(inp, out)
    print(f"\nDone: {n} rows written to {out}")
