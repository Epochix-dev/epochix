#!/usr/bin/env python
"""Print one version's CHANGELOG section, for its GitHub release notes.

    python scripts/release_notes.py 0.7.20 > notes.md

Every GitHub release was published with an empty body — 136 of them — so the
"Latest release" link on the repository page opened a page with a .vsix and
nothing else. The notes already exist in CHANGELOG.md; the release workflow
now publishes the version's section as the release body (release.yml), and
this script is what extracts it. Exits 1 when the version has no section, so a
release cannot go out without notes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(version: str, text: str | None = None) -> str | None:
    """The body of ``## [version]`` up to the next version heading, or None."""
    text = (text if text is not None else CHANGELOG.read_text(encoding="utf-8")).replace(
        "\r\n", "\n"
    )
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n", re.M)
    m = heading.search(text)
    if m is None:
        return None
    rest = text[m.end() :]
    nxt = re.search(r"^## \[", rest, re.M)
    # Link-reference definitions ("[0.3.0]: https://...") sit at the end of the
    # file and are not part of the last section's notes.
    body = rest[: nxt.start()] if nxt else re.split(r"^\[[^\]]+\]: ", rest, maxsplit=1, flags=re.M)[0]
    body = body.strip().removesuffix("---").strip()
    return body or None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py VERSION", file=sys.stderr)
        return 2
    version = argv[0].removeprefix("v")
    body = section(version)
    if body is None:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    # Bytes, not text: the notes are UTF-8 (em dashes, arrows) and a Windows
    # pipe would encode them as cp1252 and fail on the first arrow.
    sys.stdout.buffer.write((body + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
