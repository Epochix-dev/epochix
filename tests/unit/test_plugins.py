"""Tests for the model-story plugin system.

Covers:
- metaphor pack YAML loading and rendering
- task definition registration (via dict and TaskDefinition)
- exporter registration and dispatch
- reset / idempotency of plugin loading
- error-resilience (bad YAML, missing fields, non-callable exporter)
"""
from __future__ import annotations

import pytest

from model_story.plugins import reset_plugins
from model_story.plugins.exporter_registry import (
    get_exporter,
    list_exporters,
    register_exporter,
    run_exporter,
)
from model_story.plugins.metaphor_loader import (
    get_metaphor_cards,
    list_packs,
    load_yaml_pack,
)
from model_story.plugins.task_registry import (
    TaskDefinition,
    get_task,
    list_tasks,
    register_task,
)


@pytest.fixture(autouse=True)
def _clean_plugins() -> None:  # type: ignore[return]
    """Reset all plugin state before each test."""
    reset_plugins()
    yield  # type: ignore[misc]
    reset_plugins()


# ── Metaphor pack YAML loader ─────────────────────────────────────────────────

class TestMetaphorLoader:
    def test_load_valid_yaml(self, tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
        yaml_file = tmp_path / "biometric_pack.yaml"  # type: ignore[operator]
        yaml_file.write_text(  # type: ignore[union-attr]
            """
task: biometric
cards:
  awakening:
    - title: "Identity awakens"
      body: "The system sees everyone the same. EER: {value}."
      icon: "👁️"
      color: "#6366f1"
  learning:
    - title: "Faces take shape"
      body: "Clusters forming. EER: {value_pct}."
      icon: "🔍"
""",
            encoding="utf-8",
        )
        load_yaml_pack(yaml_file)

        packs = list_packs()
        assert "biometric" in packs
        assert "awakening" in packs["biometric"]
        assert "learning" in packs["biometric"]

    def test_get_cards_rendered(self, tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
        yaml_file = tmp_path / "pack.yaml"  # type: ignore[operator]
        yaml_file.write_text(  # type: ignore[union-attr]
            """
task: detection
cards:
  learning:
    - title: "Target acquired"
      body: "mAP50 is {value} at epoch {epoch}."
      icon: "🎯"
""",
            encoding="utf-8",
        )
        load_yaml_pack(yaml_file)

        cards = get_metaphor_cards("detection", "learning", epoch=5.0, value=0.432)
        assert len(cards) == 1
        assert cards[0].title == "Target acquired"
        assert "0.4320" in cards[0].body
        assert "epoch 5" in cards[0].body

    def test_get_cards_missing_task_returns_empty(self) -> None:
        cards = get_metaphor_cards("nonexistent", "awakening")
        assert cards == []

    def test_get_cards_missing_phase_returns_empty(
        self, tmp_path: pytest.TempPathFactory  # type: ignore[type-arg]
    ) -> None:
        yaml_file = tmp_path / "pack.yaml"  # type: ignore[operator]
        yaml_file.write_text("task: nlp\ncards:\n  awakening:\n    - title: T\n      body: B\n")  # type: ignore[union-attr]
        load_yaml_pack(yaml_file)

        cards = get_metaphor_cards("nlp", "polishing")  # phase not in YAML
        assert cards == []

    def test_missing_yaml_file_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="model_story.plugins.metaphor_loader"):
            load_yaml_pack("/nonexistent/path/to/pack.yaml")

        assert any("not found" in r.message for r in caplog.records)

    def test_load_yaml_requires_pyyaml(  # type: ignore[type-arg]
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If PyYAML is not installed, a helpful ImportError is raised."""
        import builtins

        real_import = builtins.__import__

        def _block_yaml(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", _block_yaml)

        yaml_file = tmp_path / "p.yaml"  # type: ignore[operator]
        yaml_file.write_text("task: test\ncards: {}")  # type: ignore[union-attr]
        with pytest.raises(ImportError, match="pip install pyyaml"):
            load_yaml_pack(yaml_file)

    def test_value_pct_placeholder(self, tmp_path: pytest.TempPathFactory) -> None:  # type: ignore[type-arg]
        yaml_file = tmp_path / "pack.yaml"  # type: ignore[operator]
        yaml_file.write_text(  # type: ignore[union-attr]
            "task: classification\ncards:\n  mastering:\n"
            "    - title: T\n      body: '{value_pct} accurate'\n",
        )
        load_yaml_pack(yaml_file)

        cards = get_metaphor_cards("classification", "mastering", value=0.872)
        assert "87.2% accurate" in cards[0].body


# ── Task registry ─────────────────────────────────────────────────────────────

class TestTaskRegistry:
    def test_register_task_definition(self) -> None:
        td = TaskDefinition(
            key="audio",
            display_name="Audio / Speech",
            primary_metric="word_error_rate",
            lower_better=True,
            grade_thresholds={"A+": 0.03, "F": float("inf")},
        )
        register_task(td)

        result = get_task("audio")
        assert result is not None
        assert result.key == "audio"
        assert result.lower_better is True
        assert result.primary_metric == "word_error_rate"

    def test_register_task_dict(self) -> None:
        from model_story.plugins.task_registry import _register_task_value

        _register_task_value(
            {
                "key": "medical_imaging",
                "display_name": "Medical Imaging",
                "primary_metric": "dice_score",
                "lower_better": False,
            },
            source="test",
        )
        result = get_task("medical_imaging")
        assert result is not None
        assert result.display_name == "Medical Imaging"

    def test_list_tasks(self) -> None:
        register_task(TaskDefinition(key="t1", display_name="T1", primary_metric="m1"))
        register_task(TaskDefinition(key="t2", display_name="T2", primary_metric="m2"))

        keys = [t.key for t in list_tasks()]
        assert "t1" in keys
        assert "t2" in keys

    def test_get_task_missing(self) -> None:
        assert get_task("does_not_exist") is None

    def test_register_invalid_dict_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from model_story.plugins.task_registry import _register_task_value

        with caplog.at_level(logging.WARNING, logger="model_story.plugins.task_registry"):
            _register_task_value({"bad_key": "no_key_field"}, source="test")

        assert get_task("") is None  # nothing registered


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
