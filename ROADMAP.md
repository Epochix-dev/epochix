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

- **F1 is graded on improvement; decide whether it should share accuracy's
  bands.** ROC AUC got bands of its own in 0.7.27 because its chance level is
  0.5 in every dataset. F1's is not a constant — it follows the positive
  class's share — so it was left on the improvement rule: a run going 0.40 →
  0.84 grades A+, one going 0.90 → 0.91 grades C−. Accuracy has the same
  blind spot (a 95% majority class makes 95% accuracy worthless) and is graded
  on fixed bands with a caveat on the card. Either treat F1 like accuracy
  (add `val_f1`/`f1` to `_ON_SCALE_KEYS[CLASSIFICATION]`) or keep it as it is;
  it is a judgement, and should be written down as one. Since 0.7.28 a project
  can set F1 bands for itself with a `val_f1` entry in `.epochix.yaml`; this
  item is about the default.
- **The VS Code panel does not read `.epochix.yaml`.** The command line, the
  server and the SDK grade with a project's thresholds; the extension's own
  engine (TypeScript) uses the built-in ones, and its Python server is started
  from a temporary folder, so it would not find a workspace file either. A
  workspace with custom thresholds therefore shows one grade in the panel and
  another from `epochix run`. The README and `docs/config.md` say so. Closing
  it means reading the workspace's file in the extension (a YAML reader in the
  bundle) and replaying the Python loader's answers, like the other tables.
- **Say which way this run was graded.** The sentence under the grade names
  both ways a grade is reached (fixed thresholds, or improvement since the
  first reading) because a frame does not record which applied. Carry it on
  the frame — a `grade_basis` beside `grade_note`: model, store column and
  migration, the TypeScript engine and its goldens, the exports — and show
  only the sentence that is true of the run.

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
