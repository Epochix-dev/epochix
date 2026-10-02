"""A project's `.epochix.yaml` changes its grades — end to end.

The README told people to put a `.epochix.yaml` in their project to set their
own grade thresholds. A loader existed, with unit tests, and so did the
grading code that took its result. Nothing connected them: the pipeline and
the server built their story engine without it, so no run ever read the file.
A file making everything under 99.5% accuracy an F still graded 90% an A.

These drive the journey a user takes — a file in the folder, then `parse()`,
the CLI, and the server's live-run API — and pin what an entry applies to.
"""

from __future__ import annotations

import re
import textwrap
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from epochix import parse
from epochix.cli import app
from epochix.config import Settings
from epochix.enums import Grade, TaskType
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import _ON_SCALE_KEYS, _PREFERRED_KEYS_FOR_TASK
from epochix.story_engine.config_loader import (
    GOVERNED_METRICS,
    GradeConfig,
    active_grade_config,
    bands_lower_better,
    config_error,
    load_grade_config,
)
from epochix.story_engine.grade import _DEFAULT_THRESHOLDS, compute_grade, grade_by_trajectory

if TYPE_CHECKING:
    from pathlib import Path

    from epochix.models import StoryFrame

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
runner = CliRunner()

# Anything under 99.5% accuracy is an F: nothing a real run reaches by accident.
STRICT = """\
version: 1
grade_thresholds:
  classification:
    "A+": 0.999
    A: 0.998
    B: 0.997
    C: 0.996
    D: 0.995
    F: 0.0
"""

ACCURACY = [0.58, 0.66, 0.74, 0.82, 0.90]


def _accuracy_log() -> list[str]:
    return [
        f"Epoch {e}/5 train_loss={1 / e:.3f} val_accuracy={v}" for e, v in enumerate(ACCURACY, 1)
    ]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder epochix is run from, with config discovery switched back on."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", "")
    # The per-user fallback must not leak a developer's own file into a test.
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")
    return tmp_path


def _told(project: Path, lines: list[str], config: str | None) -> list[StoryFrame]:
    if config is not None:
        (project / ".epochix.yaml").write_text(textwrap.dedent(config), encoding="utf-8")
    log = project / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(project / f"runs-{len(list(project.glob('*.db')))}.db")
    run = parse(log, db=db, run_name="t")
    return RunStore(db_path=db).get_story_frames(run.id)


# ── The journey ──────────────────────────────────────────────────────────────


class TestTheFileIsRead:
    def test_parse_grades_with_the_project_s_thresholds(self, project: Path) -> None:
        before = _told(project, _accuracy_log(), config=None)
        assert before[-1].grade is Grade.A, "premise: 90% is an A on the built-in bands"
        after = _told(project, _accuracy_log(), config=STRICT)
        assert after[-1].primary_metric_value == 0.90
        assert after[-1].grade is Grade.F
        assert {f.grade for f in after} == {Grade.F}

    def test_a_file_in_a_parent_folder_is_found(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        nested = project / "experiments" / "run7"
        nested.mkdir(parents=True)
        log = nested / "run.log"
        log.write_text("\n".join(_accuracy_log()) + "\n", encoding="utf-8")
        import os

        os.chdir(nested)
        try:
            run = parse(log, db=str(nested / "r.db"), run_name="t")
            frames = RunStore(db_path=str(nested / "r.db")).get_story_frames(run.id)
        finally:
            os.chdir(project)
        assert frames[-1].grade is Grade.F

    def test_the_server_grades_a_live_run_with_them(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        with TestClient(create_app(settings=Settings(db=":memory:"))) as client:
            store: RunStore = client.app.state.store  # type: ignore[attr-defined]
            assert client.post("/api/runs", json={"run_id": "live"}).status_code == 201
            seq = 0
            for epoch, value in enumerate(ACCURACY, start=1):
                for key, v in (("train_loss", 1 / epoch), ("val_accuracy", value)):
                    seq += 1
                    body = {
                        "seq": seq,
                        "epoch": epoch,
                        "canonical_key": key,
                        "raw_key": key,
                        "value": v,
                        "finished": seq == 2 * len(ACCURACY),
                    }
                    assert client.post("/api/runs/live/event", json=body).status_code == 202
            frames = store.get_story_frames("live")
        told = [f for f in frames if f.primary_metric == "val_accuracy"]
        assert told, "the live run told no story"
        assert told[-1].primary_metric_value == 0.90
        assert told[-1].grade is Grade.F

    def test_the_environment_can_name_the_file(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        elsewhere = project / "configs" / "strict.yaml"
        elsewhere.parent.mkdir()
        elsewhere.write_text(STRICT, encoding="utf-8")
        monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", str(elsewhere))
        assert _told(project, _accuracy_log(), config=None)[-1].grade is Grade.F

    def test_the_environment_can_switch_it_off(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", "off")
        assert active_grade_config() is None
        assert _told(project, _accuracy_log(), config=None)[-1].grade is Grade.A

    def test_no_file_is_the_built_in_thresholds(self, project: Path) -> None:
        assert active_grade_config() is None

    def test_a_machine_with_no_home_folder_still_runs(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A service or a stripped subprocess has no USERPROFILE / HOME."""

        def _no_home() -> Path:
            raise RuntimeError("Could not determine home directory.")

        monkeypatch.setattr("pathlib.Path.home", _no_home)
        # Such an environment names its database, as the CLI tests' one does:
        # the default path is under the home folder too.
        monkeypatch.setenv("EPOCHIX_DB", str(project / "runs.db"))
        assert active_grade_config() is None
        assert _told(project, _accuracy_log(), config=None)[-1].grade is Grade.A


# ── What an entry applies to ─────────────────────────────────────────────────


class TestATaskEntryAppliesToItsOwnMetric:
    def test_a_classification_entry_does_not_touch_an_auc(self, project: Path) -> None:
        """Written for accuracy; an AUC has bands of its own."""
        lines = [
            f"Epoch {e}/5 val_auc={v}" for e, v in enumerate([0.95, 0.96, 0.97, 0.98, 0.984], 1)
        ]
        frames = _told(project, lines, config=STRICT)
        assert {f.primary_metric for f in frames} == {"val_AUC"}
        assert frames[-1].grade is Grade.A_PLUS

    def test_a_classification_entry_does_not_touch_an_f1(self, project: Path) -> None:
        """An F1 keeps its built-in bands: 0.84 is a B+, not the F the entry
        gives anything under 99.5%."""
        values = [0.40, 0.55, 0.70, 0.80, 0.84]
        lines = [f"Epoch {e}/5 val_f1={v}" for e, v in enumerate(values, 1)]
        frames = _told(project, lines, config=STRICT)
        assert frames[-1].grade is Grade.B_PLUS

    def test_a_regression_entry_grades_the_error_not_r2(self, project: Path) -> None:
        """The fault this rule exists for: error bands read as R² floors
        graded an R² of 0.99 a B."""
        config = """\
            version: 1
            grade_thresholds:
              regression:
                A: 1.0
                B: 2.5
                C: 5.0
                D: 10.0
                F: .inf
            """
        r2 = [f"Epoch {e}/5 val_r2={v}" for e, v in enumerate([0.90, 0.95, 0.97, 0.98, 0.99], 1)]
        frames = _told(project, r2, config=config)
        assert {f.primary_metric for f in frames} == {"val_R2"}
        assert frames[-1].grade is Grade.A_PLUS

        mae = [f"Epoch {e}/5 val_mae={v}" for e, v in enumerate([9.0, 7.0, 5.5, 4.0, 3.0], 1)]
        frames = _told(project, mae, config=None)  # the file is already there
        assert {f.primary_metric for f in frames} == {"val_MAE"}
        # 3.0 is over B's 2.5 and within C's 5.0. On improvement alone it was an A.
        assert frames[-1].grade is Grade.C
        assert grade_by_trajectory(9.0, 3.0, True).value.startswith("A")

    def test_every_task_entry_names_metrics_that_task_can_be_told_by(self) -> None:
        for task, metrics in GOVERNED_METRICS.items():
            assert metrics <= set(_PREFERRED_KEYS_FOR_TASK[task]), task

    def test_it_is_the_metric_the_built_in_bands_grade_where_there_are_any(self) -> None:
        """Regression and generative differ on purpose: no built-in bands grade
        an MAE or an FID, and the file is how a project supplies them."""
        for task, metrics in GOVERNED_METRICS.items():
            if task in (TaskType.REGRESSION, TaskType.GENERATIVE):
                continue
            on_scale = (
                _ON_SCALE_KEYS[task]
                if task in _ON_SCALE_KEYS
                else frozenset(_PREFERRED_KEYS_FOR_TASK[task][:1])
            )
            assert metrics == on_scale, task
        assert not GOVERNED_METRICS[TaskType.REGRESSION] & _ON_SCALE_KEYS[TaskType.REGRESSION]


class TestAMetricEntry:
    CONFIG = """\
        version: 1
        grade_thresholds:
          eval_f1:
            A: 0.90
            B: 0.75
            C: 0.60
            F: 0.0
        """

    def test_it_grades_that_metric_on_fixed_bands(self, project: Path) -> None:
        lines = [f"Epoch {e}/5 val_f1={v}" for e, v in enumerate([0.40, 0.55, 0.70, 0.80, 0.84], 1)]
        frames = _told(project, lines, config=self.CONFIG)
        # 0.84 is over B's 0.75 and short of A's 0.90; the built-in bands say B+.
        assert [f.grade for f in frames] == [Grade.F, Grade.F, Grade.C, Grade.B, Grade.B]
        assert {f.grade_basis for f in frames} == {"thresholds"}

    def test_a_name_epochix_does_not_recognise_keeps_its_own(self, project: Path) -> None:
        """Stored under the name the run reports it as — not merged into "custom"."""
        config = """\
            version: 1
            grade_thresholds:
              my_score:
                A: 0.90
                B: 0.75
                F: 0.0
            """
        lines = [f"Epoch {e}/5 my_score={v}" for e, v in enumerate([0.5, 0.6, 0.7, 0.8, 0.85], 1)]
        frames = _told(project, lines, config=config)
        assert {f.primary_metric for f in frames} == {"my_score"}
        assert frames[-1].grade is Grade.B
        loaded = active_grade_config()
        assert loaded is not None and list(loaded.metric_thresholds) == ["my_score"]

    def test_its_name_is_read_like_a_metric_in_a_log(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(textwrap.dedent(self.CONFIG), encoding="utf-8")
        config = active_grade_config()
        assert config is not None
        assert list(config.metric_thresholds) == ["val_f1"]
        assert config.grade_thresholds == {}

    def test_it_wins_over_the_metric_s_built_in_bands(self) -> None:
        config = GradeConfig(metric_thresholds={"val_AUC": {"A": 0.99, "F": 0.0}})
        assert config.bands_for(TaskType.CLASSIFICATION, "val_AUC") == {"A": 0.99, "F": 0.0}
        assert config.bands_for(TaskType.CLASSIFICATION, "val_accuracy") is None


class TestACustomEntry:
    def test_it_applies_to_whatever_the_run_is_told_by(self, project: Path) -> None:
        config = """\
            version: 1
            grade_thresholds:
              custom:
                A: 10.0
                B: 20.0
                C: 40.0
                F: .inf
            """
        lines = [
            f"Epoch {e}/5 distortion={v}" for e, v in enumerate([60.0, 45.0, 30.0, 22.0, 15.0], 1)
        ]
        frames = _told(project, lines, config=config)
        assert {f.primary_metric for f in frames} == {"distortion"}
        # The bands rise from A to F, so lower is better: 15 is within B's 20.
        assert frames[-1].grade is Grade.B


class TestTheBandsSayWhichWayTheyRun:
    def test_an_error_s_bands_rise_and_a_score_s_fall(self) -> None:
        assert bands_lower_better({"A": 1.0, "B": 2.5, "F": float("inf")}) is True
        assert bands_lower_better({"A+": 0.95, "A": 0.9, "F": 0.0}) is False

    def test_one_band_cannot_say(self) -> None:
        assert bands_lower_better({"A": 0.9}) is None
        assert bands_lower_better({"A": 0.9, "F": float("-inf")}) is None

    def test_compute_grade_takes_the_direction_it_is_given(self) -> None:
        bands = {"A": 1.0, "B": 2.5, "F": float("inf")}
        got = compute_grade(TaskType.CLASSIFICATION, 2.0, custom_thresholds=bands, direction=True)
        assert got is Grade.B


# ── A file with something wrong in it ────────────────────────────────────────


class TestProblemsAreReportedNotGuessed:
    def _load(self, tmp_path: Path, text: str) -> GradeConfig | None:
        path = tmp_path / ".epochix.yaml"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return load_grade_config(path)

    def test_an_unknown_grade_is_dropped_and_named(self, tmp_path: Path) -> None:
        config = self._load(
            tmp_path,
            """\
            grade_thresholds:
              classification:
                "A++": 0.99
                A: 0.9
                F: 0.0
            """,
        )
        assert config is not None
        assert config.grade_thresholds["classification"] == {"A": 0.9, "F": 0.0}
        assert any("'A++' is not a grade" in p for p in config.problems)

    def test_a_threshold_that_is_not_a_number_is_dropped_and_named(self, tmp_path: Path) -> None:
        config = self._load(
            tmp_path,
            """\
            grade_thresholds:
              classification:
                A: high
                B: 0.8
                F: 0.0
            """,
        )
        assert config is not None
        assert config.grade_thresholds["classification"] == {"B": 0.8, "F": 0.0}
        assert any("threshold for A is not a number" in p for p in config.problems)

    def test_thresholds_out_of_order_are_not_used(self, tmp_path: Path) -> None:
        """Neither rising nor falling: there is no reading of it that is not a guess."""
        config = self._load(
            tmp_path,
            """\
            grade_thresholds:
              classification:
                A: 0.9
                B: 0.95
                C: 0.6
            """,
        )
        assert config is not None
        assert "classification" not in config.grade_thresholds
        assert any("not in order" in p for p in config.problems)

    def test_a_file_that_is_not_yaml_says_so(self, tmp_path: Path) -> None:
        path = tmp_path / ".epochix.yaml"
        path.write_text("grade_thresholds: [unclosed\n", encoding="utf-8")
        assert load_grade_config(path) is None
        assert "not valid YAML" in (config_error(path) or "")


# ── `epochix check` says what is in effect ───────────────────────────────────


class TestCheck:
    def _check(self, project: Path, lines: list[str]) -> str:
        log = project / "run.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = runner.invoke(app, ["check", str(log)])
        assert result.exit_code == 0, result.output
        return result.output

    def test_no_file(self, project: Path) -> None:
        assert re.search(r"thresholds\s+built-in", self._check(project, _accuracy_log()))

    def test_a_file_that_applies(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        out = self._check(project, _accuracy_log())
        assert ".epochix.yaml" in out
        assert "val_accuracy is graded on its thresholds" in out

    def test_a_file_that_does_not_apply_to_this_log(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(STRICT, encoding="utf-8")
        out = self._check(project, [f"Epoch {e}/5 train_loss={1 / e:.3f}" for e in range(1, 6)])
        assert "no entry applies to this run, which is told by train_loss" in out
        assert "the file sets: classification" in out

    def test_a_file_that_cannot_be_read(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text("grade_thresholds: [unclosed\n", encoding="utf-8")
        out = self._check(project, _accuracy_log())
        assert "not used: it is not valid YAML" in out

    def test_a_problem_in_the_file_is_shown(self, project: Path) -> None:
        (project / ".epochix.yaml").write_text(
            'grade_thresholds:\n  classification:\n    "A++": 0.99\n    A: 0.9\n    F: 0.0\n',
            encoding="utf-8",
        )
        assert "'A++' is not a grade" in self._check(project, _accuracy_log())


# ── The example file and the README ──────────────────────────────────────────

_COMMENTED_YAML = re.compile(r'^  # ((?:  )?(?:"[^"]+"|[A-Za-z_][\w+-]*):(?: .*)?)$')


def _uncommented(text: str) -> str:
    """The example with every commented-out entry switched on."""
    out = []
    for line in text.splitlines():
        match = _COMMENTED_YAML.match(line)
        out.append("  " + match.group(1) if match else line)
    return "\n".join(out) + "\n"


class TestTheExampleFile:
    EXAMPLE = REPO / ".epochix.example.yaml"

    def test_the_repository_has_no_live_thresholds_file(self) -> None:
        """One at the root would be picked up by every run made from a checkout."""
        assert not (REPO / ".epochix.yaml").exists()

    def test_copied_as_it_is_it_changes_nothing(self) -> None:
        config = load_grade_config(self.EXAMPLE)
        assert config is not None
        assert config.grade_thresholds == {}
        assert config.metric_thresholds == {}
        assert config.lower_better_override == {}
        assert config.problems == []

    def test_every_entry_in_it_loads_when_switched_on(self, tmp_path: Path) -> None:
        path = tmp_path / ".epochix.yaml"
        path.write_text(_uncommented(self.EXAMPLE.read_text(encoding="utf-8")), encoding="utf-8")
        config = load_grade_config(path)
        assert config is not None
        assert config.problems == []
        assert set(config.grade_thresholds) == {
            "classification",
            "detection",
            "segmentation",
            "nlp",
            "biometric",
            "gaze",
            "regression",
            "generative",
            "custom",
        }
        assert list(config.metric_thresholds) == ["val_f1"]

    @pytest.mark.parametrize(
        "task",
        [
            TaskType.CLASSIFICATION,
            TaskType.DETECTION,
            TaskType.SEGMENTATION,
            TaskType.NLP,
            TaskType.BIOMETRIC,
            TaskType.GAZE,
        ],
    )
    def test_the_values_it_calls_built_in_are(self, tmp_path: Path, task: TaskType) -> None:
        """So switching an entry on without editing it changes nothing."""
        path = tmp_path / ".epochix.yaml"
        path.write_text(_uncommented(self.EXAMPLE.read_text(encoding="utf-8")), encoding="utf-8")
        config = load_grade_config(path)
        assert config is not None
        built_in = {grade.value: value for grade, value in _DEFAULT_THRESHOLDS[task]}
        stated = config.grade_thresholds[task.value]
        # A task whose built-in bands stop at D has no F row: below D is F.
        assert set(stated) - set(built_in) <= {"F"}
        assert set(built_in) - set(stated) <= {"F"}
        for label in set(stated) & set(built_in):
            assert stated[label] == built_in[label], label


class TestTheReadmeExample:
    def _yaml(self) -> str:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        match = re.search(
            r"<!-- readme-example:thresholds -->\n```yaml\n(.*?)```\n<!-- /readme-example:thresholds -->",
            readme,
            re.S,
        )
        # Guard: an example that vanished must fail here, not pass by checking nothing.
        assert match, "README lost its marked thresholds example"
        return match.group(1)

    def test_it_loads_without_a_problem(self, tmp_path: Path) -> None:
        path = tmp_path / ".epochix.yaml"
        path.write_text(self._yaml(), encoding="utf-8")
        config = load_grade_config(path)
        assert config is not None and config.problems == []
        assert set(config.grade_thresholds) == {"classification"}
        assert set(config.metric_thresholds) == {"val_f1"}

    def test_it_does_what_the_readme_says(self, project: Path) -> None:
        """A+ at 0.97: a run at 96% is an A, where the built-in bands say A+."""
        lines = [
            f"Epoch {e}/5 val_accuracy={v}" for e, v in enumerate([0.8, 0.9, 0.93, 0.95, 0.96], 1)
        ]
        assert _told(project, lines, config=None)[-1].grade is Grade.A_PLUS
        assert _told(project, lines, config=self._yaml())[-1].grade is Grade.A
