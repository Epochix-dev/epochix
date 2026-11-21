"""The summary the coverage job publishes, made from a real measurement.

`scripts/coverage_summary.py` exists to name code nothing executed. So this
measures a package that has some — a module never imported, a function never
called — with coverage itself, and reads what the script says about it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "coverage_summary.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    # When this suite is itself being measured, a child process starts
    # coverage on its own (`patch = ["subprocess"]`). The measurement made
    # here is a separate one, of a separate package, so it must not inherit
    # that.
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=str(cwd),
        env={**env, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


@pytest.fixture
def report(tmp_path: Path) -> Path:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "used.py").write_text(
        "def called():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def never_called():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    (package / "never_imported.py").write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("from pkg.used import called\n\ncalled()\n", encoding="utf-8")
    (tmp_path / ".coveragerc").write_text("[run]\nsource = pkg\n", encoding="utf-8")

    measured = _run("-m", "coverage", "run", "main.py", cwd=tmp_path)
    assert measured.returncode == 0, measured.stderr
    written = _run("-m", "coverage", "json", "-o", "coverage.json", cwd=tmp_path)
    assert written.returncode == 0, written.stderr
    return tmp_path / "coverage.json"


def test_it_names_what_nothing_executed(report: Path) -> None:
    totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
    # Guard: a measurement that covered everything would prove nothing below.
    assert 0 < totals["covered_lines"] < totals["num_statements"]

    done = _run(str(SCRIPT), str(report), "--measured", "one small package", cwd=report.parent)
    assert done.returncode == 0, done.stderr
    text = done.stdout

    assert (
        f"## Coverage: {totals['percent_covered']:.2f}% "
        f"({totals['covered_lines']} of {totals['num_statements']} statements"
    ) in text
    assert "Measured: one small package." in text

    never, low, functions = (
        text.split("### Files no test executed")[1].split("### Modules under")[0],
        text.split("### Modules under")[1].split("<details>")[0],
        text.split("<details>")[1],
    )
    assert never.startswith(": 1\n")
    assert "| `pkg/never_imported.py` | 2 |" in never
    assert "used.py" not in never

    # used.py ran 3 of its 6 statements: exactly half is not "under 50%".
    assert low.startswith(" 50%: 0\n")

    assert "| `pkg/used.py` | `never_called` | 3 |" in functions
    assert "`called`" not in functions
    # The file at 0% is listed once, whole, not again function by function.
    assert "never_imported" not in functions


def test_a_report_that_measured_nothing_is_an_error(tmp_path: Path) -> None:
    """An empty report would otherwise be published as "no file at 0%"."""
    empty = tmp_path / "coverage.json"
    empty.write_text(
        json.dumps({"files": {}, "totals": {"num_statements": 0, "covered_lines": 0}}),
        encoding="utf-8",
    )
    done = _run(str(SCRIPT), str(empty), cwd=tmp_path)
    assert done.returncode == 1
    assert done.stdout == ""
    assert "measured no statements" in done.stderr
