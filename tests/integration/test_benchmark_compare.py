"""The comparison reads the trees it is given, and fails a slower one.

These run the real script over real copies of the source. The tolerances are far
wider than the job's, because so few lines are measured.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).parents[2]
SCRIPT = REPO / "scripts" / "compare_benchmarks.py"

SLOW_DOWN = """

_read = UniversalParser.parse_line


def _slowly(self, line, ctx):
    sum(range(20000))
    return _read(self, line, ctx)


UniversalParser.parse_line = _slowly
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compare_benchmarks", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(at: Path) -> Path:
    src = at / "src"
    shutil.copytree(
        REPO / "src",
        src,
        ignore=shutil.ignore_patterns("__pycache__", "_frontend", "*.egg-info"),
    )
    return src


def _compare(base: Path, head: Path, tolerance: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            f"--base-src={base}",
            f"--head-src={head}",
            "--rounds=1",
            "--lines=2000",
            f"--tolerance={tolerance}",
            "--ignore-targets",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_same_code_passes(tmp_path: Path) -> None:
    base = _tree(tmp_path / "base")
    done = _compare(base, REPO / "src", tolerance=0.9)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "universal" in done.stdout and "huggingface" in done.stdout, "nothing was compared"


def test_a_slower_parser_fails_by_name(tmp_path: Path) -> None:
    base = _tree(tmp_path / "base")
    slow = _tree(tmp_path / "slow")
    parser = slow / "epochix" / "parsers" / "universal.py"
    parser.write_text(parser.read_text(encoding="utf-8") + SLOW_DOWN, encoding="utf-8")

    done = _compare(base, slow, tolerance=0.5)

    assert done.returncode == 1, done.stdout + done.stderr
    row = next(line for line in done.stdout.splitlines() if line.startswith("universal"))
    assert "slower than base" in row


def test_a_tree_that_is_not_the_one_measured_is_refused(tmp_path: Path) -> None:
    """An installed copy winning the import would compare main with itself."""
    empty = tmp_path / "empty" / "src"
    empty.mkdir(parents=True)
    done = _compare(empty, REPO / "src", tolerance=0.9)
    assert done.returncode != 0
    assert "measured" in done.stderr.lower() or "failed" in done.stderr.lower()


@pytest.mark.parametrize(
    ("base", "head", "target", "said"),
    [
        (1000, 1000, 900, "ok"),
        (1000, 950, 900, "ok"),
        (1000, 899, None, "FAIL: more than 10% slower"),
        (1000, 899, 800, "FAIL: more than 10% slower"),
        # Close to base, but it is the change that crosses the target.
        (1000, 950, 960, "FAIL: below the target"),
        # Both below: the runner or main, not this change.
        (800, 790, 900, "warning: base and head"),
        (None, 500, 900, "ok: new"),
        (1000, None, 900, "FAIL: not measured"),
    ],
)
def test_the_verdict(base: int | None, head: int | None, target: int | None, said: str) -> None:
    assert _load().verdict(base, head, target, 0.10).startswith(said)
