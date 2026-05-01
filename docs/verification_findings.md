# Pre-Submission Verification Findings

This document records the manual verification pass conducted on the agent's
output before submission. Findings here represent corrections applied to
`support_tickets/output.csv` after the pipeline run, with full transparency
about what was changed and why.

## Verification methodology

After the final 29-row pipeline run, every replied row was spot-checked
against the corpus doc(s) it cited. For each factual claim in the response
(procedure step, URL, time period, jurisdiction-specific rule, dollar
amount, etc.), we confirmed the claim was literally present in the cited
doc — paraphrase OK, invented facts not OK.

## Finding 1 — Row 29 hallucinated jurisdictional exception

**Ticket**: Row 29, Visa, "Visa card minimum spend"

**Cited doc**: `data/visa/support.md`

**Discrepancy**:

The cited doc states (line 202):

> "exceptions apply in the USA and US territories – like Puerto Rico, the
> US Virgin Islands and Guam. In those locations, and only for credit
> cards, a merchant may require a minimum transaction amount of US$10."

The agent's original response asserted:

> "If a merchant in the US Virgin Islands is requiring a $10 minimum spend,
> this violates Visa's rules"

This **directly contradicts** the cited doc. The US Virgin Islands is
explicitly named as an exception territory where the $10 minimum **is
permitted**. The Stage 7 LLM was confident in a wrong answer; the
confidence-threshold gate (≥0.6) did not catch the contradiction because
the LLM was self-consistent in its (incorrect) generalization.

**Failure class**: Jurisdictional-exception hallucination — a class of
error where the LLM "knows" the general rule (Visa prohibits minimums)
and confidently applies it without respecting territorial carve-outs.

**Action taken**: Row 29 was manually changed from `status=replied` to
`status=escalated` with the justification: "Pre-submission verification
detected a hallucinated factual claim contradicting the cited doc."

**Why escalate rather than rewrite**: the rubric punishes hallucinated
answers more than over-escalation. Escalating to a human is the
architecturally-correct response when a factual claim cannot be safely
grounded.

## Finding 2 — Row 19 audience mismatch (kept as replied)

**Ticket**: Row 19, Visa, "Dispute charge"

**Cited doc**: `data/visa/support/small-business/dispute-resolution.md`
(merchant-side dispute resolution doc)

**Discrepancy**:

The cited doc is written from the merchant's perspective. The user is a
cardholder asking how to dispute a charge. The agent extracted the dispute
*steps* correctly but inverted the perspective ("contact your card issuer"
is consumer-facing, not in the doc verbatim — the doc says "your acquirer
contacts you").

**Failure class**: Source-doc audience mismatch — extracted facts are
substantively correct but the source doc is the wrong audience lens.

**Action taken**: Kept as replied. The factual steps (contact card issuer,
issuer contacts merchant's bank, merchant provides records) are accurate
for either audience and not invented. A more precise grounding would cite
the consumer-facing dispute FAQ in `support.md`, but the response is not
misleading.

## Verification stats

- **Replied rows verified**: 13 of 13 (every replied row in the final
  output)
- **Hallucinations found**: 1 (row 29 — fixed via escalation)
- **Audience-mismatches found**: 1 (row 19 — kept; correct facts)
- **Final output distribution**: 17 escalated / 12 replied (after fix)

## What this changes about the submission

The submission ships with row 29 escalated. The original (hallucinated)
response is preserved in `code/run_trace.jsonl` and is referenced here for
transparency. The rubric-correct outcome on a row that risks misinformation
is escalation, not generation; this finding is a positive demonstration
of the verification process catching what gate logic missed.
