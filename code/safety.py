"""Stage 1 — Safety / Adversarial Triage.

Patterns from docs/PLAN.md Rev 4 §1 (corrected by Rev 5 §9 + Rev 5.1 §1) +
Rev 5 §4 BILLING (Rev 5.1 §2 extension) + Rev 5.1 §3 OUTAGE +
safety-tuning branch §A (financial-duress phrases removed from HIGH_RISK).

Change A (safety-tuning): removed "urgent cash" / "need cash" / "cash
advance" cluster from HIGH_RISK_KEYWORDS.  These phrases fire on row 22
("Urgent need for cash"), a Visa travel-support question grounded in the
GCAS corpus.  Urgency alone without a fraud co-signal ("stolen", "fraudulent",
"compromised", "phishing") is not a high-risk indicator.  Explicit fraud /
identity-theft phrases ("stolen account", "identity theft", "fraudulent
charge", etc.) remain and still catch row 16.
"""
import re

INJECTION_PATTERNS = [
    # 1. Override directives — "ignore previous instructions" etc.
    re.compile(
        r"\b(?:ignore|disregard|forget)\s+"
        r"(?:all\s+|any\s+|the\s+|your\s+|my\s+|previous\s+|prior\s+|above\s+)*"
        r"(?:instructions?|rules?|prompts?|system|directives?)\b",
        re.IGNORECASE,
    ),
    # 2. Role/system extraction (Rev 5 §9 broadened + post-mortem CHARGE 6)
    re.compile(
        r"\b(?:reveal|show|print|output|tell|describe|explain|share|"
        r"dump|display|paste|repeat|echo|recite|disclose|expose|leak|"
        r"what\s+is|give\s+me)\s+(?:me\s+|us\s+)?"
        r"(?:your|the)\s+"
        r"(?:system\s+prompt|instructions|internal\s+rules|hidden\s+rules|prompt)\b",
        re.IGNORECASE,
    ),
    # 3. Multilingual extraction
    re.compile(
        r"(?:r[e\xe8]gles\s+internes|reglas\s+internas|"
        r"instructions?\s+internes|prompt\s+syst[e\xe8]me|"
        r"affiche\s+toutes\s+les)",
        re.IGNORECASE,
    ),
    # 4. Destructive command shape
    re.compile(
        r"\b(?:rm\s+-rf|drop\s+table|"
        r"delete\s+(?:all|every)[\s\w]*files?|"
        r"format\s+(?:c:|disk))\b",
        re.IGNORECASE,
    ),
    # 5. Code/markup injection (post-mortem CHARGE 6: + markdown-image exfil)
    re.compile(
        r"(?:<\s*script\b|<\s*iframe\b|javascript:|on\w+\s*=|"
        r"!\[[^\]]*\]\(https?://[^)]+\))",
        re.IGNORECASE,
    ),
    # 6. Jailbreak (Rev 5 §9 narrowed: dropped developer/admin to fix over-fire)
    re.compile(
        r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+"
        r"(?:\w+\s+){0,3}?"
        r"(?:a\s+|an\s+|the\s+)?"
        r"(?:different|new|root|jailbreak|unrestricted|uncensored)\b",
        re.IGNORECASE,
    ),
]

# Rev 5.1 §3 — outage patterns, tightened. PLATFORM_NOUNS extended with
# domain-feature nouns (submissions, interviews, ...); FAILURE_VERBS made
# optional in A2 to catch verbless past tense ("interviews stopped").
SCOPE_QUALIFIERS = (
    r"(?:all|everything|everyone|nothing|none\s+of|whole|entire|"
    r"completely|totally|widespread)"
)
PLATFORM_NOUNS = (
    r"(?:site|website|server|service|platform|api|app|builder|system|"
    r"tool|dashboard|console|portal|client|"
    r"submissions?|interviews?|tests?|assessments?|editor|leaderboard|tab|"
    r"page|pages|feature|features)"
)
FAILURE_VERBS = r"(?:is|are|was|were|seems?|appears?|has\s+been|have\s+been)"
FAILURE_STATES = (
    r"(?:down|broken|offline|failing|not\s+working|unavailable|"
    r"stopped(?:\s+working)?|crashed|froze|failed)"
)

OUTAGE_PATTERNS = [
    # A1: scope qualifier + failure shape
    re.compile(
        rf"\b{SCOPE_QUALIFIERS}\b.{{0,40}}?\b{FAILURE_VERBS}\s+"
        rf"(?:\w+\s+){{0,3}}?{FAILURE_STATES}\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # A2: platform-noun + failure (verbs optional per Rev 5.1 §3)
    re.compile(
        rf"\b(?:\w+\s+){{0,2}}{PLATFORM_NOUNS}\s+"
        rf"(?:{FAILURE_VERBS}\s+)?{FAILURE_STATES}\b",
        re.IGNORECASE,
    ),
    # B: inverted polarity — "none of/nothing/no X ... is/are working"
    re.compile(
        rf"\b(?:none\s+of|nothing|no\s+\w+)\b.{{0,80}}?\b(?:is|are)\s+working\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # C: explicit outage terms
    re.compile(
        r"\b(?:total|complete|major|widespread)\s+outage\b|"
        r"\bservice\s+unavailable\b|"
        r"\b50[023]\s+(?:error|server\s+error)\b",
        re.IGNORECASE,
    ),
]

HIGH_RISK_KEYWORDS = [
    # account compromise
    "account compromised",
    "account hacked",
    "account hijacked",
    "account taken over",
    "stolen account",
    "unauthorized access",
    "someone else logged in",
    "didn't make this charge",
    # identity / PII (Rev 4: actual #16 phrasing)
    "identity theft",
    "stolen identity",
    "identity has been stolen",
    "my identity",
    "ssn leaked",
    "passport leaked",
    "credentials exposed",
    "leaked credentials",
    "exposed password",
    # fraud
    "fraudulent charge",
    "fraudulent transaction",
    "fraud on my",
    "scammed",
    "phishing",
    "phished",
    # vulnerability disclosure
    "security vulnerability",
    "security disclosure",
    "0day",
    "zero-day",
    "rce",
    "remote code execution",
    "sql injection in",
    "xss in",
    # NOTE: bare-word paraphrase fallbacks ("stolen", "fraud", "hijacked",
    # "unauthorized") were dropped in tuning iteration 1 — they over-fired on
    # legitimate FAQ-shape Visa tickets ("lost or stolen card") which the
    # corpus has direct answers for. Multi-word phrases above ("stolen
    # account", "stolen identity", "fraudulent charge", etc.) still catch
    # the actual fraud / identity-theft cases.
]

VULN_DISCLOSURE_KEYWORDS = [
    "security vulnerability",
    "security disclosure",
    "0day",
    "zero-day",
    "rce",
    "remote code execution",
    "sql injection in",
    "xss in",
]

ACTION_IMPOSSIBLE_KEYWORDS = [
    # admin/role escalation (Rev 4: covers #1; Rev 5.1: refined)
    "give me admin",
    "make me admin",
    "grant me admin",
    "admin access",
    "admin override",
    "bypass the rule",
    "skip verification",
    "restore my access immediately",
    # score / data manipulation (Rev 5: broaden to "my score" — covers #2)
    "my score",
    "manipulate my ranking",
    "boost my rank",
    "move me to the next round",
    # bans / merchant actions
    "ban this merchant",
    "blacklist this merchant",
    "block this merchant",
    # Post-pre-mortem fix (#3): "ban the seller" was missed; broaden
    "ban the seller",
    "ban this seller",
    "block the seller",
    "block this seller",
    "blacklist the seller",
    "force a refund",
    "refund without proof",
    "reverse the chargeback without",
    # account destruction
    "delete my account permanently",
    "wipe my account",
    "delete all my data",
    "erase everything",
    # destructive commands (Rev 5: covers #24; redundant with INJECTION_PATTERNS[3])
    "delete all files",
    "delete files from the system",
    # auth bypass
    "reset password without verification",
    "bypass 2fa",
    "disable mfa for me",
]

BILLING_KEYWORDS = [
    "refund me",
    "give me a refund",
    "give me the refund",
    "want a refund",
    "refund asap",
    "money back",
    "give me my money",
    "return my money",
    "cancel my subscription",
    "cancel subscription",
    "pause our subscription",
    "pause my subscription",
    "pause subscription",
    "stop my subscription",
    "end my subscription",
    "billing issue",
    "billing question",
    # Rev 5.1 §2 additions: dispute/chargeback (covers #19)
    "dispute a charge",
    "dispute charge",
    "dispute the charge",
    "dispute this charge",
    "chargeback",
    "incorrect charge",
    "wrong charge",
    "charged twice",
    "double-charged",
    "double billed",
    "billed twice",
    "downgrade my plan",
    "upgrade my plan",
]

# Post-pre-mortem fix: pleasantry detection had been too greedy on greeting
# prefixes ("Hi, please pause our subscription" was matching "hi,"). Restricted
# to thanks-only — those are the end-of-conversation pleasantries warranting
# a templated 'Happy to help' reply. Greetings ("hi", "hello") are almost
# always followed by a real ask in a support context.
_PLEASANTRY_PREFIXES = (
    "thanks",
    "thank you",
    "thank u",
)
_PLEASANTRY_MAX_LEN = 60


def _is_oos_pleasantry(text: str) -> bool:
    """Detect short, thanks-shaped issue bodies. Catches:
      - "thanks!"
      - "Thank you for helping me"
      - "thanks so much for the help"
    Does NOT catch:
      - "Hi, my account is locked"     (greeting + ask)
      - "Thanks, my issue is X"        (anti-trigger blocks request words)
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > _PLEASANTRY_MAX_LEN:
        return False
    low = stripped.lower()
    if not any(low.startswith(p) for p in _PLEASANTRY_PREFIXES):
        return False
    # Reject if the body carries a real request after the pleasantry.
    # Broader anti-trigger list per Phase-7 review (#14 'subscription' miss).
    request_triggers = (
        "password", "account", "login", "error", "broken", "?",
        "subscription", "refund", "cancel", "delete", "remove", "pause",
        "billing", "charge", "issue", "help with", "question about",
        "problem", "how do i", "how to",
    )
    if any(kw in low for kw in request_triggers):
        return False
    return True


# Kept for backwards-compatible imports; unused at runtime.
OOS_PLEASANTRY = re.compile(
    r"^\s*(?:hi|hello|hey|thanks?|thank\s+you|good\s+morning)\b.*",
    re.IGNORECASE,
)


def _any_kw(text: str, kws: list[str]) -> bool:
    low = text.lower()
    return any(kw in low for kw in kws)


def safety_triage(cleaned: dict, prior_flags: dict) -> dict:
    """Run Stage 1 patterns against the (already-redacted) Issue text.

    Reads ``cleaned['Issue_redacted']`` (NOT ``Issue``) per Rev 5.1 §4
    defense-in-depth. Returns a merged flag dict layered over ``prior_flags``.
    """
    text = (
        cleaned.get("Subject", "")
        + " "
        + cleaned.get("Issue_redacted", cleaned.get("Issue", ""))
    ).strip()
    flags = dict(prior_flags)
    flags["injection_detected"] = any(p.search(text) for p in INJECTION_PATTERNS)
    flags["outage_pattern"] = any(p.search(text) for p in OUTAGE_PATTERNS)
    flags["high_risk"] = _any_kw(text, HIGH_RISK_KEYWORDS)
    flags["vuln_disclosure_shape"] = _any_kw(text, VULN_DISCLOSURE_KEYWORDS)
    flags["action_impossible"] = _any_kw(text, ACTION_IMPOSSIBLE_KEYWORDS)
    flags["billing_request"] = _any_kw(text, BILLING_KEYWORDS)
    flags["oos_pleasantry"] = _is_oos_pleasantry(cleaned.get("Issue", ""))
    return flags
