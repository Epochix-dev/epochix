"""The parser registry must hold each parser once.

Every built-in parser is registered twice over: eagerly, when
`epochix.parsers` imports each module and its `@register_parser` decorator
runs, and again by `_load_plugins`, which walks the `epochix.parsers` entry
points — where those same built-ins are declared.

The guard against that compared a freshly constructed instance against the
registry. Parsers define no `__eq__`, so it was an identity check against a
brand-new object and never matched. A published install reported 16 parsers
for the 8 that exist, and format detection sniffed every one of them twice.
"""

from __future__ import annotations

from collections import Counter

from epochix.parsers import detect_parser, get_registry
from epochix.parsers.boosting import BoostingParser
from epochix.parsers.universal import UniversalParser


def test_each_parser_appears_once() -> None:
    counts = Counter(p.name for p in get_registry())
    assert [name for name, n in counts.items() if n > 1] == []


def test_the_built_ins_are_all_there() -> None:
    names = {p.name for p in get_registry()}
    assert names >= {
        "accelerate",
        "boosting",
        "fastai",
        "huggingface",
        "keras_tensorflow",
        "pytorch_lightning",
        "ultralytics_yolo",
        "universal",
    }


def test_one_instance_per_class() -> None:
    """Deduping by name would still allow two objects of the same class."""
    types = Counter(type(p) for p in get_registry())
    assert [t.__name__ for t, n in types.items() if n > 1] == []


def test_detection_still_picks_the_right_parser() -> None:
    """The dedup must not cost us the parser it was meant to keep."""
    boosting = ["[0]\tvalidation_0-logloss:0.51987"] * 3
    assert isinstance(detect_parser(boosting), BoostingParser)
    assert isinstance(detect_parser(["nothing that looks like training"]), UniversalParser)
