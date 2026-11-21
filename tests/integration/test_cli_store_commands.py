"""`open`, `race`, `prune` and `config`, run as a user runs them.

The first coverage measurement (ROADMAP's "Code no test executes") found
these four commands never executed by any test. Driven here through the
console entry point in a subprocess, against a real store, they turned up:

- a `.env` in the folder epochix runs from — usually the user's project, with
  their own keys in it (``OPENAI_API_KEY``) — made every command die with a
  pydantic ValidationError, because unknown .env entries were forbidden;
- `config set` wrote any key and any value: ``config set nonsense 1`` or
  ``config set port abc`` then broke every command in that folder, with a
  page of traceback, `config show` included;
- `config show` printed ``auth_token`` and ``llm_key`` in clear;
- `open` opened the browser before finding its port taken, so the page shown
  was whatever already listened there;
- `race -o slides/race.gif` died with a traceback for want of the folder;
- `prune` read only the newest 10,000 runs, leaving out the oldest.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from epochix import parse
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"


def _env(db: Path, **extra: str) -> dict[str, str]:
    # The developer's own EPOCHIX_* settings must not reach the command; the
    # rest (PATH, coverage's variables) must.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("EPOCHIX_")}
    env.update(
        PYTHONPATH=str(ROOT / "src"),
        PYTHONIOENCODING="utf-8",
        EPOCHIX_DB=str(db),
        EPOCHIX_OPEN_BROWSER="false",
        EPOCHIX_GRADE_CONFIG="off",
        **extra,
    )
    return env


def _cli(cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "epochix.cli", *args],
        cwd=cwd,
        env=_env(cwd / "runs.db", **env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _store(tmp_path: Path) -> RunStore:
    return RunStore(db_path=str(tmp_path / "runs.db"))


def _parsed(tmp_path: Path, log: str, name: str) -> str:
    return parse(DEMO / log, db=str(tmp_path / "runs.db"), run_name=name).id


def _aged(tmp_path: Path, source_id: str, run_id: str, days: int) -> None:
    """A copy of a parsed run that started *days* ago."""
    store = _store(tmp_path)
    run = store.get_run(source_id)
    assert run is not None
    started = datetime.now(timezone.utc) - timedelta(days=days)
    store.create_run(run.model_copy(update={"id": run_id, "started_at": started}))


def _no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    out = result.stdout + result.stderr
    assert "Traceback" not in out and "ValidationError" not in out, out


# ── open ─────────────────────────────────────────────────────────────────────


def test_open_serves_the_run_it_names(tmp_path: Path) -> None:
    run_id = _parsed(tmp_path, "keras_image_classifier.log", "opened")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "epochix.cli", "open", run_id, "--port", str(port)],
        cwd=tmp_path,
        env=_env(tmp_path / "runs.db"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        body = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                url = f"http://127.0.0.1:{port}/api/snapshot/{run_id}"
                with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                    body = resp.read().decode("utf-8")
                break
            except OSError:
                time.sleep(0.25)
        assert body is not None, f"no server on {port}; exit {proc.poll()}"
        assert '"opened"' in body
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=30)
    # The browser is off, so the address is printed for the user to open.
    assert f"http://127.0.0.1:{port}/v/{run_id}" in out


def test_open_a_run_that_is_not_there(tmp_path: Path) -> None:
    _parsed(tmp_path, "keras_image_classifier.log", "a")
    result = _cli(tmp_path, "open", "no-such-run", "--port", str(_free_port()))
    assert result.returncode == 1
    assert "Run not found: no-such-run" in result.stderr


def test_open_stops_before_the_browser_when_the_port_is_taken(tmp_path: Path) -> None:
    run_id = _parsed(tmp_path, "keras_image_classifier.log", "a")
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        result = _cli(tmp_path, "open", run_id, "--port", str(port))
    assert result.returncode == 1
    assert f"Port {port} on 127.0.0.1 is already in use" in result.stderr
    out = result.stdout + result.stderr
    assert "/v/" not in out and "Opening run" not in out, out
    _no_traceback(result)


# ── race ─────────────────────────────────────────────────────────────────────


def test_race_writes_an_animated_gif_into_a_new_folder(tmp_path: Path) -> None:
    from PIL import Image

    a = _parsed(tmp_path, "keras_image_classifier.log", "a")
    b = _parsed(tmp_path, "pytorch_lightning.log", "b")
    result = _cli(tmp_path, "race", a, b, "-o", "slides/race.gif")
    assert result.returncode == 0, result.stdout + result.stderr
    gif = tmp_path / "slides" / "race.gif"
    assert gif.read_bytes()[:6] == b"GIF89a"
    with Image.open(gif) as img:
        assert img.n_frames > 1
    assert "Race GIF -> " in result.stdout


def test_race_needs_two_runs(tmp_path: Path) -> None:
    a = _parsed(tmp_path, "keras_image_classifier.log", "a")
    result = _cli(tmp_path, "race", a)
    assert result.returncode == 1
    assert "at least two runs" in result.stderr
    assert not (tmp_path / "race.gif").exists()


def test_race_names_a_run_that_is_not_there(tmp_path: Path) -> None:
    a = _parsed(tmp_path, "keras_image_classifier.log", "a")
    result = _cli(tmp_path, "race", a, "no-such-run")
    assert result.returncode == 1
    assert "Run not found: no-such-run" in result.stderr


def test_race_says_why_it_cannot_write(tmp_path: Path) -> None:
    a = _parsed(tmp_path, "keras_image_classifier.log", "a")
    b = _parsed(tmp_path, "pytorch_lightning.log", "b")
    (tmp_path / "taken").write_text("a file, not a folder", encoding="utf-8")
    result = _cli(tmp_path, "race", a, b, "-o", "taken/race.gif")
    assert result.returncode == 1
    assert "Cannot write" in result.stderr
    _no_traceback(result)


# ── prune ────────────────────────────────────────────────────────────────────


def _three_ages(tmp_path: Path) -> str:
    fresh = _parsed(tmp_path, "keras_image_classifier.log", "fresh")
    _aged(tmp_path, fresh, "ten-days", 10)
    _aged(tmp_path, fresh, "forty-days", 40)
    return fresh


def _ids(tmp_path: Path) -> set[str]:
    return {r.id for r in _store(tmp_path).list_runs(limit=None)}


def test_a_dry_run_lists_and_deletes_nothing(tmp_path: Path) -> None:
    fresh = _three_ages(tmp_path)
    result = _cli(tmp_path, "prune", "--older-than", "30d", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "[dry-run] Deleting forty-days" in result.stdout
    assert "ten-days" not in result.stdout and fresh not in result.stdout
    assert _ids(tmp_path) == {fresh, "ten-days", "forty-days"}


def test_prune_deletes_by_age_and_only_by_age(tmp_path: Path) -> None:
    fresh = _three_ages(tmp_path)
    frames_before = len(_store(tmp_path).get_story_frames(fresh))
    assert frames_before > 0

    result = _cli(tmp_path, "prune", "--older-than", "30d")
    assert result.returncode == 0, result.stderr
    assert "Pruned 1 run(s)." in result.stdout
    assert _ids(tmp_path) == {fresh, "ten-days"}

    result = _cli(tmp_path, "prune", "--older-than", "5d")
    assert "Pruned 1 run(s)." in result.stdout
    assert _ids(tmp_path) == {fresh}
    # The run kept keeps what it had.
    assert len(_store(tmp_path).get_story_frames(fresh)) == frames_before

    result = _cli(tmp_path, "prune", "--older-than", "5d")
    assert result.returncode == 0
    assert "Nothing to prune." in result.stdout


def test_prune_refuses_an_age_it_cannot_read(tmp_path: Path) -> None:
    fresh = _three_ages(tmp_path)
    result = _cli(tmp_path, "prune", "--older-than", "30")
    assert result.returncode == 1
    assert "--older-than must be like '30d'" in result.stderr
    assert _ids(tmp_path) == {fresh, "ten-days", "forty-days"}


def test_list_runs_without_a_limit_returns_every_run(tmp_path: Path) -> None:
    """What prune reads: a cap would drop the oldest, the ones it deletes."""
    fresh = _three_ages(tmp_path)
    store = _store(tmp_path)
    assert [r.id for r in store.list_runs(limit=None)] == [fresh, "ten-days", "forty-days"]
    assert [r.id for r in store.list_runs(limit=1)] == [fresh]


# ── config ───────────────────────────────────────────────────────────────────


def _settings_shown(tmp_path: Path, **env: str) -> dict[str, str]:
    result = _cli(tmp_path, "config", "show", **env)
    assert result.returncode == 0, result.stdout + result.stderr
    pairs = (line.strip().split(" = ", 1) for line in result.stdout.splitlines() if " = " in line)
    return dict(pairs)  # type: ignore[arg-type]


def test_show_hides_the_secrets_and_only_them(tmp_path: Path) -> None:
    shown = _settings_shown(tmp_path, EPOCHIX_AUTH_TOKEN="tok-123", EPOCHIX_LLM_KEY="sk-456")
    assert shown["auth_token"] == "(set, hidden)"
    assert shown["llm_key"] == "(set, hidden)"
    assert shown["port"] == "7860"
    assert shown["open_browser"] == "False"

    unset = _settings_shown(tmp_path)
    assert unset["auth_token"] == "''"


def test_show_never_prints_a_secret(tmp_path: Path) -> None:
    result = _cli(
        tmp_path, "config", "show", EPOCHIX_AUTH_TOKEN="tok-123", EPOCHIX_LLM_KEY="sk-456"
    )
    assert "tok-123" not in result.stdout and "sk-456" not in result.stdout


def test_set_writes_what_show_then_reads(tmp_path: Path) -> None:
    assert _cli(tmp_path, "config", "set", "port", "9000").returncode == 0
    result = _cli(tmp_path, "config", "set", "EPOCHIX_PORT", "9001")
    assert result.returncode == 0
    assert "Set EPOCHIX_PORT=9001" in result.stdout
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "EPOCHIX_PORT=9001\n"
    assert _settings_shown(tmp_path)["port"] == "9001"


def test_set_replaces_the_line_however_it_was_written(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=sk-mine\nexport epochix_port = 8000\nEPOCHIX_PORT=8001\n",
        encoding="utf-8",
    )
    assert _cli(tmp_path, "config", "set", "port", "9000").returncode == 0
    assert env.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-mine\nEPOCHIX_PORT=9000\n"
    assert _settings_shown(tmp_path)["port"] == "9000"


@pytest.mark.parametrize(
    ("key", "value", "says"),
    [
        ("nonsense", "1", "Unknown setting 'nonsense'"),
        ("EPOCHIX_PROT", "9000", "Unknown setting 'EPOCHIX_PROT'"),
        ("port", "abc", "EPOCHIX_PORT"),
        ("open_browser", "maybe", "EPOCHIX_OPEN_BROWSER"),
        ("llm_provider", "skynet", "EPOCHIX_LLM_PROVIDER"),
        ("redis_url", "redis://x", "no hosted backend"),
        ("port", "9000\nEPOCHIX_DB=/elsewhere", "one line"),
    ],
)
def test_set_refuses_what_would_break_the_folder(
    tmp_path: Path, key: str, value: str, says: str
) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-mine\n", encoding="utf-8")
    result = _cli(tmp_path, "config", "set", key, value)
    assert result.returncode == 1
    assert says in result.stderr, result.stderr
    _no_traceback(result)
    assert env.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-mine\n"
    # And the folder still works.
    assert _cli(tmp_path, "list").returncode == 0


def test_set_hides_a_secret_it_writes(tmp_path: Path) -> None:
    result = _cli(tmp_path, "config", "set", "auth_token", "tok-123")
    assert result.returncode == 0
    assert "tok-123" not in result.stdout
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "EPOCHIX_AUTH_TOKEN=tok-123\n"


def test_a_projects_own_env_file_does_not_stop_epochix(tmp_path: Path) -> None:
    """The .env beside a training script holds that project's keys."""
    run_id = _parsed(tmp_path, "keras_image_classifier.log", "mine")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-mine\nDATABASE_URL=postgres://u:p@db/x\nEPOCHIX_TYPO=1\n",
        encoding="utf-8",
    )
    result = _cli(tmp_path, "list")
    assert result.returncode == 0, result.stdout + result.stderr
    assert run_id in result.stdout

    run = _cli(tmp_path, str(DEMO / "pytorch_lightning.log"), "--port", str(_free_port()))
    assert run.returncode == 0, run.stdout + run.stderr
    assert len(_ids(tmp_path)) == 2


def test_a_bad_value_in_env_is_one_line_and_set_mends_it(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("EPOCHIX_PORT=abc\n", encoding="utf-8")
    broken = _cli(tmp_path, "list")
    assert broken.returncode == 1
    assert "EPOCHIX_PORT" in broken.stderr
    assert "./.env" in broken.stderr
    _no_traceback(broken)

    assert _cli(tmp_path, "config", "set", "port", "9000").returncode == 0
    assert _cli(tmp_path, "list").returncode == 0
