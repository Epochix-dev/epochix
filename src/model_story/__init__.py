"""Model Learning Story — visual storytelling for deep learning training runs."""

from model_story.enums import Grade, Phase, TaskType
from model_story.models import MetricEvent, Milestone, Run, StoryFrame, Warning
from model_story.parsers.base import BaseParser
from model_story.parsers.registry import register_parser

__version__ = "0.1.0"

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
    "parse": ("model_story.sdk.parse", "parse"),
    "parse_string": ("model_story.sdk.parse", "parse_string"),
    "visualize": ("model_story.sdk.visualize", "visualize"),
    "serve": ("model_story.sdk.visualize", "serve"),
    "export": ("model_story.sdk.export", "export"),
    "compare": ("model_story.sdk.compare", "compare"),
    "LiveReporter": ("model_story.sdk.live_reporter", "LiveReporter"),
    "LightningCallback": ("model_story.integrations.lightning", "StoryCallback"),
    "HuggingFaceCallback": ("model_story.integrations.hf", "StoryCallback"),
}


def __getattr__(name: str) -> object:
    if name in _SDK_ATTRS:
        module_path, attr = _SDK_ATTRS[name]
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module 'model_story' has no attribute {name!r}")
