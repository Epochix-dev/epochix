"""No shell example in the docs may chain commands with ``&&``.

Windows PowerShell 5.1 — the one that ships with Windows — rejects ``&&`` as a
parse error. CONTRIBUTING.md opened with ``cd frontend && npm ci && npm test``,
so a Windows contributor's first command failed before anything ran. One
command per line works in every shell.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_SHELL_FENCES = {"", "bash", "sh", "shell", "console", "powershell", "ps1", "pwsh", "bat", "cmd"}
_FENCE = re.compile(r"^ {0,4}```([\w-]{0,32})[^\n]{0,64}\n(.*?)^ {0,4}```", re.M | re.S)
_INLINE_CODE = re.compile(r"`([^`\n]{1,200})`")


def _markdown_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    # The changelog records what past releases did, quoting them as they were.
    return [REPO / p for p in listed if Path(p).name != "CHANGELOG.md"]


def test_the_scan_has_something_to_scan() -> None:
    names = {p.name for p in _markdown_files()}
    assert {"README.md", "CONTRIBUTING.md", "AGENTS.md", "RELEASING.md"} <= names


def test_no_shell_example_chains_with_and_and() -> None:
    offenders: list[str] = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in _FENCE.finditer(text):
            if match.group(1).lower() in _SHELL_FENCES and "&&" in match.group(2):
                offenders.append(f"{path.relative_to(REPO)}: fenced {match.group(1) or 'block'}")
        for match in _INLINE_CODE.finditer(text):
            code = match.group(1)
            # A command in inline code (`git tag … && git push …`), not prose
            # that names the operator itself (`&&`).
            if "&&" in code and code.strip() != "&&":
                offenders.append(f"{path.relative_to(REPO)}: `{code}`")
    assert not offenders, "shell examples chaining with &&:\n" + "\n".join(offenders)
