# hackathon-llm-support-agent

Multi-stage support-ticket triage agent built for the May 2026 HackerRank Orchestrate hackathon.

⭐ **Result: 65th place out of 12,885 participants (1,349 submissions)**

## Context

This was my submission for the 24-hour HackerRank Orchestrate challenge (May 1–2, 2026). The problem: build an agent that triages support tickets across three product corpora — HackerRank, Claude, and Visa — using only the provided support documentation, no external knowledge. The repo here is the work I built; the hackathon scaffold has been removed.

Full problem spec: [`docs/problem_statement.md`](./docs/problem_statement.md).

## What it does

Reads `support_tickets/support_tickets.csv` (29 rows) and writes `support_tickets/output.csv` with five columns per row:

| Column | Values |
|---|---|
| `status` | `replied`, `escalated` |
| `product_area` | most relevant support category / domain area |
| `response` | user-facing answer grounded in the corpus |
| `justification` | concise explanation of the routing/answering decision |
| `request_type` | `product_issue`, `feature_request`, `bug`, `invalid` |

## Architecture

Eight stages: preprocessing (deterministic), safety triage (deterministic regex + keywords), domain routing (1 LLM call, only when `Company=None`), request-type classification (1 LLM call), BM25 retrieval (deterministic), product-area assignment (deterministic alias map), abstain gate (deterministic, 8-rule precedence), and response generation (≤1 LLM call with grounded JSON output).

LLM calls are limited to stages 2, 3, and 7 — everything else is byte-stable across runs. Per-row LLM budget is 5 attempts shared across those three stages.

Full stage table, test instructions, and output schema: [`code/README.md`](./code/README.md).

## Engineering decisions worth calling out

**Determinism first.** Stages 0/1/4/5/6 are byte-stable (sorted file iteration, regex normalization, deterministic alias map). Stages 2/3/7 run at `temperature=0`. Cost is ~$0.20 per full 29-row run on Sonnet 4.5; worst-case wall clock is ~3 minutes.

**Reproducibility over cosmetic correction.** 28 of 29 rows are produced byte-for-byte by `python -m code.main`. Row 29 ships with a documented hallucination: the Stage 7 LLM confidently asserts that a US Virgin Islands merchant requiring a $10 minimum "violates Visa's rules" — the cited doc (line 202 of `data/visa/support.md`) explicitly names US Virgin Islands as an exception territory where the $10 minimum is permitted. I tried a jurisdictional-sensitivity prompt addition; it prevented the hallucination on row 29 but caused row 5 to escalate defensively. Net regressive. I kept the reproducible-but-wrong output and disclosed it rather than ship a prompt fix that broke other rows. Full disclosure and scoring trade-off analysis: [`docs/verification_findings.md`](./docs/verification_findings.md).

**Explicit abstain gate with precedence order.** The 8-rule gate fires in fixed order: injection → high_risk → outage → action_impossible → billing → routing-failed → request_type-failed → no-retrieval. Escalation is the architecturally-correct fallback when grounding fails — the gate makes that explicit rather than letting the response-generation stage decide.

**Tests written before code.** 145 unit tests across all 8 stages plus 7 end-to-end propagation tests on a fixture corpus. Tests were written per the TDD workflow documented in `docs/PLAN.md` before the stages were implemented. See [`code/README.md`](./code/README.md) for the test invocation.

## Results

12 escalated / 17 replied on the 29-row test set. Of the 17 replied rows: 14 verified grounded against the cited corpus document, 3 are templated out-of-scope responses (request type `invalid`), 1 known hallucination (row 29, disclosed above).

## Run it

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r code/requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
./.venv/Scripts/python.exe -m code.main
```

See [`code/README.md`](./code/README.md) for the full invocation, sample validation, and test commands.

## Repo layout

```
.
├── code/              # Agent implementation (8-stage pipeline)
├── data/              # Support corpora (HackerRank, Claude, Visa)
├── docs/              # Design rationale, plan, verification findings
└── support_tickets/   # Input CSV, sample CSV, output CSV
```

## Further reading

- [`code/README.md`](./code/README.md) — architecture table, run commands, output schema, test invocation, cost
- [`docs/PLAN.md`](./docs/PLAN.md) — 1598-line design rationale (Rev 3/4/5/5.1): per-stage failure modes, regex/keyword sets, testing methodology, adversarial review rounds
- [`docs/verification_findings.md`](./docs/verification_findings.md) — pre-submission verification pass: hallucination disclosure, reproducibility refit, scoring trade-offs
- [`docs/problem_statement.md`](./docs/problem_statement.md) — full problem spec, input/output schema, allowed values
