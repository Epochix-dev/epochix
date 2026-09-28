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

Known gaps, each deliberate and none a bug.

- **Run comparison as a PDF.** `epochix compare`, `/api/export/compare/md` and
  the comparison view's download produce Markdown; the race GIF carries the
  curves. There is no PDF version of the comparison.
- **PDFs draw Latin and Arabic script only.** A Farsi report embeds Vazirmatn
  and shapes its text with uharfbuzz (the `pdf` extra); without the shaper it
  falls back to English chrome and says `pip install "epochix[pdf]"`. Any
  other script — CJK in a run name, say — cannot be drawn by either font, and
  a name made only of such characters is replaced by the run id rather than a
  row of question marks. `test_pdf_export.py` pins exactly where that line
  falls. Fixing it means embedding a font per script, or one very large one.
- **Grading, direction and phase logic are hand-ported to TypeScript.** The
  name tables, narrative templates and messages are generated from the Python
  engine (`make gen-ts-tables`); the logic is ported by hand and held to the
  Python engine by `corpus_truth.json` and each side's tests. Generating it
  too would remove the last place the two engines can drift unseen.

---

## Decided — not doing

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
