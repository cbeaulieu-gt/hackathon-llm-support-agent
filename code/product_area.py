"""Stage 5 — Product Area assignment.

Maps the top retrieved doc's path to one of the closed label set used by the
sample CSV. Spec: docs/PLAN.md Rev 5 §1+§2+§3 (Visa sub-doc heuristic +
Claude L2 second-level mapping + index-file guard).
"""

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


def visa_product_area(top_doc_path: str) -> str:
    """Visa: distinguish travel_support vs general_support by path keywords."""
    p = top_doc_path.replace("\\", "/").lower()
    if "travel-support" in p or "travelers-cheques" in p:
        return "travel_support"
    return "general_support"


def product_area(top_doc_path: str | None) -> str:
    """Map data/<domain>/<subdir>/... to output product_area label, or '' if
    no doc was retrieved."""
    if not top_doc_path:
        return ""
    parts = top_doc_path.replace("\\", "/").split("/")
    try:
        i = parts.index("data")
        domain = parts[i + 1]
        rest = parts[i + 2 :]
    except (ValueError, IndexError):
        return ""
    if not rest:
        return ""
    first = rest[0]
    # Index file at top of domain (e.g. data/visa/index.md) → domain default
    if first.endswith(".md"):
        return DOMAIN_DEFAULT_AREA.get(domain, "")
    # Visa: sub-doc heuristic (overrides alias map)
    if domain == "visa":
        return visa_product_area(top_doc_path)
    # Claude with first='claude': descend to second-level subdir
    if (
        domain == "claude"
        and first == "claude"
        and len(rest) >= 2
        and not rest[1].endswith(".md")
    ):
        second = rest[1]
        return PRODUCT_AREA_ALIAS_L2.get(second, second.replace("-", "_"))
    # Default: first-level alias map
    return PRODUCT_AREA_ALIAS.get(first, first)
