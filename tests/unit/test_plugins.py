"""Tests for the exporter registry, called directly.

These register by hand. That an INSTALLED exporter is found and used by the
CLI and the server is `tests/integration/test_exporter_plugin_installed.py`:
these passed for the life of three plugin groups nothing loaded.
"""

from __future__ import annotations

import pytest

from epochix.plugins import reset_plugins
from epochix.plugins.exporter_registry import (
    get_exporter,
    list_exporters,
    register_exporter,
    run_exporter,
)


@pytest.fixture(autouse=True)
def _clean_plugins() -> None:  # type: ignore[return]
    """Reset all plugin state before each test."""
    reset_plugins()
    yield  # type: ignore[misc]
    reset_plugins()


# ── Exporter registry ─────────────────────────────────────────────────────────


class TestExporterRegistry:
    def test_register_and_call(self) -> None:
        calls: list[tuple[object, ...]] = []

        def my_exporter(run: object, frames: object, events: object, output_path: str) -> None:
            calls.append((run, frames, events, output_path))

        register_exporter("my_format", my_exporter)
        assert "my_format" in list_exporters()

        fn = get_exporter("my_format")
        assert fn is not None
        fn(None, [], [], "/tmp/out.my")
        assert len(calls) == 1
        assert calls[0][-1] == "/tmp/out.my"

    def test_run_exporter_dispatch(self) -> None:
        outputs: list[str] = []

        register_exporter("csv", lambda run, frames, events, path: outputs.append(path))
        run_exporter("csv", None, [], [], "/tmp/report.csv")  # type: ignore[arg-type]
        assert outputs == ["/tmp/report.csv"]

    def test_run_exporter_missing_raises(self) -> None:
        with pytest.raises(KeyError, match="no_such_format"):
            run_exporter("no_such_format", None, [], [], "/tmp/x")  # type: ignore[arg-type]

    def test_register_non_callable_raises(self) -> None:
        with pytest.raises(TypeError, match="callable"):
            register_exporter("bad", "not_a_function")  # type: ignore[arg-type]

    def test_list_exporters_empty_by_default(self) -> None:
        assert list_exporters() == []

    def test_get_exporter_missing(self) -> None:
        assert get_exporter("latex") is None
