"""An installed exporter plugin is used by `epochix export` and the server.

`docs/plugins.md` has documented the `epochix.exporters` entry point and
`epochix export <run-id> --format latex` for the life of the project. Nothing
loaded the group: with a real plugin installed (`uv pip install` into a
scratch environment, 2026-11-18) the CLI answered "Unknown export format:
'latex'", and the server had no route for it. `test_plugins.py` registered
exporters by hand and read them back, so it passed throughout.

So these install one. A plugin is installed when its package and its
`.dist-info` folder, holding `entry_points.txt`, sit on the path: that is
what an installer writes, and `importlib.metadata` finds it the same way it
finds a pip-installed package. Nothing here calls `register_exporter`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epochix import export, parse
from epochix.config import Settings
from epochix.plugins import exporter_registry
from epochix.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "demo" / "pytorch_lightning.log"

_PACKAGE = """
from pathlib import Path


def export_latex(run, frames, events, output_path):
    # Bytes, so the file is the same on every platform.
    Path(output_path).write_bytes(
        f"% {run.id} grade={run.final_grade.value} frames={len(frames)} events={len(events)}\\n".encode()
    )


def export_broken(run, frames, events, output_path):
    raise RuntimeError("the plugin's own bug")


def export_nothing(run, frames, events, output_path):
    return None


def export_markdown(run, frames, events, output_path):
    Path(output_path).write_text("PLUGIN MARKDOWN", encoding="utf-8")
"""

_ENTRY_POINTS = """[epochix.exporters]
latex = epochix_test_exporter:export_latex
broken = epochix_test_exporter:export_broken
silent = epochix_test_exporter:export_nothing
md = epochix_test_exporter:export_markdown
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    """A folder holding one installed plugin distribution."""
    root = tmp_path / "site"
    (root / "epochix_test_exporter").mkdir(parents=True)
    (root / "epochix_test_exporter" / "__init__.py").write_text(_PACKAGE, encoding="utf-8")
    dist = root / "epochix_test_exporter-0.1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: epochix-test-exporter\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (dist / "entry_points.txt").write_text(_ENTRY_POINTS, encoding="utf-8")
    (dist / "RECORD").write_text("", encoding="utf-8")
    return root


@pytest.fixture
def stored(tmp_path: Path) -> tuple[Path, str, str]:
    db = tmp_path / "runs.db"
    run = parse(LOG, db=str(db))
    assert run.final_grade is not None
    return db, run.id, run.final_grade.value


def _cli(*args: str, site: Path, db: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "epochix", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        cwd=str(cwd),
        env={
            **os.environ,
            "EPOCHIX_DB": str(db),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(site)]),
        },
        check=False,
    )


# ── the CLI ───────────────────────────────────────────────────────────────────


def test_the_documented_command_writes_the_plugins_format(
    site: Path, stored: tuple[Path, str, str], tmp_path: Path
) -> None:
    db, run_id, grade = stored
    out = tmp_path / "report.tex"

    done = _cli(
        "export", run_id, "--format", "latex", "--output", str(out), site=site, db=db, cwd=tmp_path
    )

    assert done.returncode == 0, done.stderr
    # The exporter was handed the stored run, its frames and its events.
    assert out.read_text(encoding="utf-8") == f"% {run_id} grade={grade} frames=14 events=70\n"


def test_run_export_reaches_it_too(site: Path, tmp_path: Path) -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = str(probe.getsockname()[1])
    out = tmp_path / "run.tex"

    done = _cli(
        "run", str(LOG), "--headless", "--export", "latex", "--output", str(out),
        "--port", port, site=site, db=tmp_path / "runs.db", cwd=tmp_path,
    )  # fmt: skip

    assert done.returncode == 0, done.stderr
    assert out.read_text(encoding="utf-8").startswith("% ")


def test_an_unknown_format_names_what_can_be_written_and_writes_nothing(
    site: Path, stored: tuple[Path, str, str], tmp_path: Path
) -> None:
    db, run_id, _ = stored
    out = tmp_path / "nowhere" / "x.nope"

    done = _cli(
        "export", run_id, "--format", "nope", "--output", str(out), site=site, db=db, cwd=tmp_path
    )

    assert done.returncode == 1
    assert "Unknown export format: 'nope'" in done.stderr
    assert "html, pdf, md, json, gif, broken, latex, silent." in done.stderr
    assert "Exporting" not in done.stdout + done.stderr
    assert not out.parent.exists()


def test_a_plugin_that_fails_or_writes_nothing_is_not_reported_as_written(
    site: Path, stored: tuple[Path, str, str], tmp_path: Path
) -> None:
    db, run_id, _ = stored

    broken = _cli("export", run_id, "-f", "broken", site=site, db=db, cwd=tmp_path)
    assert broken.returncode == 1
    assert "The 'broken' exporter (from epochix-test-exporter) failed" in broken.stderr
    assert "RuntimeError: the plugin's own bug" in broken.stderr

    silent = _cli("export", run_id, "-f", "silent", site=site, db=db, cwd=tmp_path)
    assert silent.returncode == 1
    assert "returned without writing" in silent.stderr
    assert not (tmp_path / f"{run_id}.silent").exists()


def test_a_plugin_cannot_replace_a_built_in_format(
    site: Path, stored: tuple[Path, str, str], tmp_path: Path
) -> None:
    db, run_id, grade = stored
    out = tmp_path / "run.md"

    done = _cli("export", run_id, "-f", "md", "-o", str(out), site=site, db=db, cwd=tmp_path)

    assert done.returncode == 0, done.stderr
    text = out.read_text(encoding="utf-8")
    assert "PLUGIN MARKDOWN" not in text
    assert grade in text


# ── the server ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(
    site: Path, stored: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.syspath_prepend(str(site))
    exporter_registry._reset()
    db, _, _ = stored
    with TestClient(create_app(Settings(db=str(db)))) as test_client:
        yield test_client  # type: ignore[misc]
    exporter_registry._reset()


def test_the_server_serves_the_plugins_format(
    client: TestClient, stored: tuple[Path, str, str]
) -> None:
    _, run_id, grade = stored

    response = client.get(f"/api/export/{run_id}/latex")

    assert response.status_code == 200, response.text
    assert response.text == f"% {run_id} grade={grade} frames=14 events=70\n"
    assert response.headers["content-disposition"] == f'attachment; filename="{run_id}.latex"'


def test_the_server_refuses_what_no_plugin_writes(
    client: TestClient, stored: tuple[Path, str, str]
) -> None:
    _, run_id, _ = stored

    missing = client.get(f"/api/export/{run_id}/nope")
    assert missing.status_code == 404
    assert "latex" in missing.json()["detail"]

    assert client.get("/api/export/ghost/latex").status_code == 404

    failed = client.get(f"/api/export/{run_id}/silent")
    assert failed.status_code == 500
    assert "returned without writing" in failed.json()["detail"]

    # A built-in format is still the built-in one.
    built_in = client.get(f"/api/export/{run_id}/md")
    assert built_in.status_code == 200
    assert "PLUGIN MARKDOWN" not in built_in.text


# ── the Python SDK ────────────────────────────────────────────────────────────


@pytest.fixture
def installed(site: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.syspath_prepend(str(site))
    exporter_registry._reset()
    yield
    exporter_registry._reset()


def test_the_sdk_writes_the_plugins_format(installed: None, tmp_path: Path) -> None:
    """`epochix.export` refused it: "choose one of html, pdf, md, json"."""
    run = parse(LOG)  # in memory: export() finds it without db=
    out = tmp_path / "report.tex"

    written = export(run, "latex", output=out)

    assert written == out.resolve()
    assert run.final_grade is not None
    assert out.read_text(encoding="utf-8") == (
        f"% {run.id} grade={run.final_grade.value} frames=14 events=70\n"
    )


def test_the_sdk_refuses_what_nothing_writes_and_writes_nothing(
    installed: None, tmp_path: Path
) -> None:
    run = parse(LOG)
    with pytest.raises(ValueError, match=r"html, pdf, md, json, gif, broken, latex, silent\."):
        export(run, "nope", output=tmp_path / "x.nope")
    assert not (tmp_path / "x.nope").exists()

    with pytest.raises(exporter_registry.ExporterFailed, match="the plugin's own bug"):
        export(run, "broken", output=tmp_path / "x.broken")
    with pytest.raises(exporter_registry.ExporterFailed, match="returned without writing"):
        export(run, "silent", output=tmp_path / "x.silent")
    assert not (tmp_path / "x.silent").exists()

    # A built-in format is still the built-in one.
    md = export(run, "md", output=tmp_path / "run.md").read_text(encoding="utf-8")
    assert "PLUGIN MARKDOWN" not in md


def test_the_sdk_writes_every_format_it_lists(tmp_path: Path) -> None:
    """Every built-in the error message offers is one export() writes.

    `gif` was listed by the CLI and refused by the SDK.
    """
    run = parse(LOG)
    for fmt in exporter_registry.BUILTIN_FORMATS:
        if fmt == "pdf":
            pytest.importorskip("fpdf")
        out = export(run, fmt, output=tmp_path / f"run.{fmt}")
        assert out.stat().st_size > 0, fmt
    assert (tmp_path / "run.gif").read_bytes()[:6] in (b"GIF87a", b"GIF89a")
