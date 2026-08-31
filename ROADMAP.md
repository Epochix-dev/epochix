# Roadmap

Open work, roughly in the order it is worth doing. Each item says what is
actually wrong and how it was measured, so nobody has to rediscover it.

Closed items live in [CHANGELOG.md](CHANGELOG.md).

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

## PDF export — keep going

The charts landed (loss / quality / error curves, drawn with fpdf2 primitives,
no new dependency). The rest of the report is still thin: a 20-epoch run
exported five pages of four text lines each before this work, and most of that
emptiness is still there on the non-chart pages.

- **A cover that justifies its own grade.** It currently shows a letter, the
  run id, task, date and one sentence. It should carry best epoch vs final
  epoch, epochs seen, duration, the metric the grade was computed from, and the
  dataset-blind caveat — the grade is the headline claim and nothing on the
  page supports it.
- **Do not title a report with a ULID.** With no run name the cover reads
  `01M1CY50EAPJFA7S5DVNJH77XD`. Fall back to the log's filename.
- **One page per phase discards most of the run.** An 11-frame run renders 3
  pages. Either a compact per-epoch table or milestone-driven page selection.
- **Final metrics is a bare list.** No best-vs-final, no direction, no units —
  four rows of numbers with nothing to compare them against.
- **Skill dimensions and metaphor cards never reach the PDF** although the
  engine computes them for every frame and the dashboard shows them.

## Dashboard

- **The layout is locked to one screen.** Measured live:
  `document.scrollHeight === window.innerHeight` (720 = 720). Fifteen
  visualisation modules compete for a single viewport, which is why charts are
  190px tall and the whole thing reads as thinner than it is. Letting the page
  scroll would give the existing panels room without building anything new.
- **Three modules appear unreachable** — `ImprovementWaterfall`,
  `ParticleField`, and the milestone/warning surfaces returned no DOM match on
  a real run. Either mount them or delete them; a dead panel is worse than no
  panel.

## Features worth considering

- **Run comparison in exports.** `CompareView` exists on screen and no export
  format includes it, so the one artifact you would want to send someone —
  "these two runs, side by side" — cannot leave the browser.
- **Say what to do next.** The engine already detects past-peak, stalled and
  overfitting. It describes them and stops short of the obvious next sentence:
  stop earlier, lower the learning rate, get more data.
- **Confidence in the grade for short runs.** An 11-epoch run and a 200-epoch
  run currently receive equally confident letters.
- **Separate GridSearchCV candidates properly.** Fold results are grouped by
  parameter set and the winner is charted, but `epochix check` reports
  "N candidates x M folds" without per-candidate detail in exports.
