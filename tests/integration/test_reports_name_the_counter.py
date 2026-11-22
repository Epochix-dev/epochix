"""A report names the counter its run counts by, as the story does.

The story of a nanoGPT run is told by step and a CatBoost run's by boosting
round (test_step_counted_runs.py, test_counter_words.py). The reports around
the story still said epoch: a PDF's table headed "Every epoch" with a column
"epoch" running to step 2000, a cover fact "best ... (epoch 44)" for round 44,
a Markdown milestone "(epoch 0)", and a comparison whose best was "(epoch 6)"
under a column "Epochs" for two boosting runs.

Driven through the real pipeline and the real exporters. A run that has
epochs must read exactly as it did.
"""

from __future__ import annotations

import asyncio
import re
import zlib
from pathlib import Path

import pytest

from epochix.exporters.compare_export import build_comparison_markdown, build_comparison_pdf
from epochix.exporters.markdown_export import build_markdown
from epochix.exporters.pdf_export import build_pdf
from epochix.i18n import _COUNTED, SUPPORTED_LOCALES, t
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.messages import COUNTERS, frames_counter

REPO = Path(__file__).resolve().parents[2]
LOGS = REPO / "tests" / "fixtures" / "logs"
NANOGPT = LOGS / "nanogpt_real.log"  # counts steps
CATBOOST = LOGS / "catboost_real_classifier.log"  # boosting rounds
XGBOOST = LOGS / "xgboost_real_classifier.log"  # boosting rounds
LORA = LOGS / "diffusers_lora_real.log"  # steps, of the 120 its bar names
KERAS = REPO / "demo" / "keras_image_classifier.log"  # epochs

# The word for an epoch in each language. Farsi's is not the plural of "دور"
# (round), "دورها", which begins with the same letters.
_EPOCH = {
    "en": re.compile(r"\bepochs?\b", re.I),
    "fr": re.compile(r"[ée]poques?", re.I),
    "fa": re.compile("دوره(?!ا)"),
}
# The labels a report names the counter with.
_LABELS = (
    "col.epoch",
    "cover.epoch_n",
    "cover.epochs",
    "phase.covers",
    "md.epochs",
    "pdf.epochs",
    "pdf.epochs_continued",
)


def _store(locale: str, *logs: Path) -> tuple[RunStore, list[str]]:
    store = RunStore(":memory:")
    ids = []
    for i, log in enumerate(logs):
        assert log.stat().st_size > 0
        run_id = f"r{i}"
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester(run_id, str(log)),
                run_id=run_id,
                store=store,
                hub=Hub(),
                locale=locale,
            )
        )
        ids.append(run_id)
    return store, ids


def _pdf_text(pdf: bytes) -> str:
    """The text drawn on every page, joined (Latin-1 core font: plain Tj strings)."""
    pages = re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S)
    out: list[bytes] = []
    for page in pages:
        try:
            out += re.findall(rb"\((.*?)\) ?Tj", zlib.decompress(page))
        except zlib.error:
            continue
    assert out, "no text was read from the PDF"
    return b" ".join(out).decode("latin-1")


# ── the labels ───────────────────────────────────────────────────────────────


def test_every_label_has_a_word_for_every_counter_in_every_language() -> None:
    assert set(_COUNTED) == set(SUPPORTED_LOCALES)
    for locale in SUPPORTED_LOCALES:
        assert set(_COUNTED[locale]) == set(COUNTERS) - {"epoch"}, locale
        for counter in COUNTERS:
            for key in _LABELS:
                said = t(key, locale, counter)
                assert said and said != key, (locale, counter, key)
                if counter == "epoch":
                    assert said == t(key, locale), "an epoch's label is the label as it was"
                else:
                    assert not _EPOCH[locale].search(said), (locale, counter, key, said)
                    assert said != t(key, locale), (locale, counter, key)


def test_a_label_without_a_counter_reads_as_it_always_has() -> None:
    assert t("pdf.epochs", "en") == t("pdf.epochs", "en", None) == "Every epoch"
    assert t("col.epoch", "fr", "epoch") == "époque"
    # A label that names no counter is the same for every run.
    assert t("cover.best", "en", "step") == t("cover.best", "en")
    # An unknown locale speaks English, of the right counter.
    assert t("col.epoch", "de", "round") == "round"


# ── Markdown ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
@pytest.mark.parametrize(
    ("log", "counter"),
    [(NANOGPT, "step"), (CATBOOST, "round"), (LORA, "step")],
    ids=["nanogpt", "catboost", "lora"],
)
def test_a_markdown_report_has_no_epoch_for_a_run_without_one(
    log: Path, counter: str, locale: str
) -> None:
    store, (run_id,) = _store(locale, log)
    frames = store.get_story_frames(run_id)
    assert frames_counter(frames) == counter, "premise"
    md = build_markdown(run_id, store)
    assert len(md) > 400
    assert not _EPOCH[locale].search(md), [
        line for line in md.splitlines() if _EPOCH[locale].search(line)
    ]


class _With:
    """A store whose run holds a length the pipeline never stores.

    The Markdown report's length row is written from `Run.total_epochs_est`,
    which a run read back from a RunStore leaves empty. An SDK caller's own
    store can hold it, and the row named an epoch.
    """

    def __init__(self, store: RunStore, run: object) -> None:
        self._store, self._run = store, run

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    def get_run(self, _run_id: str) -> object:
        return self._run


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_a_milestone_is_dated_by_the_run_s_own_counter(locale: str) -> None:
    """ "(epoch 0)" beside a boosting run's first best."""
    store, (run_id,) = _store(locale, CATBOOST)
    assert store.get_milestones(run_id), "premise: the run reached a milestone"
    md = build_markdown(run_id, store)
    assert f"## {t('md.milestones', locale)}" in md, md
    assert f"({t('cover.epoch_n', locale, 'round')} 0)" in md, md
    assert not _EPOCH[locale].search(md), md


def test_a_milestone_of_a_run_with_epochs_is_dated_as_before() -> None:
    store, (run_id,) = _store("en", KERAS)
    md = build_markdown(run_id, store)
    assert "## Milestones" in md and "(epoch 1)" in md, md


@pytest.mark.parametrize(
    ("log", "length", "row"),
    [(LORA, 120, "| **Steps** | 120 |"), (KERAS, 20, "| **Epochs** | 20 |")],
    ids=["lora", "keras"],
)
def test_a_run_s_length_is_in_what_it_counts(log: Path, length: int, row: str) -> None:
    store, (run_id,) = _store("en", log)
    run = store.get_run(run_id)
    assert run is not None
    held = run.model_copy(update={"total_epochs_est": length})
    md = build_markdown(run_id, _With(store, held))  # type: ignore[arg-type]
    assert row in md, md[:900]


def test_a_run_with_epochs_still_reports_no_other_counter() -> None:
    store, (run_id,) = _store("en", KERAS)
    md = build_markdown(run_id, store)
    assert len(md) > 400
    assert not re.search(r"\b(?<!Next )(steps?|rounds?|iterations?)\b", md, re.I), md


# ── PDF ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", ["en", "fr"])
@pytest.mark.parametrize(
    ("log", "counter"), [(NANOGPT, "step"), (CATBOOST, "round")], ids=["nanogpt", "catboost"]
)
def test_a_pdf_report_has_no_epoch_for_a_run_without_one(
    log: Path, counter: str, locale: str
) -> None:
    store, (run_id,) = _store(locale, log)
    text = _pdf_text(build_pdf(run_id=run_id, store=store))
    assert not _EPOCH[locale].search(text), _EPOCH[locale].findall(text)
    # The table of readings is headed for what it lists, column and title.
    for key in ("pdf.epochs", "col.epoch", "cover.epochs"):
        assert t(key, locale, counter) in text, (key, text[:600])


def test_a_pdf_report_of_a_run_with_epochs_reads_as_before() -> None:
    store, (run_id,) = _store("en", KERAS)
    text = _pdf_text(build_pdf(run_id=run_id, store=store))
    for key in ("pdf.epochs", "col.epoch", "cover.epochs"):
        assert t(key, "en") in text, key
    assert "Every reading" not in text
    assert not re.search(r"\b(?<!Next )(steps?|rounds?|iterations?)\b", text, re.I)


# ── the comparison ───────────────────────────────────────────────────────────


def test_two_boosting_runs_are_compared_by_round() -> None:
    store, ids = _store("en", CATBOOST, XGBOOST)
    md = build_comparison_markdown(ids, store)
    # Each run's best is dated by its round, under a column that counts readings.
    assert len(re.findall(r"\(round \d{1,3}\)", md)) == 2, md
    assert "| Readings |" in md and "Epochs" not in md, md
    assert not _EPOCH["en"].search(md), md
    text = _pdf_text(build_comparison_pdf(ids, store))
    assert "(round " in text and not _EPOCH["en"].search(text), text[:600]


def test_two_runs_with_epochs_are_compared_as_before() -> None:
    store, ids = _store("en", KERAS, KERAS)
    md = build_comparison_markdown(ids, store)
    assert len(re.findall(r"\(epoch \d{1,3}\)", md)) == 2, md
    assert "| Epochs |" in md and "Readings" not in md, md


def test_a_gap_within_the_noise_is_measured_between_readings_not_epochs() -> None:
    """ "No larger than the epoch-to-epoch movement" was said of boosting runs."""
    from epochix.story_engine.comparison import RunTrajectory, narrate_comparison

    def run(name: str, last: float, counter: str | None) -> RunTrajectory:
        values = [(float(i), v) for i, v in enumerate((0.50, 0.60, 0.70, last))]
        return RunTrajectory(name, "val_accuracy", values, counter=counter)  # type: ignore[arg-type]

    said = narrate_comparison([run("a", 0.80, "round"), run("b", 0.81, "round")])
    assert "reading-to-reading movement" in said and "epoch" not in said, said
    # One run that does not count epochs is enough: an epoch of one against a
    # round of the other is not "epoch-to-epoch".
    mixed = narrate_comparison([run("a", 0.80, "epoch"), run("b", 0.81, "round")])
    assert "reading-to-reading movement" in mixed, mixed
    for counter in ("epoch", None):
        said = narrate_comparison([run("a", 0.80, counter), run("b", 0.81, counter)])
        assert "epoch-to-epoch movement" in said, said


def test_a_run_past_its_peak_is_said_to_have_peaked_at_its_own_counter() -> None:
    from epochix.story_engine.comparison import RunTrajectory, narrate_comparison

    def run(name: str, values: list[float], counter: str) -> RunTrajectory:
        points = [(float(i * 250), v) for i, v in enumerate(values)]
        return RunTrajectory(name, "val_accuracy", points, counter=counter)  # type: ignore[arg-type]

    winner = run("steady", [0.5, 0.6, 0.7, 0.8, 0.9], "step")
    loser = run("peaked", [0.5, 0.8, 0.7, 0.6, 0.5], "step")
    for locale, phrase in (("en", "on step 250"), ("fr", "à l'étape 250"), ("fa", "گام 250")):
        said = narrate_comparison([winner, loser], locale)
        assert phrase in said, said
        assert not _EPOCH[locale].search(said), said
