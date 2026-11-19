"""macOS is tested off the PR path, and a red macOS run is seen.

Every PR ran the tests on macOS at four Pythons and the dashboard in WebKit on
a Mac. Those runners queue: on 2026-11-19 four PRs' macOS jobs waited 15-18
minutes for one and were cancelled without running a step. No user runs on a
Mac yet, so ci.yml no longer waits on one; macos.yml runs the same tests and
render on macOS after a change lands, weekly, on demand, and on a PR that asks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as True.
    if True in data:
        data["on"] = data.pop(True)  # type: ignore[call-overload]
    return data


CI = _load("ci.yml")
MAC = _load("macos.yml")
BROWSER = _load("browser.yml")


def _pytest_runs(job: dict[str, Any]) -> list[str]:
    return [s["run"] for s in job["steps"] if "pytest" in s.get("run", "")]


def test_no_pr_job_waits_on_a_mac() -> None:
    assert CI["jobs"]["test"]["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    assert CI["jobs"]["browser"] == {
        "uses": "./.github/workflows/browser.yml",
        "with": {"os": "ubuntu-latest"},
    }
    for name, job in CI["jobs"].items():
        assert "macos" not in str(job.get("runs-on", "")), name
        assert "macos" not in str(job.get("strategy", "")), name


def test_macos_runs_after_landing_weekly_on_demand_and_when_a_pr_asks() -> None:
    on = MAC["on"]
    assert on["push"]["branches"] == ["main"]
    assert on["schedule"]
    assert "workflow_dispatch" in on
    assert "labeled" in on["pull_request"]["types"]


def test_it_runs_what_ci_runs_at_the_oldest_and_newest_python() -> None:
    ci_test, mac_test = CI["jobs"]["test"], MAC["jobs"]["test"]
    assert _pytest_runs(mac_test) == _pytest_runs(ci_test)
    assert _pytest_runs(ci_test), "ci.yml's test job runs no pytest: this checks nothing"
    assert mac_test["steps"][-1].get("env") == ci_test["steps"][-1].get("env")
    pythons = ci_test["strategy"]["matrix"]["python"]
    assert mac_test["strategy"]["matrix"]["python"] == [pythons[0], pythons[-1]]
    assert mac_test["runs-on"] == "macos-latest"


def test_both_workflows_render_with_the_one_browser_job() -> None:
    assert MAC["jobs"]["browser"]["uses"] == "./.github/workflows/browser.yml"
    assert MAC["jobs"]["browser"]["with"] == {"os": "macos-latest"}
    assert "workflow_call" in BROWSER["on"]
    (render,) = BROWSER["jobs"].values()
    assert render["runs-on"] == "${{ inputs.os }}"
    assert "strategy" not in render
    # Still demands that every engine ran, on whichever OS calls it.
    assert render["env"]["EPOCHIX_REQUIRE_ALL_BROWSERS"] == "1"
    assert any(
        'ran != {"chromium", "firefox", "webkit"}' in s.get("run", "") for s in render["steps"]
    )


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    (found,) = [s for s in job["steps"] if s.get("name") == name]
    return found


def test_it_runs_the_extension_host_tests_as_ci_does() -> None:
    ci_job, mac_job = CI["jobs"]["test-vscode"], MAC["jobs"]["vscode"]
    assert mac_job["runs-on"] == "macos-latest"
    # Same checkout, Node and install as ci.yml.
    assert mac_job["steps"][:3] == ci_job["steps"][:3]
    # The webview the release ships, built the same way.
    build = "Build the webview bundle exactly as the release does"
    assert _step(mac_job, build) == _step(ci_job, build)
    # The same suite; only Linux needs a virtual display for it.
    run = "Run extension host integration tests"
    ci_run, mac_run = _step(ci_job, run), _step(mac_job, run)
    assert ci_run["run"] == "xvfb-run -a npm test"
    assert mac_run == {**ci_run, "run": "npm test"}


def test_every_mac_job_waits_for_the_decision() -> None:
    for name in ("test", "browser", "vscode"):
        job = MAC["jobs"][name]
        assert job["needs"] == "decide", name
        assert job["if"] == "needs.decide.outputs.run == 'true'", name


def test_a_red_mac_run_is_reported() -> None:
    report = MAC["jobs"]["report"]
    assert set(report["needs"]) == set(MAC["jobs"]) - {"report"}
    assert "failure()" in report["if"]
    assert "github.event_name != 'pull_request'" in report["if"]
    assert report["permissions"] == {"issues": "write"}


# ── the decision, executed ────────────────────────────────────────────────────


def _bash() -> str | None:
    found = shutil.which("bash")
    # Windows' System32 bash is WSL, which may have no distribution at all.
    if found is None or "system32" in found.lower():
        git_bash = (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        )
        return str(git_bash) if git_bash.is_file() else None
    return found


def _decide(tmp_path: Path, *, event: str, labelled: bool = False, files: str = "") -> str:
    bash = _bash()
    if bash is None:
        pytest.skip("no bash to run the step with")
    (step,) = MAC["jobs"]["decide"]["steps"]
    script = tmp_path / "decide.sh"
    script.write_text(step["run"], encoding="utf-8", newline="\n")
    fake = tmp_path / "bin"
    fake.mkdir()
    # `gh pr view N --json files --jq ...` answers the PR's changed files.
    (fake / "gh").write_text(
        '#!/bin/sh\nprintf "%s" "$FAKE_FILES"\n', encoding="utf-8", newline="\n"
    )
    (fake / "gh").chmod(0o755)
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
        "EVENT": event,
        "PR": "7",
        "LABELLED": "true" if labelled else "false",
        "FAKE_FILES": files,
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    done = subprocess.run(  # noqa: S603
        [bash, str(script)], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return output.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_anything_but_a_pr_runs(tmp_path: Path, event: str) -> None:
    assert _decide(tmp_path, event=event) == "run=true"


def test_a_pr_runs_when_labelled_macos(tmp_path: Path) -> None:
    assert _decide(tmp_path, event="pull_request", labelled=True, files="src/a.py") == "run=true"


@pytest.mark.parametrize(
    "changed", [".github/workflows/macos.yml", ".github/workflows/browser.yml"]
)
def test_a_pr_that_changes_the_mac_jobs_runs_them(tmp_path: Path, changed: str) -> None:
    files = f"src/epochix/cli.py\n{changed}\n"
    assert _decide(tmp_path, event="pull_request", files=files) == "run=true"


def test_any_other_pr_waits_for_main(tmp_path: Path) -> None:
    files = "src/epochix/cli.py\n.github/workflows/ci.yml\n"
    assert _decide(tmp_path, event="pull_request", files=files) == "run=false"
