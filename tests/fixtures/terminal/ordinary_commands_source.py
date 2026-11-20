"""Commands that are not training, run as a person runs them, output kept.

The VS Code extension watches every command in a terminal and must say
nothing about a command that is not a training run. These are the commands it
is tested against: each one is run here, from this neutral folder, and its
output (stdout and stderr, as the terminal would show them) is written byte
for byte to ``<name>.log``.

    Needs:  git, node/npm, uv, and the nanoGPT clone beside this folder
            (../nanogpt/nanoGPT) for a real project's history, printed
            without author lines so it carries no e-mail address.
    Run:    python ordinary_commands_source.py

The project folder the listings show is made here, with the files a small
training project has. The `pip install` goes into a fresh virtual
environment, which the `pytest` and web-server recordings then use. Nothing
is redrawn in place: the output goes to a pipe, so pip and npm print no
progress bars.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "project"
VENV = HERE / "venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NANOGPT = HERE.parent / "nanogpt" / "nanoGPT"


def record(name: str, args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    done = subprocess.run(
        args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False
    )
    (HERE / f"{name}.log").write_bytes(done.stdout)
    print(f"{name}.log  exit {done.returncode}  {len(done.stdout)} bytes")


def make_project() -> None:
    (PROJECT / "data").mkdir(parents=True, exist_ok=True)
    (PROJECT / "README.md").write_text("# digits\n\nA small classifier.\n", encoding="utf-8")
    (PROJECT / "requirements.txt").write_text("scikit-learn\npytest\n", encoding="utf-8")
    (PROJECT / "data" / "labels.csv").write_text("id,label\n1,3\n2,7\n", encoding="utf-8")
    (PROJECT / "train.py").write_text(TRAIN, encoding="utf-8")
    (PROJECT / "test_model.py").write_text(TESTS, encoding="utf-8")
    (PROJECT / "app.py").write_text(APP, encoding="utf-8")
    (PROJECT / "package.json").write_text(
        '{\n  "name": "digits-site",\n  "version": "1.0.0",\n  "private": true\n}\n',
        encoding="utf-8",
    )


TRAIN = '''"""Fit a classifier on the digits and print its accuracy."""
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split


def fit(seed: int = 3) -> float:
    x, y = load_digits(return_X_y=True)
    xt, xv, yt, yv = train_test_split(x, y, random_state=seed)
    return LogisticRegression(max_iter=2000).fit(xt, yt).score(xv, yv)


if __name__ == "__main__":
    print(fit())
'''

# Test names a machine-learning project really has. One fails, so pytest
# prints the source, the assertion and the numbers it compared.
TESTS = """from sklearn.metrics import precision_score, recall_score

from train import fit


def test_accuracy_is_above_chance():
    assert fit() > 0.1


def test_learning_rate_schedule_decays():
    lr = [0.1 * 0.5**epoch for epoch in range(5)]
    assert lr == sorted(lr, reverse=True)


def test_precision_and_recall_agree_on_a_perfect_model():
    y = [0, 1, 1, 0]
    assert precision_score(y, y) == recall_score(y, y) == 1.0


def test_loss_target_is_met():
    val_loss = 0.42
    assert val_loss < 0.3
"""

APP = '''async def app(scope, receive, send):
    """The smallest ASGI app: every path answers 200, /missing answers 404."""
    if scope["type"] != "http":
        return
    status = 404 if scope["path"] == "/missing" else 200
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok\\n"})
'''


def serve(name: str, args: list[str], port: int) -> None:
    """Start a web server, send it a few requests, stop it, keep its log."""
    log = (HERE / f"{name}.log").open("wb")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    server = subprocess.Popen(args, cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        time.sleep(3)
        for path in ["/", "/api/status", "/train.py", "/missing", "/", "/api/status?id=7"]:
            with contextlib.suppress(OSError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).read()
            time.sleep(0.3)
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()
    print(f"{name}.log  {(HERE / f'{name}.log').stat().st_size} bytes")


def main() -> int:
    make_project()
    if not PY.exists():
        subprocess.run(["uv", "venv", "--seed", "--python", "3.12", str(VENV)], check=True)

    # `dir` is PowerShell's Get-ChildItem in VS Code's default Windows shell;
    # `ls -lan` is Git Bash's, with numeric owners so no user name is printed.
    record("dir_powershell", ["powershell", "-NoProfile", "-Command", "dir"], PROJECT)
    # Git's own bash: on Windows a bare `bash` is WSL's.
    git = shutil.which("git")
    bash = "bash"
    if os.name == "nt" and git:
        bash = next(
            str(p / "bin" / "bash.exe")
            for p in Path(git).parents
            if (p / "bin" / "bash.exe").is_file()
        )
    record("ls_la", [bash, "-c", "ls -lan"], PROJECT)
    record(
        "git_log",
        ["git", "log", "--stat", "--date=iso", "--format=commit %H%nDate:   %ad%n%n%w(0,4,4)%B"],
        NANOGPT,
    )
    record(
        "pip_install",
        [str(PY), "-m", "pip", "install", "--no-color", "scikit-learn", "pytest", "uvicorn"],
        PROJECT,
    )
    record("pytest", [str(PY), "-m", "pytest", "-v", "-p", "no:cacheprovider"], PROJECT)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    record("npm_install", [npm, "install", "--no-color", "express"], PROJECT)
    serve("uvicorn_server", [str(PY), "-m", "uvicorn", "app:app", "--port", "8765"], 8765)
    serve("http_server", [str(PY), "-m", "http.server", "8766", "--bind", "127.0.0.1"], 8766)
    return 0


if __name__ == "__main__":
    sys.exit(main())
