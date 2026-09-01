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

Landed so far: the curves (loss / quality / error panels), a cover that carries
its own evidence, a per-epoch table, and runs named after their log instead of
their ULID. A 20-epoch export went from 5 pages of four text lines to 7 pages
with charts and a full epoch listing.

Still open:

- **Final metrics is a bare list.** Four rows of numbers with nothing to
  compare them against — no best-vs-final per series, no direction, no units.
  The cover now does this for the primary metric only.
- **Skill dimensions and metaphor cards never reach the PDF** although the
  engine computes them for every frame and the dashboard shows them.
- **Phase pages are still four lines each.** With the epoch table carrying the
  numbers, these pages should either say more about the phase or go away.
- **Non-Latin text still cannot be drawn on the page — decided, not open.**
  fpdf2's core fonts are Latin-1. Embedding a Unicode font was considered and
  rejected for now, on measured grounds: DejaVuSans does not cover Arabic, so
  it would not help the locale this project actually ships; Farsi additionally
  needs `uharfbuzz` for contextual shaping, a new runtime dependency that
  contradicts the one-installer promise; and CJK coverage is ~10 MB against a
  3.2 MB dependency. Half-doing it (Latin Extended + Cyrillic) fixes languages
  we do not ship and not the one we do.

  Mitigated instead, at no cost: the real name travels in the PDF metadata
  (UTF-16, no font needed) so viewers and file properties show it correctly,
  and the cover keeps whatever survives Latin-1 rather than printing
  `??????` — falling back to the run id when nothing legible does.

  Revisit if someone asks for it, or if a Farsi-covering font under a
  permissive licence can be subset small enough to carry.

- **A GridSearchCV run charts nothing.** Its score canonicalises to `custom`,
  which is in none of the chart key groups, so the one number the search
  produced never reaches a curve.
- **No architecture section.** `parse_architecture` reads the model summary out
  of the log and the Network panel draws it; the PDF ignores it entirely.

## Internationalisation

Audited: **narratives are complete** — all 54 template groups exist in English,
Farsi and French — and the **dashboard UI is complete**, 60 of 60 keys in all
three (the five French strings identical to English are words French shares:
Phase, Classification, Diagnostics, Distributions).

The gap is exports:

- **No exporter takes a locale.** `build_pdf`, `build_markdown`, `build_html`
  and `build_json_payload` all take `(run_id, store)` and nothing else, so
  every heading a report prints — "Final metrics", "Every epoch", "How the run
  moved" — is hardcoded English. A Farsi run's stored narratives come out in
  Farsi while the structure around them stays English.
- **The PDF cannot draw non-Latin script at all** (see above), so a Farsi
  report is doubly affected: English headings around unrenderable body text.

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
