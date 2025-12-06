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


def is_non_premium_indicator(line: str) -> bool:
    """
    Return True if the engine output line indicates a Nexus non-premium scenario.

    Args:
        line: Raw line emitted from the jackify-engine process.
    """
    if not line:
        return False

    normalized = line.strip().lower()
    if not normalized:
        return False

    # Direct phrase detection
    for phrase in _KEYWORD_PHRASES[:6]:
        if phrase in normalized:
            return True

    if "nexus" in normalized and "premium" in normalized:
        return True

    # Manual download + Nexus URL implies premium requirement in current workflows.
    if "manual download" in normalized and ("nexusmods.com" in normalized or "nexus mods" in normalized):
        return True

    return False


