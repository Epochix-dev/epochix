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
