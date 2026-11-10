# Roadmap

Open work, roughly in the order it is worth doing. Each item says what is
actually wrong and how it was measured, so nobody has to rediscover it.

Closed items live in [CHANGELOG.md](CHANGELOG.md). Rules that closed items
taught live in [AGENTS.md](AGENTS.md).

---

## Blocked — not on us

- **Verify activation capture on Apple MPS / AMD ROCm.** There is no
  vendor-specific code and no device gating; capture uses PyTorch and Keras
  forward hooks, and it has been proven to work with every accelerator hidden.
  So it *should* work — but it has only been run on CUDA and CPU, and untested
  is not the same as supported. `epochix doctor` prints the result on whatever
  device it finds and asks for that line on an unverified backend. Needs
  hardware we do not have.
- **VS Code Marketplace verified publisher.** Eligibility opens around
  January 2027.

---

## Open

From an audit on 2026-11-10 (0.7.40 plus the idle-sniff fix that followed it).
The engine is sound on what it reads; the gap is what it does not read, and
that it says nothing when it reads nothing.

Two kinds of evidence appear below, and they are not the same:

- **Measured** — `epochix check` run on a real file.
- **Probe** — `epochix check` run on a few lines *typed from memory* of a
  library's layout. A probe says where to look. It is not a fixture and must
  not become one: each of those items starts by recording a real run from a
  neutral folder ([AGENTS.md](AGENTS.md), "A demo or a 'real' fixture is a
  recording"), and the recording decides everything, the probe nothing.

Every item ends in a fixture listed in `tests/fixtures/logs/README.md` with
its script, an entry in `corpus_truth.json`, both engines changed
(`make gen-ts-tables`), and one test that runs the real file through the
pipeline.

### 1. Read the metrics files libraries write

**Measured.** A real Ultralytics `results.csv` (a header row, then one row per
epoch for 20 epochs: `epoch,time,train/box_loss,…,metrics/mAP50(B),…`) gives
parser `universal`, task `custom`, "No metrics were recognised at all". The
console log of the same kind of run is told as detection on mAP50.

A metrics file is the easiest input there is: the column names are exact, the
epoch is a column, nothing is redrawn. Start with a header-driven reader — a
first row naming `epoch` or `step`, every later row mapped through the
normaliser — and prove it on Ultralytics' file. Then record and add, one at a
time: PyTorch Lightning's `CSVLogger` (`metrics.csv`; expect rows that leave
some columns empty),
Keras's `CSVLogger`, and the Hugging Face `Trainer`'s `trainer_state.json`
(`log_history`, JSON rather than CSV). An empty cell is no reading, not a
zero. The story told from the file should equal the story told from that
run's console output; record both from one run and assert it.

### 2. timm and MMEngine

**Probe.** Lines in timm's layout (`Train: 0 [1250/1251 (100%)]  Loss: …
LR: …` and `Test: [48/48]  … Acc@1: …  Acc@5: …`): no epochs seen, `Acc@1`
not read, and the epoch counter after `Train:` listed as a metric named
`Train`. Lines in MMEngine's layout (`… - mmengine - INFO - Epoch(train)
[1][391/391]  lr: …  eta: 1:23:45  …  loss: …`, then `Epoch(val) [1][79/79]
accuracy/top1: …`): accuracy read, but no epochs seen, and `eta` and `memory`
listed as metrics. Detectron2's layout (`eta: …  iter: 19  total_loss: …
max_mem: 3000M`) fared the same: no iteration read, `eta` a metric.

Record timm's `train.py` and one MMEngine trainer (mmpretrain is the
smallest) on CPU. Then: the epoch from the line, `Acc@1` told as accuracy, and
`eta`, `memory`, `max_mem` and a counter never told as metrics
(`parsers/_never_metrics.py`; `VALUE_DECIDES` for a name that is a setting in
one log and a metric in another). Whether each gets its own parser or a rule
in the universal one is for the recording to decide. Detectron2 is hard to
install on Windows; record it on Linux or leave it out and say so.

### 3. Step-counted loops and fine-tuning scripts

**Probe.** Nothing at all was read from: MLX-LM (`Iter 10: Train loss …,
Learning Rate …` / `Iter 10: Val loss …, Val took …s`), a kohya or diffusers
LoRA run (one tqdm bar for the whole run, `steps: 10%|…| 100/1000 [… ,
avr_loss=…]`), and the PyTorch ImageNet example (`Epoch: [0][5000/5005]
Time … Loss … (…)  Acc@1 … (…)`, then ` * Acc@1 … Acc@5 …`). From a nanoGPT-style loop (`step 250: train loss …, val loss …`) the training loss was read and the validation loss on the same
line was not. scikit-learn's `MLPClassifier(verbose=True)` was read correctly
and needs nothing.

These runs count steps, not epochs, and most never print an accuracy: the
story is a loss told by step. Record nanoGPT (its character-level Shakespeare
config can be trained on CPU), then MLX-LM (needs Apple silicon — record on
a Mac or leave it out), then a LoRA trainer. "name value" pairs with a space
(`train loss …`) are the common thread; a rule for them has to stay
bounded and must not start reading prose.

### 4. Reinforcement learning

**Probe.** Nothing was read from a Stable-Baselines3 table
(`|    ep_rew_mean          | …           |` between rules of dashes, one
block per iteration, `total_timesteps` as the counter).

This is more than a parser. There is no reinforcement-learning task: the
story's metric is mean episode reward, which has no fixed scale, so it can
only be graded on improvement, and the phase sentences written for accuracy
do not apply. Needs a `TaskType`, its direction pinned, templates in three
languages that claim only what the numbers support, and a recording (PPO on
CartPole runs on CPU). Do it last: it touches every layer.

### 5. Say so when a terminal's output is not recognised

**Measured, in part.** Both issues ever opened by people outside the project
(#35, #101) were sent from the dashboard's report button with no run loaded:
0 epochs, no metric. What they ran is not known. What is known is the code
path: `TerminalFeed` withholds a terminal's output until it recognises
training, and the panel opens only then. A command whose output is never
recognised — every layout in items 1 to 4 — produces nothing: no panel, no
message. The empty panel explains what Epochix reads (0.7.32), but nothing
tells the person that their run was seen and not understood.

When a command in a watched terminal ends, or goes quiet, having printed
numbers that were not recognised, say it once: what was seen (lines, the
`name=value` pairs if any), why no story could be told, and what would fix it
— the diagnosis `epochix check` already prints, which the extension has no
equivalent of. It must not fire on `ls` or `pip install`: decide what "looked
like training" means from recordings of commands that are not training, and
test that those stay silent. Nothing of the output leaves the machine.

### 6. A page that tells a pasted log's story

The extension's engine (`StandaloneEngine.ts`, `parsers/`, `story/`) imports
nothing from `vscode`; it is plain TypeScript that turns text into frames. A
static page on the docs site (epochix.dev, deployed to GitHub Pages by
`docs.yml`)
could take a pasted log and show its grade and story in the browser, with no
install and no upload. Today the only ways to try Epochix are `pip install`
and the VS Code extension.

The page must be built from the same sources, not a copy — the Claude
artifact under "Decided — not doing" was a third engine and drifted. It needs
a test that the page's bundle tells the corpus the same as
`corpus_truth.json`, and it must state on the page that the log does not
leave the browser, and make that true (no network calls; assert it). Start
with grade, phase, story sentence and the learning curve; the full dashboard
is a separate question.

### 7. One engine, or a cheaper second one — a spike

Every engine change is written twice. The last two fixes (#150, #152) were
each a Python change and a hand port to `StandaloneEngine.ts` (1,087 lines);
the parsers, tables and thresholds are generated or replayed from goldens,
but the pipeline — sniffing, fallbacks, warm-up, frames — is ported by hand
and checked only by the corpus and the tests someone remembers to mirror.

A spike, with a written answer rather than a merge: (a) can the Python engine
run inside the extension through Pyodide — bundle size, start-up time on a
cold panel, whether `pydantic-core` loads, whether it works in a web
extension host; (b) failing that, can the pipeline's decisions be recorded as
a golden the way parser calls are (`parsers.golden.json`): every prefix of
every corpus log, the parser chosen and the frames told, replayed by the
extension. (b) would have caught both bugs above in the port without a
hand-written mirror test. Measure before deciding; the extension working with
no Python installed is a feature and stays.

### 8. Code no test executes

**Measured.** Coverage ran for the first time on 2026-11-10 (CI job
`coverage`: `tests/unit` and `tests/integration` on ubuntu and Python 3.12,
plus what both `integrations` rows execute with the real frameworks): 85.93%,
5,980 of 6,959 statements, and no file at 0%. The job's summary names every
file at 0%, every module under 50% and every function never entered; the
floor (`fail_under = 85.5` in `pyproject.toml`) only catches a drop. The
per-module figures below are from that run.

What the list showed, worst first. Each is something that ships, and each
ends in a test that runs it the way a person would, not in a number.

- **Three of the four plugin groups are loaded by nothing.**
  `docs/plugins.md` documents the entry points `epochix.metaphor_packs`,
  `epochix.exporters` and `epochix.tasks`, and says a registered exporter is
  used with `epochix export <run-id> --format latex`. `load_all_plugins()`
  has no caller: it and the three `_load_*_plugins` functions executed zero
  statements. Nothing outside `src/epochix/plugins/` imports the three
  registries, and the CLI's export knows html, pdf, md, json and gif.
  `test_plugins.py` registers by hand and reads back, which is the
  `.epochix.yaml` loader over again ([AGENTS.md](AGENTS.md), "Grading reads
  the project's `.epochix.yaml`"). Parser plugins are a separate path
  (`parsers/registry.py`) and do work. Either wire the three in, each proved
  by a test that installs a real plugin package and sees it used, or take
  them out of the docs and the package.
- **`export(parse("train.log"))` fails.** `sdk/export.py` 19.2%,
  `sdk/compare.py` 19.8%, `sdk/visualize.py` 13.9%: `export`, `compare`,
  `visualize` and `serve` are documented in `docs/api.md` and no test calls
  any of them. Run by hand on 2026-11-10: `parse()` stores into `:memory:`
  unless given `db=`, and the others read the configured database, so
  `export(run)` raises `ValueError: Run not found` in all four formats, and
  `compare(a, b)` returns its verdict with an empty `narrative` because the
  failed lookup is swallowed. With the same `db=` passed to both, json, md
  and pdf export and the narrative is written. `visualize(run)` reads the
  same database, so by the code it opens a page for a run its server does
  not have; that was not run. The Jupyter magic had this bug and it was
  fixed there (`test_jupyter_magic.py`). Decide what `parse()` does by
  default, then test the journey as documented. `parse_string` has no test
  either.
- **The Jupyter magics are not run by their own test.**
  `integrations/jupyter.py` 19.6%. `test_jupyter_magic.py` loads the
  extension in a real IPython shell and then tests the helpers the magics
  call; `_line_magic`, `_cell_magic` and `_ensure_server` never execute. Run
  `%epochix train.log` and `%%epochix --live` through the shell.
- **`/sse/live/{run_id}` is never requested.** `server/sse.py` 38.3%: the
  whole route. The dashboard falls back to it when a WebSocket cannot be
  opened (`frontend/src/sse-client.js`), and the README documents its token.
  Test the replay from `last_seq`, that `complete` ends the stream, and that
  a wrong token is refused.
- **Five commands no test runs:** `epochix open`, `export`, `race`, `prune`
  and `config` (85 statements of `cli.py`, which is 62% overall). `open` and
  `export` are tested only for refusing a missing argument.
- **Two tests skip in every CI job.** Not a coverage figure, but found by
  reading one: `exporters/html_export.py` is 50.0% because both tests that
  take `build_html` past its bundle check skip with "frontend bundle not
  built". Only the `browser` job builds the bundle and it runs only
  `tests/browser`, so the HTML export's inlining, and the test that run data
  cannot break out of its `<script>` block, run nowhere.
  `test_the_watermark_carries_the_brand_mark` skips in a source checkout,
  which is every job. Run them where the bundle and the wheel exist, and
  fail on a skip there.
- **`GET /api/raw/{run_id}` has no caller** in the dashboard, the extension
  or the docs, and no test. Document and test it, or remove it.

Not findings: the Lightning and Hugging Face callbacks, the TensorBoard and
W&B importers and the torch hooks in `sdk/activations.py` read 0% to 45%
without the frameworks installed and are run by the `integrations` jobs,
whose data the `coverage` job adds. The LLM fallback's three request
functions need a running Ollama, which CI does not have. Reading standard
input (`python train.py | epochix`) had never run either; it is small, so it
now has a test (`test_stdin_pipe.py`).

Left to do the same way: the frontend (Vitest has a coverage script that CI
does not run, limited to two files) and the extension (Mocha inside the VS
Code host). What each takes is written in the pull request that added the
`coverage` job.

### 9. The parser docs leave out four libraries

**Measured.** `docs/parsers.md` ("Supported Frameworks") has no section for
XGBoost, LightGBM, CatBoost or scikit-learn's `GridSearchCV`; none of the four
names appears anywhere under `docs/`. All four are read, and
`tests/fixtures/logs/` holds real recordings of each. Add the sections with
example lines copied from those recordings, not typed, and a test that fails
when a parser in the registry has no section, so the next one cannot be left
out the same way.

---

## Decided — not doing

- **A Claude artifact.** One shipped until 0.7.21 and was withdrawn: a third,
  hand-written engine (last touched in 0.3.0) that graded regression on
  perplexity bands and animated random "activations". A new one is worth
  building only if it is generated from the Python engine's tables and
  replays `grading.golden.json` like the extension's engine — otherwise it is
  a fourth copy to drift.
- **PDFs for scripts beyond Latin and Arabic.** A Farsi report embeds
  Vazirmatn and shapes its text with uharfbuzz (the `pdf` extra); without the
  shaper it falls back to English chrome and says `pip install
  "epochix[pdf]"`. Any other script — CJK in a run name, say — cannot be drawn
  by either font, and a name made only of such characters is replaced by the
  run id rather than a row of question marks. `test_pdf_export.py` pins
  exactly where that line falls. Drawing it would mean bundling a font per
  script, or one very large one (a full CJK font is 15 MB or more, against
  Vazirmatn's ~245 KB); decided on 2026-09-28 not to grow the package for it.
  The HTML and Markdown exports carry every script already.

- **Universal (fallback) parser at 50k lines/sec.** It runs at ~31k on CI. The
  gate never ran until 0.7.13; it then measured 16.7k. Two output-identical
  passes (single-scan blanking in 0.7.13; line-profiled overhead in 0.7.15 —
  `try/except` for `contextlib.suppress`, cached name lookups, a fail-fast
  regex) took it to 31k. The largest remaining cost is Pydantic validation of
  `RawMetric`, which is part of the public plugin API (`docs/plugins.md`);
  swapping it for a faster type would silently drop validation for
  third-party parsers. Not worth it: 31k lines/sec reads a million-line log in
  about half a minute, and a live run prints a few lines per second. The
  gate's floor for this parser is 24k, to catch regressions; the framework
  parsers keep 50k (64k-129k on CI).

## Checked — not a problem

Claims that were filed as bugs, measured, and found wrong. Kept so they are
not filed again.

- *"The dashboard layout is locked to one screen."* It is not. `#app` is a
  fixed-height shell and `.app-body` scrolls inside it (`overflow-y: auto`) —
  measured live at **3510px of content in a 720px region**, about five
  screens. The claim came from reading `document.scrollHeight ===
  innerHeight`, which is simply how an app shell behaves, in a browser pane
  that was reporting a viewport of 0x0 at the time.
- *"Milestone surfaces are unreachable."* Milestones are rendered by
  `TimelineStory`, mounted through `JourneyPanel`. The run probed had zero
  milestones, so the DOM was empty for a legitimate reason.
