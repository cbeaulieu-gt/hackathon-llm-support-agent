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
from .query_expansion import expand_query
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
    trace: dict | None = None,
) -> dict:
    """Run all 8 stages on a single input row. Returns the output row dict.

    Args:
        row: Input row with keys 'Issue', 'Subject', 'Company'.
        llm_client: Optional injected LLMClient. If None, constructs the
            default Anthropic-backed client. Tests pass a mock here.
        index: Optional injected BM25 index. If None, uses the cached
            production index over ``data/``. Tests pass a fixture index.
        trace: Optional dict to populate with per-stage decision audit info
            (post-mortem CHARGE 5). Mutated in place; pass ``{}`` to opt in.
    """
    if llm_client is None:
        llm_client = LLMClient.from_env()
    if index is None:
        index = get_index()
    budget = RowBudget()

    # Stage 0
    cleaned, flags_0 = preprocess(row)
    if trace is not None:
        trace["stage_0_flags"] = dict(flags_0)
    # Stage 1
    flags = safety_triage(cleaned, flags_0)
    if trace is not None:
        trace["stage_1_flags"] = {k: v for k, v in flags.items() if k not in flags_0}

    # Stage 2
    routed_domain, route_source = route_domain(cleaned, flags, llm_client, budget)
    # Per Rev 4 Stage 2 table: domain_routing_failed fires when LLM retries
    # are exhausted AND the keyword heuristic also returns 'none'.
    if routed_domain == "none" and route_source == "fallback":
        flags["domain_routing_failed"] = True
    else:
        flags.setdefault("domain_routing_failed", False)
    if trace is not None:
        trace["stage_2_routed_domain"] = routed_domain
        trace["stage_2_route_source"] = route_source

    # Stage 3
    request_type, rt_source = classify_request_type(cleaned, flags, llm_client, budget)
    flags.setdefault("request_type_classification_failed", False)
    if trace is not None:
        trace["stage_3_request_type"] = request_type
        trace["stage_3_source"] = rt_source

    # Stage 3.5 — Query Expansion.
    # Calls the LLM to map user vocabulary onto corpus vocabulary so BM25 can
    # find the right document even when phrasing doesn't match the index.
    # Failure is always a silent no-op: expansion == '' leaves the query
    # unchanged and no exception propagates.
    subject = cleaned.get("Subject", "")
    issue = cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    expansion, expansion_info = expand_query(
        subject=subject,
        issue_redacted=issue,
        domain=routed_domain,
        llm_client=llm_client,
        budget=budget,
    )
    if trace is not None:
        trace["stage_3_5_query_expansion"] = expansion_info

    # Stage 4 — runs for ALL rows per Rev 5 §14 (Q3 user choice).
    # Domain-filter when known so e.g. HackerRank tickets don't pull Claude docs.
    # If domain == 'none', search across full corpus (e.g. invalid rows).
    # Subject is duplicated in the query: it's typically a focused topic
    # whereas Issue is verbose, so BM25 should weight it more heavily.
    # Expansion keywords (Stage 3.5) are appended when non-empty.
    base_query = (subject + " " + subject + " " + issue).strip()
    query = (base_query + " " + expansion).strip() if expansion else base_query
    domain_filter = routed_domain if routed_domain != "none" else None
    top_k_docs: list = retrieve(query, index, domain_filter=domain_filter)
    if trace is not None:
        trace["stage_4_query"] = query[:200]
        trace["stage_4_domain_filter"] = domain_filter
        trace["stage_4_top_k"] = [
            {"path": d["path"], "score": round(d["score"], 3)}
            for d in top_k_docs
        ]

    # Stage 5 — pass full top-K list so the low-specificity avoidance
    # heuristic can scan beyond top-1; also pass domain and request_type so
    # the invalid+no-domain short-circuit can suppress noise-derived labels.
    pa = product_area(top_k_docs, routed_domain, request_type=request_type)
    if trace is not None:
        trace["stage_5_product_area"] = pa

    # Stage 6
    status, justification = stage_6_decide(
        flags, len(top_k_docs), top_k_docs, request_type
    )
    if trace is not None:
        trace["stage_6_status"] = status
        trace["stage_6_justification"] = justification

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

    # Post-pre-mortem fix: if Stage 7 returned the escalate template because
    # grounding failed (refused / low-confidence / hallucinated cite / API
    # failure), propagate to status. Otherwise we ship rows where
    # status='replied' AND response='Escalate to a human' — self-contradicting.
    if response == "Escalate to a human" and status == "replied":
        status = "escalated"
        justification = "Escalated: stage_7_grounding_failed"
        pa = ""

    if trace is not None:
        trace["stage_7_response_first_120"] = response[:120]
        trace["final_status"] = status
        trace["final_justification"] = justification
        trace["llm_budget_remaining"] = budget.remaining

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
            row_trace: dict = {}
            out = run_pipeline(row, llm, index, trace=row_trace)
            w.writerow(out)
            # Rich per-stage trace (post-mortem CHARGE 5).
            trace.write(i, output=out, decision=row_trace)
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
