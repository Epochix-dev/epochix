"""A model that isn't learning must not be narrated as if it were.

Reported from a real run: a Fashion-MNIST CNN stuck at ~11 % accuracy (chance
is 10 % for 10 classes) was narrated "Loss curves bend downward. The model is a
diligent student." and "Patterns are starting to click." The phase templates are
driven by how far through training we are, not by whether the metric moved — so
the story asserted progress the data does not show.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from epochix import parse

if TYPE_CHECKING:
    from pathlib import Path

# Phrases that claim progress. None may appear for a run that made none.
_PROGRESS_CLAIMS = re.compile(
    r"diligent student|patterns are starting|bend downward|upward trend"
    r"|crystallise|steady progress|improvement continues",
    re.IGNORECASE,
)


def _narratives(tmp_path: Path, lines: list[str], locale: str = "en") -> list[str]:
    from epochix.store.sqlite_store import RunStore

    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t", locale=locale)
    return [f.narrative for f in RunStore(db_path=db).get_story_frames(run.id)]


def _stuck_lines() -> list[str]:
    # 10-class problem pinned at chance (10%): 0.101 -> 0.116 is noise.
    return ["device=cpu epochs=20"] + [
        f"Epoch {e}/20 train_loss=2.3010 val_accuracy={a:.4f}"
        for e, a in enumerate([0.101, 0.108, 0.112, 0.116], 1)
    ]


# Any of the honest stalled phrasings (the template has several variants).
_STALL_PHRASES = re.compile(
    r"not learning|no meaningful progress|barely moved|essentially where it started",
    re.IGNORECASE,
)


def test_a_stuck_run_is_not_praised(tmp_path: Path) -> None:
    narratives = _narratives(tmp_path, _stuck_lines())
    assert narratives, "no frames produced"
    last = narratives[-1]
    assert not _PROGRESS_CLAIMS.search(last), f"claimed progress for a stuck run: {last!r}"
    assert _STALL_PHRASES.search(last), f"did not say the run is stuck: {last!r}"


def test_a_stuck_run_says_what_to_check(tmp_path: Path) -> None:
    """The message should be actionable, not just negative."""
    text = " ".join(_narratives(tmp_path, _stuck_lines())).lower()
    assert "learning rate" in text or "setup problem" in text, text


def test_a_learning_run_is_still_encouraged(tmp_path: Path) -> None:
    """No false positives — a model that really improves keeps its story."""
    lines = ["device=cpu epochs=20"] + [
        f"Epoch {e}/20 train_loss={0.9 - e * 0.1:.4f} val_accuracy={a:.4f}"
        for e, a in enumerate([0.42, 0.61, 0.74, 0.83, 0.88], 1)
    ]
    last = _narratives(tmp_path, lines)[-1]
    assert "not learning" not in last.lower(), last
    assert "no meaningful progress" not in last.lower(), last


def test_slow_but_real_improvement_is_not_called_stalled(tmp_path: Path) -> None:
    """40% -> 56% is genuine progress, just unspectacular."""
    lines = ["device=cpu epochs=20"] + [
        f"Epoch {e}/20 train_loss={0.9 - e * 0.02:.4f} val_accuracy={a:.4f}"
        for e, a in enumerate([0.40, 0.44, 0.48, 0.52, 0.56], 1)
    ]
    last = _narratives(tmp_path, lines)[-1]
    assert "not learning" not in last.lower(), last


def test_the_stalled_message_is_localised(tmp_path: Path) -> None:
    last = _narratives(tmp_path, _stuck_lines(), locale="fa")[-1]
    assert re.search(r"[؀-ۿ]", last), f"expected Persian, got {last!r}"


def test_every_stalled_variant_is_actionable() -> None:
    """Variant choice is seeded by the run id, so ONE unhelpful variant means a
    random third of users get a dead end — and a randomly failing test.
    """
    from epochix.story_engine.narrator import _load_stalled

    for variant in _load_stalled("en"):
        low = variant.lower()
        assert "learning rate" in low or "setup problem" in low, (
            f"stalled variant offers nothing to check: {variant!r}"
        )


# "Stalled" and "past peak" are different diagnoses with different fixes, and
# the stalled test ran first. `rel` is the fraction of achievable improvement
# realised, so a run that got WORSE scores below zero and satisfies "less than
# 3% improvement" just as a flat run does. A classic overfit — val_accuracy
# 0.79 -> 0.60 while train loss kept falling — was therefore narrated "the
# metric has barely moved ... the model is not learning yet", on the same
# screen as the overfitting warning it had triggered, and sent the reader after
# a learning-rate or data-pipeline bug that was not there.

_DECLINE_PHRASES = re.compile(
    r"passed its peak|past its best|slipped from|not improving on it",
    re.IGNORECASE,
)


def _overfitting_lines() -> list[str]:
    """Train loss falls, validation accuracy falls with it — textbook overfit."""
    rows = [(1, 0.9000, 0.7920), (2, 0.7000, 0.7600), (3, 0.5200, 0.7100)]
    rows += [(4, 0.3600, 0.6700), (5, 0.2400, 0.6300), (6, 0.1500, 0.6000)]
    return ["device=cpu epochs=6"] + [
        f"Epoch {e}/6 train_loss={tr:.4f} val_accuracy={va:.4f}" for e, tr, va in rows
    ]


def test_a_falling_metric_is_not_called_barely_moved(tmp_path: Path) -> None:
    last = _narratives(tmp_path, _overfitting_lines())[-1]
    assert not _STALL_PHRASES.search(last), (
        f"a 0.79 -> 0.60 decline was narrated as a stall: {last!r}"
    )


def test_a_falling_metric_is_named_as_a_decline(tmp_path: Path) -> None:
    last = _narratives(tmp_path, _overfitting_lines())[-1]
    assert _DECLINE_PHRASES.search(last), f"never said the run fell: {last!r}"


def test_the_decline_narrative_carries_the_real_numbers(tmp_path: Path) -> None:
    """No fabricated figures: both the peak and the current value must appear."""
    last = _narratives(tmp_path, _overfitting_lines())[-1]
    assert "0.7920" in last, f"peak value missing: {last!r}"
    assert "0.6000" in last, f"current value missing: {last!r}"


def test_a_genuinely_flat_run_is_still_called_stalled(tmp_path: Path) -> None:
    """The guard must not swallow the stalled diagnosis it is narrowing.

    Noise around a fixed level dips below its own best, so an unguarded
    "any drop from peak wins" would have turned every stuck run into a
    past-peak report and lost the actionable advice entirely.
    """
    last = _narratives(tmp_path, _stuck_lines())[-1]
    assert _STALL_PHRASES.search(last), f"flat run lost its stalled message: {last!r}"
