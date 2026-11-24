# Terminal output

What a watched terminal in VS Code prints, for the extension's notice that a
command was seen and not told (`epochix-vscode/src/terminal/CommandReading.ts`).
These are not part of the log corpus: no parser is tested on them, and
`corpus_truth.json` does not list them. The extension's tests drive each one
through the terminal watcher and assert what it says:

- the ordinary commands must say nothing;
- a training run in a layout nothing reads must say it was seen and not read.

Every log is a recording, made from a neutral folder and never edited. Record
one again with its script; `tests/unit/test_fixture_provenance.py` fails on a
log listed nowhere here.

## Recorded runs

The ordinary commands were run by `ordinary_commands_source.py` into a pipe,
as the terminal shows them minus progress bars (pip and npm print none to a
pipe). The project they list, test and serve is made by that script.

| Log | The run | Script |
|---|---|---|
| `dir_powershell.log` | `dir` in Windows PowerShell 5.1 (VS Code's default shell on Windows), in a small project folder. | `ordinary_commands_source.py` |
| `ls_la.log` | `ls -lan` in Git Bash in the same folder; numeric owners, so no user name is printed. | `ordinary_commands_source.py` |
| `git_log.log` | `git log --stat` of the whole nanoGPT history, without author lines: commit messages about losses, learning rates and iterations. | `ordinary_commands_source.py` |
| `pip_install.log` | `pip install scikit-learn pytest uvicorn` into a fresh virtual environment: versions, sizes and download rates. | `ordinary_commands_source.py` |
| `pytest.log` | `pytest -v` on four tests named after metrics, one failing on `val_loss = 0.42`. | `ordinary_commands_source.py` |
| `npm_install.log` | `npm install express`. | `ordinary_commands_source.py` |
| `uvicorn_server.log` | A uvicorn server answering six requests, then stopped. | `ordinary_commands_source.py` |
| `http_server.log` | `python -m http.server` answering the same six requests. | `ordinary_commands_source.py` |

## Format samples

None. `tests/fixtures/logs/garbage.log`, a hand-written web server log, is
driven through the watcher too, from its own folder.

The training run in a layout nothing reads is in the log corpus as well:
`tests/fixtures/logs/sb3_ppo_real.log`, Stable-Baselines3 PPO on CartPole at
`verbose=1`, a table per iteration (`|    loss | 7.28 |`). It is recorded
there, with its script, and `corpus_truth.json` pins that nothing is read
from it. A reader for that layout leaves this suite needing another.
