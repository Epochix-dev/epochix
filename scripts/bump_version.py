#!/usr/bin/env python
"""Set the release version everywhere that carries it.

    python scripts/bump_version.py 0.7.11

Four files record the version and they must not drift apart:

* ``pyproject.toml`` is the source of truth and what PyPI publishes.
* ``uv.lock`` records the project version too, and only refreshes when uv next
  resolves — so bumping pyproject alone left the lock one release behind after
  every release, and someone (me) then committed "chore: sync uv.lock" a few
  hours later. Three of those landed in a single week before this existed.
* ``epochix-vscode/package.json`` is rewritten from the git tag at publish
  time, but the committed value is meant to sit at the last released version.
  It had drifted onto a 0.5.x line matching no tag at all.
* ``epochix-vscode/package-lock.json`` records the extension's own version
  twice (top level and ``packages[""]``). It sat at 0.5.76 through every
  release up to 0.7.10 while the manifest beside it moved on — found only
  because an unrelated ``npm install`` rewrote it.

CHANGELOG.md is deliberately NOT touched. What changed is not derivable from a
version number, and a generated entry would be exactly the kind of filler this
project refuses to ship.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _replace_once(path: pathlib.Path, pattern: str, replacement: str) -> None:
    """Rewrite exactly one match, or fail loudly.

    Deliberately strict: a silent zero-match would print success and leave the
    version behind, which is the failure this script exists to prevent.
    """
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"{path}: expected one match for {pattern!r}, found {count}")
    if new != text:
        path.write_text(new, encoding="utf-8")


def _set_lock_version(path: pathlib.Path, version: str) -> None:
    """Set the package's own version in an npm lockfile, formatting untouched.

    npm writes lockfiles as ``JSON.stringify(lock, null, 2) + "\\n"``, which
    ``json.dumps(indent=2)`` reproduces byte for byte, so a round trip changes
    nothing but the two fields. Line endings are preserved as found, because a
    checkout under ``core.autocrlf`` has CRLF on disk.
    """
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    lock = json.loads(raw)
    if "version" not in lock or "" not in lock.get("packages", {}):
        raise SystemExit(f"{path}: not an npm v2+ lockfile with a root package")
    lock["version"] = version
    lock["packages"][""]["version"] = version
    out = json.dumps(lock, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    path.write_bytes(out.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="the new version, e.g. 0.7.11")
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="skip `uv lock` (for a machine without uv)",
    )
    args = parser.parse_args(argv)

    version = args.version.lstrip("v")
    if not _SEMVER.match(version):
        raise SystemExit(f"not a version: {args.version!r}")

    _replace_once(
        ROOT / "pyproject.toml",
        r'(?m)^version = "[^"]+"',
        f'version = "{version}"',
    )
    print(f"  pyproject.toml            -> {version}")

    _replace_once(
        ROOT / "epochix-vscode" / "package.json",
        r'"version": "[^"]+"',
        f'"version": "{version}"',
    )
    print(f"  epochix-vscode/package.json -> {version}")

    _set_lock_version(ROOT / "epochix-vscode" / "package-lock.json", version)
    print(f"  epochix-vscode/package-lock.json -> {version}")

    if args.no_lock:
        print("  uv.lock                   -> skipped (--no-lock)")
    else:
        result = subprocess.run(["uv", "lock"], cwd=ROOT)
        if result.returncode != 0:
            raise SystemExit("uv lock failed — the lock is now behind pyproject")
        print(f"  uv.lock                   -> {version}")

    print(f"\nBumped to {version}. Write the CHANGELOG entry by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
