from epochix.parsers.base import BaseParser, ParserContext
from epochix.parsers.registry import detect_parser, get_registry, register_parser

__all__ = [
    "BaseParser",
    "ParserContext",
    "register_parser",
    "detect_parser",
    "get_registry",
]

# Eagerly register built-in parsers in priority order
from epochix.parsers import (  # noqa: E402, F401
    accelerate,
    fastai,
    huggingface,
    keras_tensorflow,
    pytorch_lightning,
    ultralytics_yolo,
    universal,
)
