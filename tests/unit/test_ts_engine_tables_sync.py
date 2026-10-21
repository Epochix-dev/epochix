"""The extension's engine tables are generated from this engine's — keep them so.

`scripts/gen_ts_engine_tables.py` writes the TypeScript tables and a golden
file of this engine's canonical names, which the extension's own test replays.
Hand-porting them let 170 of 319 names drift, including `valid_loss` read as
training loss. Change the Python, run the script, commit both.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_ts_engine_tables", REPO / "scripts" / "gen_ts_engine_tables.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _committed(path: Path) -> str:
    assert path.is_file(), f"missing generated file: {path}"
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_ts_tables_are_current() -> None:
    gen = _generator()
    assert _committed(gen.TARGET) == gen.render(), (
        "epochix-vscode/src/story/engineTables.generated.ts is stale — "
        "run: python scripts/gen_ts_engine_tables.py"
    )


def test_golden_names_are_current() -> None:
    gen = _generator()
    assert _committed(gen.GOLDEN) == gen.render_golden(), (
        "canonical.golden.json is stale — run: python scripts/gen_ts_engine_tables.py"
    )


def test_grading_tables_are_current() -> None:
    gen = _generator()
    assert _committed(gen.GRADING) == gen.render_grading(), (
        "epochix-vscode/src/story/grading.generated.ts is stale — "
        "run: python scripts/gen_ts_engine_tables.py"
    )


def test_grading_golden_is_current() -> None:
    gen = _generator()
    assert _committed(gen.GRADING_GOLDEN) == gen.render_grading_golden(), (
        "grading.golden.json is stale — run: python scripts/gen_ts_engine_tables.py"
    )


def test_grading_golden_covers_what_had_drifted() -> None:
    """The cases the hand-ported logic got wrong must be in the replay."""
    golden = json.loads(_committed(_generator().GRADING_GOLDEN))
    assert len(golden["compute_grade"]) > 500
    assert len(golden["compute_phase"]) > 500
    # Direction pins for LightGBM's raw names now live in Python.
    assert golden["metric_lower_better"]["l1"] is True
    assert golden["metric_lower_better"]["val_mape"] is True
    # The improvement ratio is clamped: a value past the ideal is 1, not more.
    assert [0.0, 1.4, 0.0, None] not in golden["relative_improvement"]
    assert any(v == 1.4 and r == 1.0 for v, _, _, r in golden["relative_improvement"])
    # Unknown progress is None, not a made-up 0.05.
    assert any(p is None for p, *_ in golden["compute_phase"])


def test_golden_covers_the_names_that_drifted() -> None:
    golden = json.loads(_committed(_generator().GOLDEN))
    assert len(golden) > 300
    assert golden["valid_loss"] == "val_loss"
    assert golden["eval_loss"] == "val_loss"
    assert golden["val_mae"] == "val_MAE"
    assert golden["mae"] == "MAE"


def test_parsers_golden_is_what_the_parsers_answer() -> None:
    """Every recorded call, fed back to the Python parsers, gives what it gave.

    Recording runs the parser tests (scripts/parser_recorder.py), too slow for
    here; this replay is what fails when a parser changes and the golden the
    extension replays was not regenerated.
    """
    gen = _generator()
    golden = json.loads(_committed(gen.PARSERS_GOLDEN))
    wrong = gen.replay_parsers_golden(golden)
    assert wrong == [], (
        f"parsers.golden.json is stale ({len(wrong)} calls differ) — "
        "run: make gen-ts-tables\n" + "\n".join(wrong[:10])
    )


def test_parsers_golden_reaches_every_port() -> None:
    golden = json.loads(_committed(_generator().PARSERS_GOLDEN))
    rows = [row for sequences in golden.values() for s in sequences for row in s.get("events", [])]
    assert len(rows) > 3000, "the parser golden lost its recordings"
    ported = {
        "accelerate",
        "boosting",
        "fastai",
        "huggingface",
        "keras_tensorflow",
        "pytorch_lightning",
        "ultralytics_yolo",
        "universal",
    }
    assert {row[0] for row in rows} == ported


def test_every_test_that_feeds_a_parser_is_recorded() -> None:
    """A new test file that calls a parser directly must be in the golden, or
    its lines never reach the extension's ports."""
    gen = _generator()
    recorded = {node.split("::")[0] for node in json.loads(_committed(gen.PARSERS_GOLDEN))}
    missing = sorted(set(gen._recorded_test_files()) - recorded)
    assert missing == [], f"not in parsers.golden.json — run: make gen-ts-tables: {missing}"
