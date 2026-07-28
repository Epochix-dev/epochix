"""Compare two runs side-by-side."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from epochix.console import console_safe

if TYPE_CHECKING:
    from epochix.models import Run


@dataclass
class RunDiff:
    """Result of :func:`compare` — a side-by-side comparison of two runs."""

    run_a: Run
    run_b: Run
    grade_delta: str = ""
    summary: str = ""
    #: Plain-English account of WHY the runs differ — the part a curve overlay
    #: cannot tell you. Empty when the runs have too little data to compare.
    narrative: str = ""
    better: str = ""  # "a", "b", or "tie"
    metric_diffs: dict[str, tuple[float, float]] = field(default_factory=dict)

    def show(self) -> None:
        """Print a summary to stdout."""
        a, b = self.run_a, self.run_b
        ga = a.final_grade.value if a.final_grade else "—"
        gb = b.final_grade.value if b.final_grade else "—"
        print(f"\n  Run A: {a.name or a.id}  [{ga}]  task={a.task_type.value}")
        print(f"  Run B: {b.name or b.id}  [{gb}]  task={b.task_type.value}")
        if self.better == "a":
            print(console_safe(f"  → Run A wins  ({self.grade_delta})"))
        elif self.better == "b":
            print(console_safe(f"  → Run B wins  ({self.grade_delta})"))
        else:
            print(console_safe("  → Tie"))
        if self.summary:
            print(f"\n  {self.summary}")
        for key, (va, vb) in self.metric_diffs.items():
            arrow = "↑" if va < vb else ("↓" if va > vb else "=")
            print(f"  {key:24s}  {va:.4f}  {arrow}  {vb:.4f}")
        print()


def compare(
    run_a: Run | str,
    run_b: Run | str,
    *,
    db: str | None = None,
) -> RunDiff:
    """Compare two runs and return a :class:`RunDiff`.

    Parameters
    ----------
    run_a, run_b:
        Either a :class:`~epochix.models.Run` object, or a path to a
        JSON export file (produced by ``epochix export --format json``).
    db:
        SQLite DB path (used when *run_a*/*run_b* is a run ID string).

    Returns
    -------
    RunDiff
    """

    a = _resolve(run_a, db=db)
    b = _resolve(run_b, db=db)

    # Grade comparison
    from epochix.enums import Grade

    _GRADE_ORDER = list(Grade)
    ga_idx = _GRADE_ORDER.index(a.final_grade) if a.final_grade else len(_GRADE_ORDER)
    gb_idx = _GRADE_ORDER.index(b.final_grade) if b.final_grade else len(_GRADE_ORDER)

    if ga_idx < gb_idx:
        better = "a"
        ga_str = a.final_grade.value if a.final_grade else "?"
        gb_str = b.final_grade.value if b.final_grade else "?"
        grade_delta = f"{ga_str} vs {gb_str}"
    elif gb_idx < ga_idx:
        better = "b"
        gb_str = b.final_grade.value if b.final_grade else "?"
        ga_str = a.final_grade.value if a.final_grade else "?"
        grade_delta = f"{gb_str} vs {ga_str}"
    else:
        better = "tie"
        grade_delta = "equal"

    summary = (
        f"Run {'A' if better == 'a' else 'B'} achieves a better grade ({grade_delta})."
        if better != "tie"
        else "Both runs achieved the same grade."
    )

    return RunDiff(
        run_a=a,
        run_b=b,
        grade_delta=grade_delta,
        summary=summary,
        better=better,
        narrative=_comparison_narrative(a, b, db=db),
    )


def _comparison_narrative(a: Run, b: Run, *, db: str | None) -> str:
    """Best-effort explanation of the difference; never fatal to `compare`."""
    from epochix.config import get_settings
    from epochix.store.sqlite_store import RunStore
    from epochix.story_engine.comparison import narrate_comparison, trajectory_from_frames

    try:
        store = RunStore(db_path=db or get_settings().db)
        trajectories = []
        for run in (a, b):
            traj = trajectory_from_frames(
                run.name or run.id,
                list(store.get_story_frames(run.id)),
                grade=run.final_grade.value if run.final_grade else None,
            )
            if traj is not None:
                trajectories.append(traj)
        if len(trajectories) < 2:
            return ""
        return narrate_comparison(trajectories)
    except Exception:  # noqa: BLE001 - a missing DB must not break comparison
        return ""


def _resolve(run_or_path: Run | str, db: str | None) -> Run:
    from epochix.models import Run as RunModel

    if isinstance(run_or_path, RunModel):
        return run_or_path

    path_candidate = run_or_path
    import json
    from pathlib import Path

    p = Path(path_candidate)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        return RunModel.model_validate(data["run"])

    # Treat as run_id → look up in DB
    from epochix.config import get_settings
    from epochix.store.sqlite_store import RunStore

    settings = get_settings()
    store = RunStore(db_path=db or settings.db)
    run = store.get_run(path_candidate)
    if run is None:
        raise ValueError(f"Run not found: {path_candidate!r}")
    return run
