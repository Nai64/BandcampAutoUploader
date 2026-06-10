"""Single source of truth for the application version.

Other files (pyproject.toml, scripts/installer.iss, README.md badge) are kept
in sync via scripts/set_version.py. To bump the version, edit this file and
then run::

    python scripts/set_version.py

(or pass a new version directly)::

    python scripts/set_version.py 3.0.0b
    python scripts/set_version.py 4
"""
from __future__ import annotations

import re

__version__ = "3.3.1"
__version_label__ = "3.3.1"

_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*(?:(?:[ab]|rc)\d*)?$")


def is_valid_version(version: str) -> bool:
    """Return True if the given string looks like a sensible version token."""
    return bool(_VERSION_RE.match(version))


def full_version() -> str:
    """Return the human-readable version label (includes suffix if any)."""
    return __version_label__


def numeric_prefix() -> str:
    """Return the leading integer portion of the version (e.g. '3' from '3.0.0b')."""
    match = re.match(r"^(\d+)", __version__)
    return match.group(1) if match else __version__
