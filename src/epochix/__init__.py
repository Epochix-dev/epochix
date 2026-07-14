"""Epochix — visual storytelling for deep learning training runs."""

from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetricEvent, Milestone, Run, StoryFrame, Warning
from epochix.parsers.base import BaseParser
from epochix.parsers.registry import register_parser

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("epochix")
except Exception:  # noqa: BLE001 — fallback when the package isn't installed
    __version__ = "0.0.0+local"

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
