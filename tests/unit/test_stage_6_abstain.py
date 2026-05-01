"""Stage 6 abstain gate tests. Spec: Rev 5 §10 (8-rule precedence)."""
from code.abstain import is_bug_bounty_doc, stage_6_decide


def _flags(**kw):
    base = {
        "injection_detected": False,
        "high_risk": False,
        "outage_pattern": False,
        "action_impossible": False,
        "billing_request": False,
        "domain_routing_failed": False,
        "request_type_classification_failed": False,
        "vuln_disclosure_shape": False,
    }
    base.update(kw)
    return base


def _doc(path):
    return {"path": path, "score": 5.0, "snippet": ""}


def test_injection_first():
    s, j = stage_6_decide(
        _flags(injection_detected=True, high_risk=True),
        3,
        [_doc("data/x/y/z.md")],
        "bug",
    )
    assert s == "escalated"
    assert "injection" in j.lower()


def test_high_risk_escalates():
    s, j = stage_6_decide(
        _flags(high_risk=True), 3, [_doc("data/x/y/z.md")], "bug"
    )
    assert s == "escalated"
    assert "high_risk" in j


def test_vuln_disclosure_with_bug_bounty_doc_replies():
    docs = [_doc("data/claude/safeguards/12119250-bug-bounty-program.md")]
    s, _ = stage_6_decide(
        _flags(high_risk=True, vuln_disclosure_shape=True),
        1, docs, "bug",
    )
    assert s == "replied"


def test_vuln_disclosure_without_bug_bounty_doc_escalates():
    """high_risk + vuln_disclosure_shape but top doc isn't bug-bounty → still escalate."""
    docs = [_doc("data/claude/screen/foo.md")]
    s, _ = stage_6_decide(
        _flags(high_risk=True, vuln_disclosure_shape=True),
        1, docs, "bug",
    )
    assert s == "escalated"


def test_outage_escalates():
    s, j = stage_6_decide(
        _flags(outage_pattern=True), 3, [_doc("x")], "bug"
    )
    assert s == "escalated"
    assert "outage" in j


def test_action_impossible_escalates():
    s, _ = stage_6_decide(
        _flags(action_impossible=True), 3, [_doc("x")], "bug"
    )
    assert s == "escalated"


def test_billing_no_doc_escalates():
    s, j = stage_6_decide(
        _flags(billing_request=True), 0, [], "product_issue"
    )
    assert s == "escalated"
    assert "billing" in j


def test_billing_with_doc_replies():
    s, _ = stage_6_decide(
        _flags(billing_request=True),
        1,
        [_doc("data/hackerrank/general-help/billing-faq.md")],
        "product_issue",
    )
    assert s == "replied"


def test_domain_routing_failed_escalates():
    s, _ = stage_6_decide(_flags(domain_routing_failed=True), 0, [], "bug")
    assert s == "escalated"


def test_no_retrieval_escalates_for_bug():
    s, _ = stage_6_decide(_flags(), 0, [], "bug")
    assert s == "escalated"


def test_no_retrieval_replies_for_invalid():
    """invalid rows with no retrieval should still reply (templated OOS)."""
    s, _ = stage_6_decide(_flags(), 0, [], "invalid")
    assert s == "replied"


def test_replied_default_with_doc():
    s, j = stage_6_decide(
        _flags(), 1, [_doc("data/claude/screen/foo.md")], "bug"
    )
    assert s == "replied"
    assert "foo.md" in j


def test_is_bug_bounty_doc_detection():
    assert is_bug_bounty_doc(
        "data/claude/safeguards/11427875-public-vulnerability-reporting.md"
    )
    assert is_bug_bounty_doc(
        "data/claude/safeguards/12119250-model-safety-bug-bounty-program.md"
    )
    assert not is_bug_bounty_doc("data/claude/screen/foo.md")
    assert not is_bug_bounty_doc(
        "data/claude/safeguards/9307344-responsible-use.md"
    )
