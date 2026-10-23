"""Every log in the repository says whether it is a recording.

Fifteen of the test logs were written by hand in the shape of a framework's
output and named after it, and nothing said so. Four were the shape of
nothing a library prints — `pytorch_lightning_30ep.log` is not Lightning's
layout, and `yolo_100ep.log` is no version of Ultralytics' — yet tests pinned
them as that framework's output, and every new check (the corpus truth, the
parser golden) pinned them again. Real Lightning output went unread for the
life of the project behind exactly such a sample.

So each folder's README lists its logs as recorded runs, with the script that
produced each, or as format samples, with the layout each imitates. This
fails when a log is in neither list, in both, or names a script that is not
there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = [ROOT / "demo", ROOT / "tests" / "fixtures" / "logs"]


def _sections(readme: Path) -> dict[str, str]:
    text = readme.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    return {part.split("\n", 1)[0].strip(): part for part in parts[1:]}


def _rows(section: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("| `")
    ]


def _logs_named(section: str) -> set[str]:
    """The logs a section lists: a table's first column (its other columns
    point at related logs), or, where the section is prose, every log it names."""
    rows = _rows(section)
    if rows:
        return {row[0].strip("`") for row in rows}
    return set(re.findall(r"`([\w.-]{1,80}\.log)`", section))


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda p: p.name)
def test_every_log_is_a_recording_or_a_sample(folder: Path) -> None:
    sections = _sections(folder / "README.md")
    recorded = _logs_named(sections["Recorded runs"])
    samples = _logs_named(sections["Format samples"])
    logs = {p.name for p in folder.glob("*.log")}
    assert len(logs) >= 5, f"{folder} lost its logs"
    # Only this folder's logs count; a row may point at a log elsewhere.
    recorded &= logs
    samples &= logs
    assert not recorded & samples, f"listed as both: {sorted(recorded & samples)}"
    assert sorted(logs - recorded - samples) == [], "say in the README what these are"


def test_a_log_named_real_is_a_recording() -> None:
    folder = ROOT / "tests" / "fixtures" / "logs"
    sections = _sections(folder / "README.md")
    samples = _logs_named(sections["Format samples"])
    assert sorted(n for n in samples if "_real" in n) == []


def test_every_recording_names_a_script_that_exists() -> None:
    folder = ROOT / "tests" / "fixtures" / "logs"
    rows = _rows(_sections(folder / "README.md")["Recorded runs"])
    assert len(rows) >= 10
    unkept = []
    for row in rows:
        log, script = row[0].strip("`"), row[-1]
        assert (folder / log).is_file(), f"{log} is listed but missing"
        if script == "not kept":
            unkept.append(log)
            continue
        path = re.match(r"`([^`]{1,120})`", script)
        assert path, f"{log}: no script named"
        assert (folder / path.group(1)).resolve().is_file(), f"{log}: {path.group(1)} missing"
    # accelerate_real.log and fastai_real.log were the last two, captured in
    # 0.5.16 without their scripts and recorded again. A recording ships with
    # the script that produced it.
    assert unkept == []


def test_the_demo_recordings_have_their_scripts() -> None:
    folder = ROOT / "demo"
    rows = _rows(_sections(folder / "README.md")["Recorded runs"])
    assert len(rows) >= 3
    for row in rows:
        script = re.match(r"`([^`]{1,120})`", row[-1])
        assert script and (folder / script.group(1)).is_file(), row[0]
