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
The engine is sound on what it reads; the gap is what it does not read. Two of
the audit's items shipped in 0.7.41 (2026-11-22) and are not listed: runs that
count steps (nanoGPT, the PyTorch ImageNet example, a diffusers LoRA bar), and
a notice when a watched terminal's command is seen and not told. So did
everything the first coverage run found unexecuted (item 7). 0.7.42
(2026-11-23) shipped two of the three parts left in item 3: a kohya-ss run,
and a step bar read as it is drawn over a pipe or SSH. 0.7.43, the same day,
shipped one fix that was on no list here: a run is told it is past its best
only after three readings in a row more than 1% off it (#197).

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

### 3. What is left of the step-counted runs

nanoGPT, the PyTorch ImageNet example, a diffusers LoRA bar (0.7.41) and a
kohya-ss `sd-scripts` run (0.7.42, #195) are read, from recordings. Since
0.7.42 the three that count steps (nanoGPT and both LoRA runs) are told by
step, not as epochs; the ImageNet example has epochs (#194). A bar redrawn
over the whole run is read as it is drawn when piped to `epochix -` or
tailed over SSH (#195), as it already was from a file. Not done, as
`docs/parsers.md` ("Not read yet") says:

- **MLX-LM** (`Iter 10: Train loss …, Learning Rate …` / `Iter 10: Val loss
  …, Val took …s`) has not been recorded: it needs Apple silicon. Record it on
  a Mac or leave it out.

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

### 5. A page that tells a pasted log's story

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

### 6. One engine, or a cheaper second one — a spike

Every engine change is written twice. #150 and #152 were each a Python change
and a hand port to `StandaloneEngine.ts` (1,194 lines in 0.7.41, 1,229 in
0.7.42, 1,243 in 0.7.43); the parsers, tables and thresholds are generated or
replayed from goldens, but the pipeline — sniffing, fallbacks, warm-up,
frames, milestones — is ported by hand and checked only by the corpus and the
tests someone remembers to mirror. 0.7.41 measured what that costs: the
extension's milestones had drifted into a different set altogether, and 58 of
the 60 corpus logs gave different milestones in VS Code than everywhere else.
Nothing compared them until `corpus_truth.json` recorded milestones (#175).

0.7.42's counter (#194) was ported the same way, and checked once by hand:
the extension's engine was bundled from `main` and from the branch, and every
corpus log was told through both in three languages. 150 of 180 outputs were
the same; the other 30 differed in 1,538 lines, each only in the counter's
name. That is (b) below, run once from a script that is not in the
repository and checks nothing the next time.

0.7.43's past-its-best rule (#197) shows the gap from the other side. The
rule is a count kept between readings, written twice. In Python a test
holds it over every corpus log: no reading more than 1% off its best is
told it is within 1%, and none is told it slipped before three such
readings in a row. The extension's copy is tested on three synthetic runs
of five to seven readings. `corpusParity.test.ts` compares each log's
metrics, final grade and phase, and milestones, but not the sentence any
frame tells.

The sentences are now compared: `stories.golden.json` is every corpus log
told by Python in three languages, under run ids that between them pick
every variant, and `storiesGolden.test.ts` holds the extension to it word
for word. Measured first, the engines told 4,194 of 4,206 frames
differently. Most of that was the variant each picked from a run id, but
under one pick they still differed in an exact half's rounding, a first
reading's change, the learning-rate warning (never raised in VS Code) and
the order of two warnings. That is the sentences, not the pipeline: the
sniffing, fallbacks and warm-up are still ported by hand, and a log the
corpus lacks is still unchecked.

A spike, with a written answer rather than a merge: (a) can the Python engine
run inside the extension through Pyodide — bundle size, start-up time on a
cold panel, whether `pydantic-core` loads, whether it works in a web
extension host; (b) failing that, can the pipeline's decisions be recorded as
a golden the way parser calls are (`parsers.golden.json`): every prefix of
every corpus log, the parser chosen and the frames told, replayed by the
extension. (b) would have caught both bugs above in the port without a
hand-written mirror test. Measure before deciding; the extension working with
no Python installed is a feature and stays.

### 7. Code no test executes

**Measured.** Coverage ran for the first time on 2026-11-10 (CI job
`coverage`: `tests/unit` and `tests/integration` on ubuntu and Python 3.12,
plus what both `integrations` rows execute with the real frameworks): 85.93%,
5,980 of 6,959 statements, and no file at 0%. The job's summary names every
file at 0%, every module under 50% and every function never entered; the
floor (`fail_under = 85.5` in `pyproject.toml`) only catches a drop. The
per-module figures below are from that run.

Everything the list showed now has a test that runs it the way a person
would, shipped in 0.7.41: the plugin groups (#169), `export(parse(log))`
(#160), the Jupyter magics (#172), the five commands (#171, and #169 for
`export`), the two tests that skipped in every job (#170, now run against
the wheel) and `GET /api/raw` (#177). Running them found most of 0.7.41's
fixes.

Not findings: the Lightning and Hugging Face callbacks, the TensorBoard and
W&B importers and the torch hooks in `sdk/activations.py` read 0% to 45%
without the frameworks installed and are run by the `integrations` jobs,
whose data the `coverage` job adds. The LLM fallback's three request
functions need a running Ollama, which CI does not have. Reading standard
input (`python train.py | epochix`) had never run either; it is small, so it
now has a test (`test_stdin_pipe.py`).

Left to do the same way: the frontend and the extension, neither measured in
CI.

- **The frontend.** Vitest has a coverage script that CI does not run, and
  `vitest.config.js` measures only `store.js` and `ws-client.js`. Measured by
  hand over all of `src/` while fixing the metric direction (#179): 40.9% of
  lines before, 51.9% after.
- **The extension** (Mocha inside the VS Code host). Every command now runs
  in a test (#180; six of the eight never had, and Export Run did nothing),
  but no coverage figure exists.

What each takes is written in the pull request that added the `coverage`
job.

### 8. The parser docs leave out four libraries

**Measured.** `docs/parsers.md` ("Supported Frameworks") has no section for
XGBoost, LightGBM, CatBoost or scikit-learn's `GridSearchCV`; none of the four
names appears anywhere under `docs/`. All four are read, and
`tests/fixtures/logs/` holds real recordings of each. Add the sections with
example lines copied from those recordings, not typed, and a test that fails
when a parser in the registry has no section, so the next one cannot be left
out the same way.

### 9. The PDF report has no milestones

**Measured.** Since 0.7.41 a run's milestones are stored and read back, and
the HTML and Markdown reports list them with their epochs. The PDF lists
none: `pdf_export.py` and `_pdf_render.py` never read them, and its
docstrings, which promised a section, were corrected instead (#174). A
section needs a layout of its own and the Farsi shaping the rest of the PDF
already does, in all three languages, and a test that every stored milestone
appears in the PDF of a corpus run.

---

## Decided — not doing

- **A Claude artifact.** One shipped until 0.7.21 and was withdrawn: a third,
  hand-written engine (last touched in 0.3.0) that graded regression on
  perplexity bands and animated random "activations". A new one is worth
  building only if it is generated from the Python engine's tables and
  replays `grading.golden.json` like the extension's engine — otherwise it is
  a fourth copy to drift.
- **Metaphor packs and task plugins.** Both plugin groups were documented and
  loaded by nothing until 0.7.41 removed them (#169). A pack's cards are free
  text placed beside the grade, which epochix's own sentences may not be
  ([AGENTS.md](AGENTS.md), "A story sentence may say only what the numbers
  support"). A task plugin would regrade runs in the Python engine only; the
  extension grades from tables generated from Python and cannot load one. A
  project sets a task's thresholds in `.epochix.yaml`, which both engines
  read. Exporter plugins stay, and are wired in.
- **Grade and phase changes as milestones.** The extension raised them, and
  Python never did; 0.7.41 removed them (#175) rather than add them to
  Python, its store and its reports. The learning curve, the phase ribbon and
  the grade card show every change in both engines. The extension's version
  also fired once per letter, so a run that fell from B to C and recovered
  read as ending on C. If they come back, they start in Python, firing on
  every change, and reach the extension through the corpus parity test.
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
