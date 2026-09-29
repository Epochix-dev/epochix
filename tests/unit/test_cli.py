"""CLI routing tests.

Guards against the regression where a positional argument on the Typer group
callback swallowed subcommand names (so `epochix serve` was parsed as a
log-file path). The console entry point (`main_entry`) routes bare log-file
invocations to the implicit `run` command while real subcommands dispatch.
"""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

import epochix.cli as cli

runner = CliRunner()


# ── subcommands dispatch correctly (not swallowed as a log file) ───────────────


def test_serve_help_shows_serve_options() -> None:
    result = runner.invoke(cli.app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "Host to bind to" in result.output
    assert "Port to listen on" in result.output


def test_list_help_routes_to_list() -> None:
    result = runner.invoke(cli.app, ["list", "--help"])
    assert result.exit_code == 0
    assert "saved runs" in result.output.lower()


def test_open_requires_run_id() -> None:
    result = runner.invoke(cli.app, ["open"])
    assert result.exit_code != 0
    assert "RUN_ID" in result.output


def test_export_requires_run_id() -> None:
    result = runner.invoke(cli.app, ["export"])
    assert result.exit_code != 0
    assert "RUN_ID" in result.output


def test_run_command_reports_missing_file() -> None:
    result = runner.invoke(cli.app, ["run", "definitely_not_a_real_file.log"])
    assert result.exit_code == 1
    assert "file not found" in result.output.lower()


# ── entry-point shim: bare log file → `run`, subcommands left intact ───────────


def _capture_argv(monkeypatch) -> dict:
    seen: dict = {}
    monkeypatch.setattr(cli, "app", lambda: seen.setdefault("argv", list(sys.argv)))
    return seen


def test_shim_routes_logfile_to_run(monkeypatch) -> None:
    seen = _capture_argv(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["epochix", "train.log"])
    cli.main_entry()
    assert seen["argv"][1:] == ["run", "train.log"]


def test_shim_routes_option_only_to_run(monkeypatch) -> None:
    seen = _capture_argv(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["epochix", "--live"])
    cli.main_entry()
    assert seen["argv"][1:] == ["run", "--live"]


def test_shim_leaves_subcommands_untouched(monkeypatch) -> None:
    seen = _capture_argv(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["epochix", "serve", "--port", "9000"])
    cli.main_entry()
    assert seen["argv"][1:] == ["serve", "--port", "9000"]


def test_shim_passes_through_top_level_help(monkeypatch) -> None:
    seen = _capture_argv(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["epochix", "--help"])
    cli.main_entry()
    # help is passed straight through (no 'run' injected)
    assert seen["argv"][1:] == ["--help"]


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_prints_the_version(flag: str) -> None:
    """It was routed to `run` and answered "No such option: --version"."""
    import os
    import pathlib
    import subprocess

    from epochix import __version__

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "epochix", flag],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[2] / "src")},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"epochix {__version__}"


@pytest.mark.parametrize("how", [["run"], ["run", "--tail"]])
def test_a_folder_is_refused_before_a_run_is_stored(how: list[str], tmp_path) -> None:
    """A folder used to reach open(): a PermissionError traceback on Windows,
    and a run left "in progress" in `epochix list` for good."""
    import os
    import pathlib
    import subprocess

    env = {
        **os.environ,
        "EPOCHIX_DB": str(tmp_path / "runs.db"),
        "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[2] / "src"),
    }
    folder = tmp_path / "logs"
    folder.mkdir()

    def epochix(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "epochix", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            env={**env, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )

    result = epochix(*how, str(folder), "--headless")
    assert result.returncode == 1, result.stderr
    assert "is a folder" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr and "Error:" in result.stderr

    listed = epochix("list")
    assert listed.returncode == 0, listed.stderr
    assert "No runs found" in listed.stdout, listed.stdout


def test_sdk_parse_refuses_a_folder(tmp_path) -> None:
    from epochix.sdk import parse

    with pytest.raises(IsADirectoryError, match="folder"):
        parse(tmp_path)


def test_doctor_reports_the_version_that_is_running(monkeypatch) -> None:
    """It read importlib.metadata, which beside an older installed copy
    reported that copy: "epochix 0.5.94" from a 0.7.22 tree."""
    import importlib.metadata

    from epochix import __version__

    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "0.5.94")
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert f"epochix        {__version__}\n" in result.output, result.output


def test_every_command_is_in_the_cli_reference() -> None:
    """doctor, import-tensorboard and import-wandb shipped undocumented there."""
    import pathlib

    reference = (pathlib.Path(__file__).resolve().parents[2] / "docs" / "cli.md").read_text(
        encoding="utf-8"
    )
    missing = [name for name in sorted(cli._SUBCOMMANDS) if f"## `epochix {name}`" not in reference]
    assert not missing, f"docs/cli.md has no section for: {missing}"
    assert "`epochix --version`" in reference
