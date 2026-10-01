"""Nothing in the repository says which machine it was made on.

Two fixtures — a byte-exact Ultralytics capture and an offline W&B run — were
recorded from a scratch folder and committed with that folder's full path in
them: the Windows user name, the profile directory, the tool that owned the
folder. They are test data nobody reads, in a public repository, and in the
W&B case inside the wheel's test suite. A recorded log is exactly the kind of
file that carries this, so every tracked file is checked, binary ones too.

Record fixtures and demos from a neutral folder (the demo scripts do), and
switch a tool's machine metadata off rather than editing the result.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A user's profile on Windows, macOS or Linux, in either slash.
_MACHINE_PATH = re.compile(
    rb"[\\/]Users[\\/][A-Za-z0-9._-]{1,40}[\\/]"
    rb"|AppData[\\/](?:Local|Roaming)[\\/]"
    rb"|/home/[a-z_][a-z0-9_-]{0,30}/"
)
# Paths written out as documentation, not recorded from a machine.
_ALLOWED = (
    b"/home/runner/",  # GitHub Actions' own home, in workflow docs
    b"/home/user/",
    b"/Users/you/",
    b"\\Users\\you\\",
)


def _tracked() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    return [REPO / p.decode("utf-8") for p in listed if p]


def test_there_are_files_to_check() -> None:
    files = _tracked()
    assert len(files) > 300
    assert any(p.suffix == ".wandb" for p in files), "the binary fixture is not being scanned"


def test_no_tracked_file_carries_a_machine_path() -> None:
    offenders: list[str] = []
    for path in _tracked():
        if not path.is_file() or path == Path(__file__).resolve():
            continue
        blob = path.read_bytes()
        for match in _MACHINE_PATH.finditer(blob):
            around = blob[max(0, match.start() - 20) : match.end() + 40]
            if any(ok in around for ok in _ALLOWED):
                continue
            offenders.append(f"{path.relative_to(REPO)}: {around.decode('latin1')!r}")
            break
    assert not offenders, "\n".join(offenders)
