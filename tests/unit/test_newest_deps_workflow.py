"""The weekly job really runs the newest versions, and a red run is seen.

Every other job installs from uv.lock, so a step that lost its upgrade would
still pass, and would be testing the lock under a name that says otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[2]
TEXT = (ROOT / ".github" / "workflows" / "newest-deps.yml").read_text(encoding="utf-8")
JOBS: dict[str, Any] = yaml.safe_load(TEXT)["jobs"]
UPGRADE = "uv lock --upgrade"


def _commands(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def _test_files(job: dict[str, Any]) -> set[str]:
    return set(re.findall(r"tests/[\w/]+\.py", "\n".join(_commands(job))))


def test_it_runs_on_a_schedule_and_on_demand() -> None:
    assert "cron:" in TEXT
    assert "workflow_dispatch:" in TEXT


def test_every_job_that_runs_tests_upgrades_the_lock_first() -> None:
    testing = {name: job for name, job in JOBS.items() if "pytest" in "".join(_commands(job))}
    assert set(testing) == {"tests", "frameworks"}, "a job was renamed: this test checks nothing"
    for name, job in testing.items():
        commands = _commands(job)
        upgrade = next(i for i, command in enumerate(commands) if UPGRADE in command)
        first_test = next(i for i, command in enumerate(commands) if "pytest" in command)
        assert upgrade < first_test, name


def test_nothing_returns_to_the_lock_or_hides_a_failure() -> None:
    for flag in ("--frozen", "--locked", "|| true", "continue-on-error"):
        assert flag not in TEXT, flag


def test_the_upgraded_lock_is_never_committed() -> None:
    for command in ("git commit", "git push", "contents: write"):
        assert command not in TEXT, command


def test_the_frameworks_job_runs_what_ci_runs() -> None:
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    expected = _test_files(ci["jobs"]["integrations"])
    assert expected, "ci.yml's integrations job names no test files any more"
    assert _test_files(JOBS["frameworks"]) == expected


def test_a_red_run_of_any_job_is_reported() -> None:
    report = JOBS["report"]
    assert set(report["needs"]) == set(JOBS) - {"report"}
    assert "failure()" in report["if"]
    assert report["permissions"] == {"issues": "write"}


def test_dependabot_moves_the_lock() -> None:
    """The pip ecosystem edits pyproject and leaves uv.lock where it was."""
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    python = [u for u in config["updates"] if u["package-ecosystem"] in {"pip", "uv"}]
    assert len(python) == 1
    assert python[0]["package-ecosystem"] == "uv"
    # The floors in pyproject are a promise to users, not the latest release.
    assert python[0]["versioning-strategy"] == "increase-if-necessary"
