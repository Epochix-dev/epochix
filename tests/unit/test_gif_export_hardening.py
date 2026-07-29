"""The GIF renderer draws untrusted input, so it gets an adversarial test.

A run name comes from a log file, and a log file is whatever the training
process wrote — which on a shared machine or in CI is not necessarily under the
reader's control. `build_gif` is also a public function that will be reachable
over HTTP once the dashboard's Record button lands, so its parameters are
attacker-reachable too.

Three classes were open before this:

* **Dimension bomb.** ``width``/``height`` decided the allocation with no
  bound. 20000x20000 is ~1.2 GB *per frame*, times dozens of frames.
* **Bidi and control characters in a label.** ``safe\\u202egnp.exe`` renders as
  ``safeexe.gnp`` — a name that lies about what it is.
* **Unbounded label length.** 100k characters cost 4.6 s of free CPU and drew
  almost entirely off-canvas.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

pytest.importorskip("PIL", reason="GIF export needs the 'gif' extra")

from epochix.exporters.gif_export import (  # noqa: E402
    _MAX_DIM,
    _MAX_NAME_CHARS,
    _MIN_DIM,
    _safe_label,
    build_gif,
)


def _run(tmp_path: Path, name: str = "a run") -> tuple[str, RunStore]:
    log = tmp_path / "train.log"
    log.write_text(
        "".join(f"Epoch {i}/6 val_acc={0.30 + 0.1 * i:.4f}\n" for i in range(1, 7)),
        encoding="utf-8",
    )
    db = str(tmp_path / "runs.db")
    return parse(log, db=db, run_name=name).id, RunStore(db_path=db)


@pytest.mark.parametrize(
    ("width", "height"),
    [(20000, 20000), (10**6, 10**6), (0, 0), (-5, -5)],
)
def test_caller_supplied_dimensions_cannot_decide_the_allocation(
    width: int, height: int, tmp_path: Path
) -> None:
    """20000x20000 is ~1.2 GB per frame; the caller must not get to ask."""
    from PIL import Image

    run_id, store = _run(tmp_path)
    img = Image.open(io.BytesIO(build_gif(run_id=run_id, store=store, width=width, height=height)))
    assert _MIN_DIM <= img.size[0] <= _MAX_DIM
    assert _MIN_DIM <= img.size[1] <= _MAX_DIM


def test_a_bidi_override_cannot_disguise_the_name() -> None:
    """U+202E reverses what follows: "safe\\u202egnp.exe" *displays* as
    "safeexe.gnp". A label must not be able to lie about itself."""
    out = _safe_label("safe‮gnp.exe")
    assert "‮" not in out
    assert out == "safegnp.exe"


def test_control_characters_are_stripped() -> None:
    out = _safe_label("a\x00b\x07c\x1bd")
    assert all(ch.isprintable() or ch == " " for ch in out), repr(out)


def test_newlines_cannot_break_the_layout() -> None:
    assert "\n" not in _safe_label("l1\nl2\rl3\tl4")


def test_a_label_is_length_capped() -> None:
    assert len(_safe_label("A" * 100_000)) <= _MAX_NAME_CHARS


def test_an_empty_or_all_control_label_still_renders() -> None:
    """Stripping must not leave an empty string the renderer then chokes on."""
    assert _safe_label("") == "run"
    assert _safe_label("\x00\x01\x02") == "run"


def test_a_hostile_name_still_produces_a_valid_gif(tmp_path: Path) -> None:
    from PIL import Image

    run_id, store = _run(tmp_path, name="‮" + "X" * 50_000 + "\x00\x1b[31m")
    img = Image.open(io.BytesIO(build_gif(run_id=run_id, store=store)))
    assert img.format == "GIF"
    assert img.n_frames > 1


def test_fps_is_bounded(tmp_path: Path) -> None:
    """A zero or negative fps would divide by zero in the frame duration."""
    run_id, store = _run(tmp_path)
    for fps in (0, -10, 10**9):
        assert build_gif(run_id=run_id, store=store, fps=fps)
