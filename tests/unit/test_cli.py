"""CLI routing tests.

Guards against the regression where a positional argument on the Typer group
callback swallowed subcommand names (so `epochix serve` was parsed as a
log-file path). The console entry point (`main_entry`) routes bare log-file
invocations to the implicit `run` command while real subcommands dispatch.
"""

from __future__ import annotations

import sys

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
