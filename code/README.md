# Agent — HackerRank Orchestrate (May 2026)

Multi-stage support-ticket triage agent. Reads `support_tickets/support_tickets.csv` (29 rows) and writes predictions to `support_tickets/output.csv` plus a per-row decision trace at `code/run_trace.jsonl`.

## Run

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r code/requirements.txt
cp .env.example .env  # set ANTHROPIC_API_KEY
./.venv/Scripts/python.exe -m code.main
```

This writes `support_tickets/output.csv` (29 data rows + header).

To validate against the labelled sample first:

```bash
./.venv/Scripts/python.exe -m code.eval_on_sample
```

## Architecture (8 stages)

| # | Stage | Type | Notes |
|---|---|---|---|
| 0 | Preprocess | deterministic | strip + curly-quote / CRLF normalize, secret-shape redaction, Company canonicalization |
| 1 | Safety triage | deterministic regex + keywords | sets `injection_detected`, `high_risk`, `outage_pattern`, `action_impossible`, `billing_request`, `oos_pleasantry`, `vuln_disclosure_shape` |
| 2 | Domain routing | 1 LLM call (only when `Company=None`) | falls back to keyword heuristic on LLM failure |
| 3 | Request-type classification | 1 LLM call | shorts to `invalid` for OOS pleasantries / empty issues |
| 4 | BM25 retrieval | deterministic | corpus-wide unicode tokenizer, sorted file iteration, `index.md` filtered, domain-scoped when `routed_domain != none` |
| 5 | Product-area assignment | deterministic | first-level alias map; Visa sub-doc heuristic; Claude L2 mapping; `index.md` → domain default |
| 6 | Abstain gate | deterministic | 8-rule precedence (injection → high_risk → outage → action_impossible → billing → routing-failed → request_type-failed → no-retrieval) |
| 7 | Response generation | ≤1 LLM call | grounded JSON output with `cited_doc_paths` membership check; refused / low-confidence / hallucinated-citation all flip to `escalated`; `response` post-processed through `SECRET_PATTERNS` |

Per-row LLM call budget is 5 attempts shared across Stages 2/3/7. On exhaustion, Stages 2/3 fall through to keyword heuristics; Stage 7 escalates the row.

## Determinism

Stages 0/1/4/5/6 are byte-stable across runs (sorted file iteration, regex-based normalization, deterministic alias map). Stages 2/3/7 are best-effort at `temperature=0` — Anthropic does not formally guarantee API determinism.

## Output schema

`output.csv`:

```
issue,subject,company,response,product_area,status,request_type,justification
```

- `status ∈ {replied, escalated}`
- `request_type ∈ {bug, product_issue, feature_request, invalid}`
- All values lowercase. (The bundled sample CSV uses Title Case headers + lowercase request_type; the lowercase template ships with the repo so this is the contract we picked. If the evaluator rejects, one find-and-replace flips to Title Case.)

## Tests

```bash
./.venv/Scripts/python.exe -m pytest tests/unit/
```

145 unit tests across all 8 stages plus 7 end-to-end propagation tests on a fixture corpus.

## Cost

~$0.20 per full 29-row run on Sonnet 4.5 at `temperature=0`. Worst-case wall clock ~3 min depending on API latency.

## Design rationale

See `docs/PLAN.md` (1598 lines, Rev 3 + Rev 4 + Rev 5 + Rev 5.1) for the per-stage failure modes, regex/keyword sets with positive/negative examples, the testing methodology cuts, and inquisitor-pass corrections (3 adversarial review rounds before scaffolding). Verified pattern assertions: 60 (Rev 4 + Rev 5) + 13 (Rev 5.1) before code; 145 unit tests after code.
