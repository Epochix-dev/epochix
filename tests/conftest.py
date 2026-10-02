"""Shared fixtures.

Grading reads a project's `.epochix.yaml`, looked for from the working
directory upwards and then in the user's home folder. A test's result must not
depend on what a developer happens to keep in either, so the lookup is off
unless a test turns it on.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_grade_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", "off")
