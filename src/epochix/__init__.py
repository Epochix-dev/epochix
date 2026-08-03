"""Epochix — visual storytelling for deep learning training runs."""

from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetricEvent, Milestone, Run, StoryFrame, Warning
from epochix.parsers.base import BaseParser
from epochix.parsers.registry import register_parser


def _resolve_version() -> str:
    """Version of the code that is actually running.

    ``importlib.metadata.version`` reads the INSTALLED distribution's metadata,
    which describes the installed copy — not necessarily this one. Running from
    a source checkout on a machine that also has a release installed made
    ``/api/version`` report the installed number: it said 0.5.75 while serving
    0.5.80 source.

    That is not cosmetic. The VS Code extension compares ``/api/version``
    against its own version to warn about a stale Python package, so a wrong
    answer here either raises a false alarm or hides a real one.

    A ``pyproject.toml`` sitting above the package root means we are running
    from the tree, so the tree's version is the truthful answer.
    """
    from pathlib import Path

    # src/epochix/__init__.py -> src/epochix -> src -> repo root
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        try:
            import re

            text = pyproject.read_text(encoding="utf-8")
            # Only the [project] version, not a dependency pin further down.
            match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if match and 'name = "epochix"' in text:
                return match.group(1)
        except OSError:  # pragma: no cover - unreadable checkout
            pass

    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("epochix")
    except Exception:  # noqa: BLE001 — fallback when the package isn't installed
        return "0.0.0+local"


__version__ = _resolve_version()

__all__ = [
    # Core models
    "Run",
    "MetricEvent",
    "StoryFrame",
    "Milestone",
    "Warning",
    # Enums
    "Phase",
    "Grade",
    "TaskType",
    # Plugin interface
    "register_parser",
    "BaseParser",
    # SDK functions — populated lazily via __getattr__ below
    "parse",
    "parse_string",
    "visualize",
    "serve",
    "export",
    "compare",
    "LiveReporter",
    "LightningCallback",
    "HuggingFaceCallback",
]

_SDK_ATTRS = {
    "parse": ("epochix.sdk.parse", "parse"),
    "parse_string": ("epochix.sdk.parse", "parse_string"),
    "visualize": ("epochix.sdk.visualize", "visualize"),
    "serve": ("epochix.sdk.visualize", "serve"),
    "export": ("epochix.sdk.export", "export"),
    "compare": ("epochix.sdk.compare", "compare"),
    "LiveReporter": ("epochix.sdk.live_reporter", "LiveReporter"),
    "LightningCallback": ("epochix.integrations.lightning", "StoryCallback"),
    "HuggingFaceCallback": ("epochix.integrations.hf", "StoryCallback"),
}


def load_ipython_extension(ipython: object) -> None:
    """Entry point for ``%load_ext epochix``.

    IPython looks for this on the module you name, so it has to live on the
    top-level package — not on epochix.integrations.jupyter. Without it,
    ``%load_ext epochix`` (what the docs tell people to run) printed "The
    epochix module is not an IPython extension" and registered no magics.
    """
    from epochix.integrations.jupyter import load_ipython_extension as _load

    _load(ipython)


def unload_ipython_extension(ipython: object) -> None:
    """Entry point for ``%unload_ext epochix``."""
    from epochix.integrations.jupyter import unload_ipython_extension as _unload

    _unload(ipython)


def __getattr__(name: str) -> object:
    if name in _SDK_ATTRS:
        module_path, attr = _SDK_ATTRS[name]
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module 'epochix' has no attribute {name!r}")
