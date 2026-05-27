"""Tests for Phase 4.3 — .epochix.yaml grade-threshold config loader."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from epochix.enums import Grade, TaskType
from epochix.story_engine.config_loader import (
    GradeConfig,
    find_config_file,
    load_grade_config,
)
from epochix.story_engine.grade import compute_grade

# ── GradeConfig dataclass ─────────────────────────────────────────────────────

class TestGradeConfig:
    def test_get_thresholds_present(self) -> None:
        cfg = GradeConfig(
            grade_thresholds={"classification": {"A+": 0.97, "A": 0.92}},
        )
        result = cfg.get_thresholds(TaskType.CLASSIFICATION)
        assert result == {"A+": 0.97, "A": 0.92}

    def test_get_thresholds_missing_returns_none(self) -> None:
        cfg = GradeConfig()
        assert cfg.get_thresholds(TaskType.DETECTION) is None

    def test_get_lower_better_present(self) -> None:
        cfg = GradeConfig(lower_better_override={"nlp": True})
        assert cfg.get_lower_better(TaskType.NLP) is True

    def test_get_lower_better_missing_returns_none(self) -> None:
        cfg = GradeConfig()
        assert cfg.get_lower_better(TaskType.CLASSIFICATION) is None

    def test_get_lower_better_false_override(self) -> None:
        cfg = GradeConfig(lower_better_override={"classification": False})
        assert cfg.get_lower_better(TaskType.CLASSIFICATION) is False


# ── find_config_file ──────────────────────────────────────────────────────────

class TestFindConfigFile:
    def test_finds_file_in_given_dir(self, tmp_path: Path) -> None:
        config = tmp_path / ".epochix.yaml"
        config.write_text("version: 1\n", encoding="utf-8")
        found = find_config_file(start=tmp_path)
        assert found == config

    def test_finds_file_in_parent(self, tmp_path: Path) -> None:
        config = tmp_path / ".epochix.yaml"
        config.write_text("version: 1\n", encoding="utf-8")
        sub = tmp_path / "sub" / "project"
        sub.mkdir(parents=True)
        found = find_config_file(start=sub)
        assert found == config

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        found = find_config_file(start=tmp_path)
        assert found is None

    def test_returns_none_for_empty_tree(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        assert find_config_file(start=tmp_path / "a" / "b" / "c") is None


# ── load_grade_config ─────────────────────────────────────────────────────────

class TestLoadGradeConfig:
    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = load_grade_config(path=tmp_path / "nonexistent.yaml")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text("", encoding="utf-8")
        assert load_grade_config(path=p) is None

    def test_returns_none_for_invalid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text("{ bad yaml: [unclosed", encoding="utf-8")
        assert load_grade_config(path=p) is None

    def test_returns_none_for_non_mapping_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        assert load_grade_config(path=p) is None

    def test_parses_grade_thresholds(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text(
            textwrap.dedent("""\
                version: 1
                grade_thresholds:
                  classification:
                    "A+": 0.97
                    A:    0.92
                    "A-": 0.88
            """),
            encoding="utf-8",
        )
        cfg = load_grade_config(path=p)
        assert cfg is not None
        t = cfg.get_thresholds(TaskType.CLASSIFICATION)
        assert t is not None
        assert t["A+"] == pytest.approx(0.97)
        assert t["A"] == pytest.approx(0.92)
        assert t["A-"] == pytest.approx(0.88)

    def test_parses_lower_better_override(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text(
            textwrap.dedent("""\
                version: 1
                lower_better:
                  classification: false
                  nlp: true
            """),
            encoding="utf-8",
        )
        cfg = load_grade_config(path=p)
        assert cfg is not None
        assert cfg.get_lower_better(TaskType.CLASSIFICATION) is False
        assert cfg.get_lower_better(TaskType.NLP) is True

    def test_ignores_missing_sections(self, tmp_path: Path) -> None:
        p = tmp_path / ".epochix.yaml"
        p.write_text("version: 1\n", encoding="utf-8")
        cfg = load_grade_config(path=p)
        assert cfg is not None
        assert cfg.grade_thresholds == {}
        assert cfg.lower_better_override == {}

    def test_returns_none_when_no_file_in_tree(self, tmp_path: Path) -> None:
        # Ensure no .epochix.yaml exists anywhere in tmp_path
        result = load_grade_config(path=tmp_path / "missing.yaml")
        assert result is None

    def test_full_config_file(self, tmp_path: Path) -> None:
        """Round-trip parse of a complete config matching the default template."""
        p = tmp_path / ".epochix.yaml"
        p.write_text(
            textwrap.dedent("""\
                version: 1
                grade_thresholds:
                  classification:
                    "A+": 0.95
                    A:    0.90
                    "A-": 0.87
                    "B+": 0.82
                    B:    0.75
                    "B-": 0.70
                    "C+": 0.65
                    C:    0.60
                    "C-": 0.55
                    D:    0.50
                    F:    0.0
                  nlp:
                    "A+": 10.0
                    A:    20.0
                    F:    .inf
                lower_better:
                  nlp: true
                  classification: false
            """),
            encoding="utf-8",
        )
        cfg = load_grade_config(path=p)
        assert cfg is not None
        cls_t = cfg.get_thresholds(TaskType.CLASSIFICATION)
        assert cls_t is not None
        assert len(cls_t) == 11
        assert cls_t["F"] == pytest.approx(0.0)

        nlp_t = cfg.get_thresholds(TaskType.NLP)
        assert nlp_t is not None
        assert nlp_t["A+"] == pytest.approx(10.0)
        import math
        assert math.isinf(nlp_t["F"])

        assert cfg.get_lower_better(TaskType.NLP) is True
        assert cfg.get_lower_better(TaskType.CLASSIFICATION) is False


# ── compute_grade with config ─────────────────────────────────────────────────

class TestComputeGradeWithConfig:
    def test_config_overrides_default_threshold(self) -> None:
        """Custom A+ threshold of 0.99 means 0.95 is no longer A+."""
        cfg = GradeConfig(
            grade_thresholds={
                "classification": {
                    "A+": 0.99, "A": 0.93, "A-": 0.88,
                    "B+": 0.83, "B": 0.76, "B-": 0.70,
                    "C+": 0.65, "C": 0.60, "C-": 0.55,
                    "D": 0.50, "F": 0.0,
                }
            }
        )
        # 0.95 is below new A+ threshold (0.99) but above A threshold (0.93)
        grade = compute_grade(TaskType.CLASSIFICATION, 0.95, config=cfg)
        assert grade == Grade.A

    def test_config_not_applied_when_task_absent(self) -> None:
        """Config with no detection section falls back to built-in defaults."""
        cfg = GradeConfig()  # empty
        grade = compute_grade(TaskType.DETECTION, 0.80, config=cfg)
        # Built-in: 0.80 > 0.75 → A+
        assert grade == Grade.A_PLUS

    def test_lower_better_override_via_config(self) -> None:
        """Config can flip lower_better for a task."""
        # Default classification is higher-is-better; flip it artificially
        cfg = GradeConfig(
            grade_thresholds={
                "classification": {
                    "A+": 0.05, "A": 0.10, "A-": 0.20,
                    "B+": 0.35, "B": 0.50, "B-": 0.65,
                    "C+": 0.80, "C": 1.00, "C-": 1.50,
                    "D": 2.50, "F": 100.0,
                }
            },
            lower_better_override={"classification": True},
        )
        # value=0.03 ≤ 0.05 → A+
        grade = compute_grade(TaskType.CLASSIFICATION, 0.03, config=cfg)
        assert grade == Grade.A_PLUS

    def test_explicit_custom_thresholds_beat_config(self) -> None:
        """Explicit custom_thresholds take priority over config."""
        cfg = GradeConfig(
            grade_thresholds={"classification": {"A+": 0.99, "F": 0.0}}
        )
        # custom_thresholds says A+ at 0.50 — config wants 0.99
        custom = {"A+": 0.50, "F": 0.0}
        grade = compute_grade(
            TaskType.CLASSIFICATION, 0.55, custom_thresholds=custom, config=cfg
        )
        assert grade == Grade.A_PLUS

    def test_alias_labels_accepted(self) -> None:
        """YAML keys like 'A_PLUS' and 'BPLUS' are normalised to A+ / B+."""
        cfg = GradeConfig(
            grade_thresholds={
                "classification": {"A_PLUS": 0.95, "A": 0.90, "F": 0.0}
            }
        )
        grade = compute_grade(TaskType.CLASSIFICATION, 0.96, config=cfg)
        assert grade == Grade.A_PLUS

    def test_no_config_uses_defaults(self) -> None:
        """Without config, built-in defaults apply."""
        grade = compute_grade(TaskType.CLASSIFICATION, 0.96)
        assert grade == Grade.A_PLUS

    def test_config_none_does_not_change_behaviour(self) -> None:
        grade_no_cfg = compute_grade(TaskType.CLASSIFICATION, 0.80)
        grade_cfg_none = compute_grade(TaskType.CLASSIFICATION, 0.80, config=None)
        assert grade_no_cfg == grade_cfg_none


# ── StoryEngine integration ───────────────────────────────────────────────────

class TestStoryEngineWithConfig:
    def test_story_engine_accepts_grade_config(self) -> None:
        """StoryEngine stores grade_config and uses it in process()."""
        from datetime import datetime, timezone

        from epochix.models import MetricEvent
        from epochix.story_engine import StoryEngine

        cfg = GradeConfig(
            grade_thresholds={
                "classification": {
                    "A+": 0.99, "A": 0.95, "A-": 0.90,
                    "B+": 0.85, "B": 0.80, "B-": 0.75,
                    "C+": 0.70, "C": 0.65, "C-": 0.60,
                    "D": 0.55, "F": 0.0,
                }
            }
        )
        engine = StoryEngine(
            run_id="cfg-test",
            task=None,
            grade_config=cfg,
        )
        ts = datetime.now(tz=timezone.utc)

        def _evt(seq: int, value: float) -> MetricEvent:
            return MetricEvent(
                run_id="cfg-test",
                seq=seq,
                timestamp=ts,
                epoch=float(seq),
                canonical_key="val_accuracy",
                raw_key="acc",
                value=value,
            )

        # Need ≥3 events before a frame is produced
        engine.process(_evt(1, 0.60))
        engine.process(_evt(2, 0.65))
        frame = engine.process(_evt(3, 0.82))

        assert frame is not None
        # With custom config: B+ requires ≥ 0.85, B requires ≥ 0.80; 0.82 → B
        assert frame.grade == Grade.B
