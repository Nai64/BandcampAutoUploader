"""
Publish a new release of Bandcamp Auto Uploader via python-semantic-release.

Usage::

    # preview the next version
    python scripts/release.py --dry-run

    # publish (stamp + build + tag + push + GitHub release)
    python scripts/release.py

    # skip confirmation prompts (for automation)
    python scripts/release.py --yes
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Load ``.env`` and map ``TOKEN`` → ``GITHUB_TOKEN`` for PSR."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)

    if "TOKEN" in os.environ and "GITHUB_TOKEN" not in os.environ:
        os.environ["GITHUB_TOKEN"] = os.environ["TOKEN"]


def _read_version() -> str:
    sys.path.insert(0, str(ROOT))
    from bandcamp_auto_uploader import __version__
    return __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a new release of Bandcamp Auto Uploader.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Preview without changing anything.",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip all confirmation prompts.",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the build step (use existing artifacts).",
    )
    parser.add_argument(
        "--skip-push", action="store_true",
        help="Skip git push and VCS release creation.",
    )
    args = parser.parse_args()

    _load_env()

    cmd = ["python", "-m", "semantic_release", "-v"]
    if args.dry_run:
        cmd.append("--noop")

    cmd.append("version")

    if args.skip_build or args.dry_run:
        cmd.append("--skip-build")

    if not args.skip_push and not args.dry_run:
        cmd.append("--push")

    if not args.dry_run and not args.yes:
        print(f"  Current version : {_read_version()}")
        if input("  Proceed with release? [y/N] ").strip().lower() != "y":
            print("  Aborted.")
            return 1

    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    sys.exit(main())