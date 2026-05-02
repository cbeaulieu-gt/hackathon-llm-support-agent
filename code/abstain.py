"""Stage 6 — Abstain Gate.

Spec: docs/PLAN.md Rev 5 §10. Eight precedence rules; first match wins.
``justification`` carries the first-fired rule name. ``vuln_disclosure_shape``
+ bug-bounty top doc skips the high_risk escalation per Rev 5 §5.

Change B (safety-tuning): ``action_impossible`` is no longer an unconditional
escalation.  When retrieval surfaces at least one document AND neither
``injection_detected`` nor ``high_risk`` is also set, Stage 7 is given the
chance to craft a grounded reply that acknowledges the impossible action and
redirects to the documented legitimate path (e.g. "I cannot restore your
seat, but your IT admin can do this via…").  If Stage 7 cannot ground a
response it returns "Escalate to a human" and main.py propagates that back
to ``escalated`` — so the safety net is preserved.

Critical guard: ``injection_detected`` still wins unconditionally (rule 1),
and ``high_risk`` still wins (rule 2) before this carve-out is reached, so
rows 24 (delete-all-files injection) and any fraud+action-impossible combo
are not affected.
"""


def is_bug_bounty_doc(path: str) -> bool:
    """Detect that the retrieved doc is a bug-bounty / vulnerability-reporting page."""
    p = path.lower()
    return any(
        kw in p
        for kw in [
            "vulnerability-reporting",
            "bug-bounty",
            "bug_bounty",
            "public-vulnerability",
        ]
    )


def stage_6_decide(
    flags: dict,
    retrieval_count: int,
    top_k_docs: list,
    request_type: str,
) -> tuple[str, str]:
    """Returns ``(status, justification)``.

    Precedence (first match wins; Rev 5 §10):
      1. injection_detected
      2. high_risk (UNLESS vuln_disclosure_shape AND bug-bounty doc retrieved)
      3. outage_pattern
      4. action_impossible
      5. billing_request AND retrieval=0
      6. domain_routing_failed
      7. request_type_classification_failed
      8. retrieval=0 AND domain != none AND request_type != invalid
    Else: status=replied.
    """
    if flags.get("injection_detected"):
        return ("escalated", "Escalated: injection_detected")

    if flags.get("high_risk"):
        if (
            flags.get("vuln_disclosure_shape")
            and top_k_docs
            and is_bug_bounty_doc(top_k_docs[0]["path"])
        ):
            pass  # fall through to reply via grounded LLM call
        else:
            return ("escalated", "Escalated: high_risk")

    if flags.get("outage_pattern"):
        return ("escalated", "Escalated: outage_pattern")

    if flags.get("action_impossible"):
        # Change B: when corpus has relevant content and no higher-priority
        # safety flag is set (injection and high_risk already handled above),
        # allow Stage 7 to craft a "cannot do X, but here's how you can…"
        # reply grounded in the retrieved documents.  Without corpus content
        # there is nothing to say, so fall back to escalation.
        if top_k_docs:
            return (
                "replied",
                "Replied: action_impossible_with_corpus",
            )
        return ("escalated", "Escalated: action_impossible_no_corpus")

    if flags.get("billing_request") and retrieval_count == 0:
        return ("escalated", "Escalated: billing_request_no_doc")

    if flags.get("domain_routing_failed"):
        return ("escalated", "Escalated: domain_routing_failed")

    if flags.get("request_type_classification_failed"):
        return ("escalated", "Escalated: request_type_classification_failed")

    if (
        retrieval_count == 0
        and not flags.get("domain_routing_failed")
        and request_type != "invalid"
    ):
        return ("escalated", "Escalated: no_retrieval")

    if top_k_docs:
        basename = top_k_docs[0]["path"].rsplit("/", 1)[-1]
        return ("replied", f"Replied: grounded by {basename}")
    return ("replied", "Replied: templated OOS")
