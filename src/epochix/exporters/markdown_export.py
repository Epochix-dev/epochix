"""Markdown export — plain-English summary of a training run."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from epochix.store.sqlite_store import RunStore

# Characters that turn text into markup. A run name comes from a log file, and
# these exports get pasted into VS Code previews, Notion and README renderers —
# several of which honour raw HTML, and most of which honour a link.
_MD_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _md_escape(text: str) -> str:
    """Escape a log-derived string so it renders as the text it is.

    Without this, a run named ``[click](javascript:alert(1))`` exports as a
    working link, and ``<script>`` survives into any renderer that allows
    inline HTML. Neither is a name — both are markup the log author chose.
    """
    return _MD_SPECIALS.sub(r"\\\1", _CONTROL.sub("", text)).replace("\n", " ").replace("\r", " ")


def _code_safe(text: str) -> str:
    """Make a string safe *inside* a code span.

    Backslash escapes do not apply within backticks, so the only thing that can
    escape a code span is another backtick. Drop them, along with the pipe that
    would otherwise end the table cell.
    """
    return _CONTROL.sub("", text).replace("`", "").replace("|", "\\|").replace("\n", " ")


_GRADE_EMOJI: dict[str, str] = {
    "A+": "🏆",
    "A": "🥇",
    "A-": "🥈",
    "B+": "🥉",
    "B": "✅",
    "B-": "👍",
    "C+": "🙂",
    "C": "😐",
    "C-": "😕",
    "D": "⚠️",
    "F": "❌",
    "I": "⏳",
}

_PHASE_LABEL: dict[str, str] = {
    "awakening": "🌱 Awakening",
    "learning": "📚 Learning",
    "understanding": "💡 Understanding",
    "mastering": "⚡ Mastering",
    "polishing": "✨ Polishing",
}

_MILESTONE_EMOJI: dict[str, str] = {
    "first_above_25": "🎯",
    "first_above_50": "🌟",
    "first_above_75": "🚀",
    "first_above_90": "🏆",
    "best_so_far": "✅",
    "biggest_jump": "⚡",
    "overfit_warning": "⚠️",
    "plateau": "😴",
    "lr_drop": "📉",
    "divergence": "💥",
    "training_complete": "🎓",
}


def build_markdown(run_id: str, store: RunStore) -> str:
    """Build a Markdown summary for a finished run.

    Returns
    -------
    str
        UTF-8 Markdown document.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)

    lines: list[str] = []

    # ── Title & metadata ──────────────────────────────────────────────────
    title = _md_escape(run.name or run.id)
    lines.append(f"# {title}")
    lines.append("")

    grade_str = run.final_grade.value if run.final_grade else "—"
    grade_emoji = _GRADE_EMOJI.get(grade_str, "")
    task_str = run.task_type.value if run.task_type else "custom"
    phase_str = ""
    if frames:
        last_phase = frames[-1].phase
        phase_str = _PHASE_LABEL.get(last_phase.value if last_phase else "", "")

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Grade** | {grade_emoji} **{grade_str}** |")
    lines.append(f"| **Task** | {task_str} |")
    lines.append(f"| **Final phase** | {phase_str or '—'} |")
    lines.append(f"| **Primary metric** | {_md_escape(str(run.primary_metric))} |")
    if run.total_epochs_est:
        lines.append(f"| **Epochs** | {run.total_epochs_est} |")
    if run.framework_detected:
        lines.append(f"| **Framework** | {run.framework_detected} |")
    if run.finished_at:
        lines.append(f"| **Finished** | {run.finished_at.strftime('%Y-%m-%d %H:%M')} |")
    lines.append("")

    # ── Story summary ─────────────────────────────────────────────────────
    if run.story_summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(run.story_summary)
        lines.append("")

    # ── Final narrative ───────────────────────────────────────────────────
    if frames:
        last = frames[-1]
        if last.narrative:
            lines.append("## Final State")
            lines.append("")
            lines.append(f"*{last.narrative}*")
            lines.append("")

    # ── Key metrics ───────────────────────────────────────────────────────
    if events:
        # Latest value per canonical key
        latest: dict[str, float] = {}
        for ev in events:
            latest[ev.canonical_key] = ev.value

        lines.append("## Key Metrics")
        lines.append("")
        lines.append("| Metric | Final Value |")
        lines.append("|--------|-------------|")
        for key, val in sorted(latest.items()):
            lines.append(f"| `{_code_safe(key)}` | `{val:.4f}` |")
        lines.append("")

    # ── Milestones ────────────────────────────────────────────────────────
    milestone_frames = [f for f in frames if f.milestones]
    if milestone_frames:
        lines.append("## Milestones")
        lines.append("")
        for frame in milestone_frames:
            for m in frame.milestones:
                emoji = _MILESTONE_EMOJI.get(m.kind, "📌")
                epoch_str = f" (epoch {frame.epoch})" if frame.epoch is not None else ""
                msg = m.message or m.kind.replace("_", " ").title()
                lines.append(f"- {emoji} **{msg}**{epoch_str}")
        lines.append("")

    # ── Warnings ─────────────────────────────────────────────────────────
    warning_frames = [f for f in frames if f.warnings]
    if warning_frames:
        lines.append("## Warnings")
        lines.append("")
        seen: set[str] = set()
        for frame in warning_frames:
            for w in frame.warnings:
                if w.message not in seen:
                    seen.add(w.message)
                    lines.append(f"> ⚠️ {w.message}")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    repo = "https://github.com/epochix-dev/epochix"
    lines.append(f"*Generated by [epochix]({repo}) · Run ID: `{run_id}`*")
    lines.append("")

    return "\n".join(lines)
