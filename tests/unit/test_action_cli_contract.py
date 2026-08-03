"""Every `epochix …` command the shipped GitHub Action runs must exist.

`.github/actions/epochix/action.yml` invoked `epochix batch <log> --json
--headless` and parsed `d['id']` from stdout. There has never been a `batch`
command, and `run` had no `--json`, so the Action failed for every caller —
a branded, documented integration that had never worked once.

Nothing caught it because the Action is YAML that CI never executes. This is
the same shape as the `/api/parse` endpoint the extension called for months,
and it gets the same fix: compare what the caller names against what the
callee actually publishes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.main import get_command

from epochix.cli import app

ACTIONS = sorted((Path(__file__).resolve().parents[2] / ".github" / "actions").rglob("action.yml"))

# `epochix <word>` on ONE line, e.g.
#   OUTPUT=$(epochix run "$LOG" --json)
#   epochix export "$RUN_ID" --format html
#
# Horizontal whitespace only: `\s` would span the newline between a step's
# `- name: Install epochix` and the `shell: bash` beneath it and report
# "shell" as a subcommand.
_INVOCATION = re.compile(r"\bepochix[ \t]+([a-z][a-z0-9-]*)")


def _executable_lines(text: str) -> str:
    """Drop YAML comments — prose about a command is not a call to it.

    This file's own comment explaining that `epochix batch` never existed
    would otherwise fail the test that exists because of it.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _real_commands() -> set[str]:
    return set(get_command(app).commands)  # type: ignore[attr-defined]


def test_there_is_at_least_one_action_to_check() -> None:
    """Guard the guard: a moved directory must fail, not silently pass."""
    assert ACTIONS, "no action.yml found — did .github/actions move?"


@pytest.mark.parametrize("path", ACTIONS, ids=lambda p: p.parent.name)
def test_action_only_calls_real_commands(path: Path) -> None:
    known = _real_commands()
    called = set(_INVOCATION.findall(_executable_lines(path.read_text(encoding="utf-8"))))
    # Bare `epochix <log>` is legal (run is the default), so only flag words
    # that look like a subcommand but are not one.
    unknown = {c for c in called if c not in known and not c.endswith(".log")}
    assert not unknown, (
        f"{path} calls epochix subcommand(s) that do not exist: {sorted(unknown)}; "
        f"available: {sorted(known)}"
    )


def test_run_supports_the_flags_the_action_passes() -> None:
    """The Action needs machine-readable output; `--json` is that contract."""
    params = {
        opt
        for p in get_command(app).commands["run"].params  # type: ignore[attr-defined]
        for opt in p.opts
    }
    for flag in ("--json", "--task", "--name"):
        assert flag in params, f"`epochix run` is missing {flag}, which the Action relies on"
