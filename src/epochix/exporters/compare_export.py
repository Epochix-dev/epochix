"""Several runs side by side, as a document you can send.

The comparison view overlays the runs' curves and explains the difference in
a paragraph, and none of it could leave the browser: the race GIF animates the
curves, but the explanation and the numbers behind it — each run's grade, its
final and best values, where the best was — existed only on screen. This is
the written version, from the same narrative the view shows, as Markdown or as
a PDF. Both are built from one :class:`Comparison`, so they cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from epochix.exporters.markdown_export import _code_safe, _md_escape
from epochix.i18n import t
from epochix.story_engine.comparison import (
    RunTrajectory,
    narrate_comparison,
    run_labels,
    run_trajectories,
)

if TYPE_CHECKING:
    from epochix.models import Run
    from epochix.store.sqlite_store import RunStore


@dataclass(frozen=True)
class ComparisonRow:
    """One run's line in the comparison table, as display strings."""

    label: str
    grade: str
    metric: str
    final: str
    best: str
    epochs: str
    # How the letter was reached, then the grade note, as sentences in the
    # comparison's language; "" when there is neither. Two runs graded the two
    # different ways have letters that do not compare, and the table said
    # nothing about it.
    note: str


@dataclass(frozen=True)
class Comparison:
    """Everything a comparison document says, in *locale*."""

    locale: str
    runs: list[Run]
    narrative: str
    rows: list[ComparisonRow]
    # Runs with a curve to draw, labelled as in the rows.
    trajectories: list[RunTrajectory]

    @property
    def has_notes(self) -> bool:
        return any(row.note for row in self.rows)

    def headers(self) -> list[str]:
        head = [
            t("cmp.run", self.locale),
            t("md.grade", self.locale),
            t("md.primary_metric", self.locale),
            t("col.final", self.locale),
            t("cover.best", self.locale),
            t("md.epochs", self.locale),
        ]
        if self.has_notes:
            head.append(t("md.grade_note", self.locale))
        # Some of these keys are lower-case column labels elsewhere ("final", "best").
        return [h[:1].upper() + h[1:] for h in head]


def build_comparison(run_ids: list[str], store: RunStore, locale: str | None = None) -> Comparison:
    """The comparison of *run_ids*, in *locale* or the first run's language.

    Raises ValueError for an unknown id or fewer than two runs.
    """
    if len(run_ids) < 2:
        raise ValueError("A comparison needs at least two runs.")
    runs: list[Run] = []
    for rid in run_ids:
        run = store.get_run(rid)
        if run is None:
            raise ValueError(f"Run not found: {rid!r}")
        runs.append(run)
    if locale is None:
        locale = str(runs[0].config.get("locale", "en")) if runs[0].config else "en"

    frames = [store.get_story_frames(run.id) for run in runs]
    trajectories = run_trajectories(list(zip(runs, frames, strict=True)))
    labels = run_labels(runs)
    usable = [tr for tr in trajectories if tr is not None]

    rows: list[ComparisonRow] = []
    for run, run_frames, traj, label in zip(runs, frames, trajectories, labels, strict=True):
        grade = run.final_grade.value if run.final_grade else "—"
        if traj is not None:
            metric = traj.primary_metric
            final = f"{traj.final_value:.4g}"
            best_epoch, best_value = traj.best
            best = f"{best_value:.4g} ({t('cover.epoch_n', locale)} {best_epoch:g})"
            epochs = str(len(traj.values))
        elif run_frames:
            # One reading, or readings without epochs: no trajectory, but the
            # value is real and is shown as what it is.
            metric = run_frames[-1].primary_metric or run.primary_metric
            final = f"{run_frames[-1].primary_metric_value:.4g}"
            best, epochs = "—", str(len(run_frames))
        else:
            metric, final, best, epochs = run.primary_metric, "—", "—", "0"
        last = run_frames[-1] if run_frames else None
        sentences = []
        if last is not None and last.grade_basis is not None:
            sentences.append(t(f"grade_basis.{last.grade_basis}", locale))
        if last is not None and last.grade_note is not None:
            sentences.append(t(f"grade_note.{last.grade_note}", locale))
        note = " ".join(sentences)
        rows.append(ComparisonRow(label, grade, metric, final, best, epochs, note))

    return Comparison(
        locale=locale,
        runs=runs,
        # The same paragraph the comparison view shows, including its refusals:
        # runs on different metrics, or too short to compare, are said to be so.
        narrative=narrate_comparison(usable, locale),
        rows=rows,
        trajectories=usable,
    )


def build_comparison_markdown(
    run_ids: list[str], store: RunStore, locale: str | None = None
) -> str:
    """A Markdown comparison of *run_ids*, in *locale* or the first run's language.

    Raises ValueError for an unknown id or fewer than two runs.
    """
    cmp = build_comparison(run_ids, store, locale)
    lines = [f"# {t('cmp.title', cmp.locale)}", "", cmp.narrative, ""]
    head = cmp.headers()
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "---|" * len(head))
    for row in cmp.rows:
        cells = [
            _md_escape(row.label),
            f"**{row.grade}**",
            f"`{_code_safe(row.metric)}`",
            row.final,
            row.best,
            row.epochs,
        ]
        if cmp.has_notes:
            cells.append(row.note)
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "---", ""]
    ids = ", ".join(f"`{run.id}`" for run in cmp.runs)
    lines.append(f"*Generated by [epochix](https://github.com/epochix-dev/epochix) · {ids}*")
    lines.append("")
    return "\n".join(lines)


def build_comparison_pdf(run_ids: list[str], store: RunStore, locale: str | None = None) -> bytes:
    """The same comparison as a PDF: the narrative, the curves overlaid, the table.

    Raises ValueError for an unknown id or fewer than two runs.
    """
    from epochix.exporters._pdf_render import pdf_can_draw, render_comparison_pdf

    cmp = build_comparison(run_ids, store, locale)
    if pdf_can_draw(cmp.locale):
        return render_comparison_pdf(cmp)
    # Farsi without the text shaper: an English document that says why,
    # as the single-run report does, rather than a page of question marks.
    return render_comparison_pdf(build_comparison(run_ids, store, "en"), fell_back=True)
