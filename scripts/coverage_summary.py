#!/usr/bin/env python3
"""Turn a coverage JSON report into the summary the CI job publishes.

The total is the least useful line of a coverage report. This project's
recurring bug is code that shipped without ever having run, so what gets
published is the list a reviewer can act on: the files nothing executed, the
modules mostly not executed, and the functions never entered.

Usage::

    coverage json -o coverage.json --fail-under=0
    python scripts/coverage_summary.py coverage.json >> "$GITHUB_STEP_SUMMARY"

It reports and never judges: the floor is `fail_under` in pyproject.toml, held
by `coverage report`. It exits non-zero only when the report measured nothing,
because an empty report would otherwise read as "no file at 0%".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# A module below this is listed by name.
LOW = 50.0
# A never-entered function shorter than this is left out of the list: a
# one-line `__repr__` is not what the list is for.
MIN_FUNCTION_STATEMENTS = 3


def _name(path: str) -> str:
    """`src\\epochix\\cli.py` and `src/epochix/cli.py` as `epochix/cli.py`."""
    posix = path.replace("\\", "/")
    return posix.split("src/", 1)[1] if "src/" in posix else posix


def _floor() -> float | None:
    """The `fail_under` that `coverage report` will hold, read as it reads it."""
    try:
        from coverage import Coverage
    except ImportError:
        return None
    value = Coverage().get_option("report:fail_under")
    return float(value) if isinstance(value, (int, float)) and value else None


def summarise(report: dict[str, Any], measured: str | None, floor: float | None) -> str:
    totals = report["totals"]
    files = sorted(
        (_name(path), data)
        for path, data in report["files"].items()
        if data["summary"]["num_statements"]
    )
    out: list[str] = []
    out.append(
        f"## Coverage: {totals['percent_covered']:.2f}% "
        f"({totals['covered_lines']} of {totals['num_statements']} statements, "
        f"{len(files)} files)"
    )
    out.append("")
    if measured:
        out.append(f"Measured: {measured}.")
    if floor is not None:
        out.append(f"Floor (`fail_under` in pyproject.toml): {floor:g}%.")
    out.append("")

    never = [(name, data) for name, data in files if data["summary"]["covered_lines"] == 0]
    out.append(f"### Files no test executed: {len(never)}")
    out.append("")
    if never:
        out.append("| File | Statements |")
        out.append("| --- | ---: |")
        out.extend(f"| `{name}` | {data['summary']['num_statements']} |" for name, data in never)
    else:
        out.append("None: every file with a statement in it had at least one executed.")
    out.append("")

    low = sorted(
        (data["summary"]["percent_covered"], name, data)
        for name, data in files
        if data["summary"]["covered_lines"] and data["summary"]["percent_covered"] < LOW
    )
    out.append(f"### Modules under {LOW:g}%: {len(low)}")
    out.append("")
    if low:
        out.append("| Module | Executed | Statements | Covered |")
        out.append("| --- | ---: | ---: | ---: |")
        out.extend(
            f"| `{name}` | {data['summary']['covered_lines']} "
            f"| {data['summary']['num_statements']} | {percent:.1f}% |"
            for percent, name, data in low
        )
    else:
        out.append("None.")
    out.append("")

    functions = [
        (name, function, data["summary"]["num_statements"])
        for name, file_data in files
        # A file at 0% is already listed whole, above.
        if file_data["summary"]["covered_lines"]
        for function, data in file_data.get("functions", {}).items()
        if function
        and data["summary"]["covered_lines"] == 0
        and data["summary"]["num_statements"] >= MIN_FUNCTION_STATEMENTS
    ]
    out.append(
        f"<details><summary>Functions never entered, in files that did run: "
        f"{len(functions)} (of {MIN_FUNCTION_STATEMENTS} statements or more)</summary>"
    )
    out.append("")
    if functions:
        out.append("| File | Function | Statements |")
        out.append("| --- | --- | ---: |")
        out.extend(f"| `{name}` | `{function}` | {count} |" for name, function, count in functions)
    else:
        out.append("None.")
    out.append("")
    out.append("</details>")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="output of `coverage json`")
    parser.add_argument("--measured", help="what was run, for the reader of the summary")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not report.get("files") or not report["totals"]["num_statements"]:
        print("coverage_summary: the report measured no statements", file=sys.stderr)
        return 1
    sys.stdout.write(summarise(report, args.measured, _floor()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
