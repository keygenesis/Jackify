"""
Utilities for detecting Nexus Premium requirement messages in engine output.
"""

from __future__ import annotations

_KEYWORD_PHRASES = (
    "buy nexus premium",
    "requires nexus premium",
    "requires a nexus premium",
    "nexus premium is required",
    "nexus premium required",
    "nexus mods premium is required",
    "manual download",  # Evaluated with additional context
)


def is_non_premium_indicator(line: str) -> tuple[bool, str | None]:
    """
    Return True if the engine output line indicates a Nexus non-premium scenario.

    Args:
        line: Raw line emitted from the jackify-engine process.

    Returns:
        Tuple of (is_premium_error: bool, matched_pattern: str | None)
    """
    if not line:
        return False, None

    normalized = line.strip().lower()
    if not normalized:
        return False, None

    # Direct phrase detection
    for phrase in _KEYWORD_PHRASES[:6]:
        if phrase in normalized:
            return True, phrase

    # Manual download + Nexus URL implies premium requirement in current workflows.
    if "manual download" in normalized and ("nexusmods.com" in normalized or "nexus mods" in normalized):
        return True, "manual download + nexusmods.com"

    return False, None


