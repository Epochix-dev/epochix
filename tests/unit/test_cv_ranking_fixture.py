"""tests/fixtures/cv_ranking.json is what the Python ranking says, exactly.

The dashboard ranks cross-validation folds in JavaScript
(frontend/src/crossValidation.js) and is tested against this fixture, so the
dashboard and the reports cannot name different winners. This keeps the
fixture honest: if the Python ranking changes, this fails until the fixture is
regenerated, and then the JavaScript test fails until the port follows.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from epochix.cross_validation import is_search, summarise

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "cv_ranking.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_is_not_empty() -> None:
    assert len(CASES) >= 7
    assert sum(len(c["rows"]) for c in CASES.values()) >= 10
    assert any(any(r["chosen"] for r in c["rows"]) for c in CASES.values())


@pytest.mark.parametrize("name", sorted(CASES))
def test_python_ranks_as_the_fixture_says(name: str) -> None:
    case = CASES[name]
    assert is_search(case["cv"]) == case["is_search"]
    got = [dataclasses.asdict(r) for r in summarise(case["cv"])]
    exact = ("metric", "setting", "folds", "chosen")
    assert [[r[k] for k in exact] for r in got] == [[r[k] for k in exact] for r in case["rows"]]
    # statistics.stdev changed algorithm between Python versions and differs in
    # the last digits (3.10 against 3.12+), so the numbers are compared to
    # 1e-12, as the JavaScript side compares them. The ranking is exact.
    for mine, want in zip(got, case["rows"], strict=True):
        for key in ("mean", "lowest", "highest", "std"):
            if want[key] is None:
                assert mine[key] is None
            else:
                assert mine[key] == pytest.approx(want[key], rel=1e-12, abs=1e-15)
