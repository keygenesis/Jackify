"""
TTW-Compatible Modlists Configuration

Defines which Fallout New Vegas modlists support Tale of Two Wastelands.
This whitelist determines when Jackify should offer TTW installation after
a successful modlist installation.
"""

TTW_COMPATIBLE_MODLISTS = {
    # Exact modlist names that support/require TTW
    "exact_matches": [
        "Begin Again",
        "Uranium Fever",
        "The Badlands",
        "Wild Card TTW",
    ],

    # Pattern matching for modlist names (regex)
    "patterns": [
        r".*TTW.*",  # Any modlist with TTW in name
        r".*Tale.*Two.*Wastelands.*",
    ]
}


def is_ttw_compatible(modlist_name: str) -> bool:
    """Check if modlist name matches TTW compatibility criteria

    Args:
        modlist_name: Name of the modlist to check

    Returns:
        bool: True if modlist is TTW-compatible, False otherwise
    """
    import re

    # Check exact matches
    if modlist_name in TTW_COMPATIBLE_MODLISTS['exact_matches']:
        return True

    # Check pattern matches
    for pattern in TTW_COMPATIBLE_MODLISTS['patterns']:
        if re.match(pattern, modlist_name, re.IGNORECASE):
            return True

    return False
