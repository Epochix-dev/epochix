"""The benchmark job fails when the benchmarks crash.

`pytest tests/benchmarks/ ... || true` hid all seven erroring at setup under
pytest 9.2: the job that ran them passed, and all that showed was a missing
artifact in the next one.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "benchmarks.yml"


def test_the_job_does_not_swallow_a_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pytest tests/benchmarks/" in text, "the job no longer runs them"
    assert "|| true" not in text


def test_a_change_to_the_job_runs_the_job() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '- ".github/workflows/benchmarks.yml"' in text
    assert '- "tests/benchmarks/**"' in text
