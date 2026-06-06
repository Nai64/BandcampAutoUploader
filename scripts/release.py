"""
Publish a new release of Bandcamp Auto Uploader.

Creates a GitHub release with the version folder artifacts (standalone EXE
+ installer for every architecture that can be built).

Requires:
  - ``gh`` CLI 2.x (authenticated to ``Nai64/BandcampAutoUploader``)
  - ``git``
  - matching Python interpreters for the arches you want to ship

Usage::

    # publish the current version
    python scripts/release.py

    # bump to a new version and publish
    python scripts/release.py 3.1.0

    # preview only – no files modified, no network calls
    python scripts/release.py --dry-run

    # skip all confirmation prompts (for automation)
    python scripts/release.py --yes
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run *cmd* and stream output; raise on non-zero return."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def _check_deps() -> None:
    """Fail early if required tools are missing."""
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[FAIL] gh CLI not found – install from https://cli.github.com/")
        sys.exit(1)

    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[FAIL] git not found")
        sys.exit(1)


def _read_version() -> str:
    """Return the ``__version__`` string from the source-of-truth module."""
    sys.path.insert(0, str(ROOT))
    from bandcamp_auto_uploader import __version__  # noqa: E402
    return __version__


def _bump_version(new_version: str | None, dry_run: bool) -> str | None:
    """If *new_version* is given, run ``set_version.py`` with it.

    Returns the version that was set, or ``None`` if the version stays
    as-is (current version unchanged).
    """
    if new_version is None:
        return None

    cmd = [sys.executable, "scripts/set_version.py", new_version]
    print(f"\n  Bumping version to {new_version} …")
    if not dry_run:
        _run(cmd, cwd=str(ROOT))
    return new_version


def _verify_clean_tree(dry_run: bool) -> None:
    """Abort if the working tree has uncommitted changes (unless dry-run)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, check=True, cwd=str(ROOT),
    )
    if result.stdout.strip() or result.stderr.strip():
        if not dry_run:
            print("[FAIL] Working tree has uncommitted changes. Commit or stash them first.")
            sys.exit(1)
        print("  [dry-run] Working tree is dirty - would abort.")


def _build(version: str, dry_run: bool) -> None:
    """Build all available arches with installers."""
    cmd = [sys.executable, "scripts/build_gui.py", "--all", "--installer"]
    print(f"\n  Building all arches with installers …")
    if dry_run:
        print(f"  [dry-run] Would run: $ {' '.join(cmd)}")
        print(f"  [dry-run] Expected output:  dist/BandcampAutoUploader-V{version}/*")
        return
    _run(cmd, cwd=str(ROOT))


def _commit_version_bump(version: str, dry_run: bool) -> bool:
    """Commit the files touched by ``set_version.py``.

    Returns ``True`` if there was anything to commit.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, check=True, cwd=str(ROOT),
    )
    modified = result.stdout.strip()
    if not modified:
        return False

    if dry_run:
        print(f"  [dry-run] Would commit:\n{modified}")
        return True

    _run(["git", "add", "-A"], cwd=str(ROOT))
    _run(["git", "commit", "-m", f"Release v{version}"], cwd=str(ROOT))
    return True


def _push(version: str, dry_run: bool) -> None:
    """Push the commit and tag to ``origin``."""
    if dry_run:
        print(f"  [dry-run] Would push commit + tag v{version} to origin")
        return
    _run(["git", "push", "origin"], cwd=str(ROOT))
    _run(["git", "push", "origin", f"v{version}"], cwd=str(ROOT))


def _create_github_release(version: str, dry_run: bool) -> None:
    """Create a GitHub release via ``gh`` and upload build artifacts."""
    version_folder = f"dist/BandcampAutoUploader-V{version}"
    artifacts = str(ROOT / version_folder / "*")

    cmd = [
        "gh", "release", "create",
        f"v{version}",
        "--title", f"v{version}",
        "--generate-notes",
        artifacts,
    ]

    if dry_run:
        print(f"  [dry-run] Would run: $ {' '.join(cmd)}")
        print(f"  [dry-run] Uploads: {version_folder}/* -> release v{version}")
        return

    print(f"\n  Creating GitHub release v{version} …")
    _run(cmd, cwd=str(ROOT))
    print(f"  Release URL: https://github.com/Nai64/BandcampAutoUploader/releases/tag/v{version}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a new release of Bandcamp Auto Uploader.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "version", nargs="?", default=None,
        help="New version to publish (e.g. 3.1.0). Defaults to current.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would happen without changing anything.",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip all confirmation prompts.",
    )
    args = parser.parse_args()

    _check_deps()

    # ── read current version ────────────────────────────────────────
    current = _read_version()
    print(f"\n  Current version : {current}")

    # ── verify clean tree BEFORE bumping ─────────────────────────────
    # (otherwise the bump itself dirties the tree and we can't tell
    #  what is user-introduced vs. set_version.py changes)
    _verify_clean_tree(args.dry_run)

    # ── bump? ────────────────────────────────────────────────────────
    requested = _bump_version(args.version, args.dry_run)
    version = requested or current

    print(f"  Release version : {version}")

    if not args.yes and not args.dry_run:
        answer = input("\n  Proceed with this release? [y/N] ").strip().lower()
        if answer != "y":
            print("  Aborted.")
            return 1

    # ── build ────────────────────────────────────────────────────────
    _build(version, args.dry_run)

    # ── commit + tag ─────────────────────────────────────────────────
    committed = _commit_version_bump(version, args.dry_run)
    if committed:
        msg = "committed" if not args.dry_run else "would commit"
        print(f"  Version bump {msg}.")

    # ── push ─────────────────────────────────────────────────────────
    _push(version, args.dry_run)
    print(f"  Tag v{version} pushed.")

    # ── GitHub release ───────────────────────────────────────────────
    _create_github_release(version, args.dry_run)

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
