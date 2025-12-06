"""
Steam Utilities Module

Centralized Steam installation type detection to avoid redundant subprocess calls.
"""

import logging
import subprocess
import shutil
from typing import Tuple

logger = logging.getLogger(__name__)


def detect_steam_installation_types() -> Tuple[bool, bool]:
    """
    Detect Steam installation types at startup.

    Performs detection ONCE and returns results to be cached in SystemInfo.

    Returns:
        Tuple[bool, bool]: (is_flatpak_steam, is_native_steam)
    """
    is_flatpak = _detect_flatpak_steam()
    is_native = _detect_native_steam()

    logger.info(f"Steam installation detection: Flatpak={is_flatpak}, Native={is_native}")

    return is_flatpak, is_native


def _detect_flatpak_steam() -> bool:
    """Detect if Steam is installed as a Flatpak."""
    try:
        # First check if flatpak command exists
        if not shutil.which('flatpak'):
            return False

        # Verify the app is actually installed (not just directory exists)
        result = subprocess.run(
            ['flatpak', 'list', '--app'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Suppress stderr
            text=True,
            timeout=5
        )

        if result.returncode == 0 and 'com.valvesoftware.Steam' in result.stdout:
            logger.debug("Flatpak Steam detected")
            return True

    except Exception as e:
        logger.debug(f"Error detecting Flatpak Steam: {e}")

    return False


def _detect_native_steam() -> bool:
    """Detect if native Steam installation exists."""
    try:
        # Check for common Steam paths
        import os
        steam_paths = [
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/root")
        ]

        for path in steam_paths:
            if os.path.exists(path):
                logger.debug(f"Native Steam detected at: {path}")
                return True

    except Exception as e:
        logger.debug(f"Error detecting native Steam: {e}")

    return False
