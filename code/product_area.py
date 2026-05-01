"""Stage 5 — Product Area assignment.

Maps the top retrieved doc's path to one of the closed label set used by the
sample CSV. Spec: docs/PLAN.md Rev 5 §1+§2+§3 (Visa sub-doc heuristic +
Claude L2 second-level mapping + index-file guard) + Stage 5 specificity fix
(low-specificity subdir avoidance + invalid/no-domain short-circuit).
"""
from __future__ import annotations

PRODUCT_AREA_ALIAS = {
    # data/hackerrank/<dir> → label
    "screen": "screen",
    "hackerrank_community": "community",
    "general-help": "general_support",
    "engage": "engage",
    "chakra": "chakra",
    "integrations": "integrations",
    "interviews": "interviews",
    "library": "library",
    "settings": "settings",
    "skillup": "skillup",
    "uncategorized": "uncategorized",
    # data/claude/<dir> → label
    "claude": "claude",
    "claude-api-and-console": "claude-api-and-console",
    "claude-code": "claude-code",
    "claude-desktop": "claude-desktop",
    "claude-for-education": "claude-for-education",
    "claude-for-government": "claude-for-government",
    "claude-for-nonprofits": "claude-for-nonprofits",
    "claude-in-chrome": "claude-in-chrome",
    "claude-mobile-apps": "claude-mobile-apps",
    "amazon-bedrock": "amazon-bedrock",
    "connectors": "connectors",
    "identity-management-sso-jit-scim": "identity-management-sso-jit-scim",
    "privacy-and-legal": "privacy",
    "pro-and-max-plans": "pro-and-max-plans",
    "safeguards": "safeguards",
    "team-and-enterprise-plans": "team-and-enterprise-plans",
    # data/visa/<dir> → label (overridden by visa_product_area for Visa)
    "support": "travel_support",
}

PRODUCT_AREA_ALIAS_L2 = {
    # data/claude/claude/<L2-subdir>/ → label
    "conversation-management": "conversation_management",
    "account-management": "account_management",
    "features-and-capabilities": "features_and_capabilities",
    "get-started-with-claude": "get_started_with_claude",
    "personalization-and-settings": "personalization_and_settings",
    "troubleshooting": "troubleshooting",
    "usage-and-limits": "usage_and_limits",
}

DOMAIN_DEFAULT_AREA = {
    "hackerrank": "general_support",
    "claude": "claude",
    "visa": "general_support",
}

# Subdirectories whose content is too generic to trust as a product_area
# signal. When top-1 falls in one of these for a given domain, Stage 5 will
# prefer the next top-K doc whose first-level subdir is NOT in this set.
# Visa and Claude are intentionally empty: their corpus structure doesn't
# exhibit the same release-notes / catch-all problem.
LOW_SPECIFICITY_SUBDIRS: dict[str, set[str]] = {
    "hackerrank": {"general-help", "uncategorized"},
    "claude": set(),
    "visa": set(),
}


def visa_product_area(top_doc_path: str) -> str:
    """Visa: distinguish travel_support vs general_support by path keywords.

    Args:
        top_doc_path: Normalized (forward-slash) path to the top retrieved doc.

    Returns:
        "travel_support" if the path contains travel-related keywords,
        otherwise "general_support".
    """
    p = top_doc_path.replace("\\", "/").lower()
    if "travel-support" in p or "travelers-cheques" in p:
        return "travel_support"
    return "general_support"


def _extract_subdir(path: str, domain: str) -> str:
    """Extract the first-level subdirectory under data/<domain>/ from a path.

    Args:
        path: Doc path (forward-slash normalized).
        domain: The routed domain (e.g. "hackerrank", "claude", "visa").

    Returns:
        The first path segment after data/<domain>/, or empty string if the
        path doesn't conform to that structure.
    """
    parts = path.replace("\\", "/").split("/")
    try:
        i = parts.index("data")
        # parts[i+1] is domain, parts[i+2] is the first subdir
        if parts[i + 1] != domain:
            return ""
        candidate = parts[i + 2] if len(parts) > i + 2 else ""
        # Index files at the domain root (e.g. "index.md") have no subdir
        return "" if candidate.endswith(".md") else candidate
    except (ValueError, IndexError):
        return ""


def _derive_product_area(path: str, domain: str) -> str:
    """Map data/<domain>/<subdir>/... to an output product_area label.

    This is the pure path-to-label translation, applied to whichever doc
    has been selected (top-1 or the low-specificity override candidate).

    Args:
        path: Doc path (may use backslashes — normalized internally).
        domain: The routed domain string.

    Returns:
        A product_area label string, or empty string when derivation fails.
    """
    if not path:
        return ""
    parts = path.replace("\\", "/").split("/")
    try:
        i = parts.index("data")
        domain_in_path = parts[i + 1]
        rest = parts[i + 2:]
    except (ValueError, IndexError):
        return ""
    if not rest:
        return ""
    first = rest[0]
    # Index file at top of domain (e.g. data/visa/index.md) → domain default
    if first.endswith(".md"):
        return DOMAIN_DEFAULT_AREA.get(domain_in_path, "")
    # Visa: sub-doc heuristic (overrides alias map)
    if domain_in_path == "visa":
        return visa_product_area(path)
    # Claude with first='claude': descend to second-level subdir
    if (
        domain_in_path == "claude"
        and first == "claude"
        and len(rest) >= 2
        and not rest[1].endswith(".md")
    ):
        second = rest[1]
        return PRODUCT_AREA_ALIAS_L2.get(second, second.replace("-", "_"))
    # Default: first-level alias map
    return PRODUCT_AREA_ALIAS.get(first, first)


def product_area(
    top_k_docs: list[dict],
    domain: str,
    request_type: str = "",
) -> str:
    """Derive the product_area label from the top-K retrieved docs.

    Implements two targeted fixes over the naive top-1 approach:

    Fix 1 — Low-specificity subdir avoidance: when top-1 falls in a known
    catch-all subdir (e.g. ``general-help`` or ``uncategorized`` for the
    ``hackerrank`` domain), scan the remaining top-K docs for one whose
    first-level subdir is NOT in that catch-all set and prefer it.

    Fix 2 — Invalid + no-domain short-circuit: when ``request_type`` is
    ``"invalid"`` and ``domain`` is ``"none"``, retrieval results are noise
    (BM25 searched the full corpus on an OOS query). Return empty string
    rather than a spurious label.

    Args:
        top_k_docs: Ordered list of dicts with at least a ``"path"`` key, as
            returned by ``retrieval.retrieve()``. May be empty.
        domain: The routed domain string (e.g. ``"hackerrank"``, ``"claude"``,
            ``"visa"``, or ``"none"``).
        request_type: The classified request type (e.g. ``"question"``,
            ``"invalid"``). Defaults to empty string (no special handling).

    Returns:
        A product_area label string, or ``""`` when no label can be reliably
        derived.
    """
    # Fix 2: OOS / invalid + no-domain → retrieval is noise, emit nothing
    if request_type == "invalid" and domain == "none":
        return ""

    if not top_k_docs:
        return ""

    top_1_path = top_k_docs[0]["path"]
    top_1_subdir = _extract_subdir(top_1_path, domain)
    low_spec = LOW_SPECIFICITY_SUBDIRS.get(domain, set())

    # Fix 1: if top-1 is in a low-specificity subdir, search the rest of
    # top-K for a doc with a higher-specificity subdir and use that instead.
    if top_1_subdir in low_spec:
        for candidate in top_k_docs[1:]:
            cand_path = candidate["path"]
            cand_subdir = _extract_subdir(cand_path, domain)
            if cand_subdir and cand_subdir not in low_spec:
                return _derive_product_area(cand_path, domain)
        # All top-K docs are in low-specificity subdirs; fall through to top-1
    return _derive_product_area(top_1_path, domain)
