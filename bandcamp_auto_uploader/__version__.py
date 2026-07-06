"""Single source of truth for the application version.

Other files (config/pyproject.toml, scripts/version.inc, README.md) are kept
in sync by python-semantic-release when publishing.  To bump locally::

    semantic-release version --noop   # preview
    semantic-release version          # stamp + tag + push
"""
from __future__ import annotations

import re

__version__ = "3.6.0"
__version_label__ = "3.6.0"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?$")


def is_valid_version(version: str) -> bool:
    """Return True if the given string looks like a sensible version token."""
    return bool(_VERSION_RE.match(version))


def full_version() -> str:
    """Return the human-readable version label."""
    return __version_label__


def numeric_prefix() -> str:
    """Return the leading integer portion of the version (e.g. '3' from '3.0.0')."""
    match = re.match(r"^(\d+)", __version__)
    return match.group(1) if match else __version__
