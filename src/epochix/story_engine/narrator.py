from __future__ import annotations

import hashlib
import random
from pathlib import Path

from epochix.enums import Phase, TaskType

# Template variants per task × phase (loaded lazily, cached)
_template_cache: dict[str, list[str]] = {}
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_templates(task: TaskType, phase: Phase, locale: str = "en") -> list[str]:
    key = f"{task.value}/{phase.value}/{locale}"
    if key in _template_cache:
        return _template_cache[key]

    # Try locale-specific file, fall back to English
    for suffix in (f".{locale}.txt", ".txt"):
        path = _TEMPLATES_DIR / task.value / f"{phase.value}{suffix}"
        if path.exists():
            raw = path.read_text(encoding="utf-8").splitlines()
            lines = [ln.strip() for ln in raw if ln.strip()]
            _template_cache[key] = lines or ["Training in progress."]
            return _template_cache[key]

    # Hard fallback — should not happen once all templates exist
    fallback = f"The model is in the {phase.value} phase."
    _template_cache[key] = [fallback]
    return [fallback]


def _load_special(name: str, locale: str, fallback: str) -> list[str]:
    """Load a phase-independent template set (``_stalled``, ``_pastpeak``)."""
    key = f"{name}/{locale}"
    if key in _template_cache:
        return _template_cache[key]
    for suffix in (f".{locale}.txt", ".txt"):
        path = _TEMPLATES_DIR / f"{name}{suffix}"
        if path.exists():
            lines = [
                ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            _template_cache[key] = lines or [fallback]
            return _template_cache[key]
    _template_cache[key] = [fallback]
    return [fallback]


def narrate_past_peak(
    epoch: float | None,
    primary_value: float,
    best_value: float,
    best_epoch: float | None,
    run_id: str,
    locale: str = "en",
) -> str:
    """Say the run is past its best instead of calling it "peak form".

    The phase templates are progress-driven, so a run that peaked at epoch 7
    and declined afterwards was still narrated "Final refinements bring the
    model to peak form" at epoch 10 — contradicting the diagnostics panel on
    the same page, which correctly reported the earlier best checkpoint.
    """
    templates = _load_special("_pastpeak", locale, "The run is past its best value.")
    seed = int(hashlib.md5(run_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    template = random.Random(seed).choice(templates)
    return (
        template.replace("{epoch}", str(int(epoch)) if epoch is not None else "?")
        .replace("{value}", f"{primary_value:.4f}")
        .replace("{best}", f"{best_value:.4f}")
        .replace("{best_epoch}", str(int(best_epoch)) if best_epoch is not None else "?")
    )


def narrate_single_reading(
    primary_value: float,
    run_id: str,
    locale: str = "en",
    metric: str | None = None,
) -> str:
    """Report a result rather than a stage of training.

    The phase templates describe where a run is in its arc — "the model
    awakens", "first patterns emerge from the noise". A script that fits once
    and prints a score has no arc: training finished before the first line was
    printed. Narrating it as epoch one describes a journey that never happened,
    and says the model is "learning to see" when it has already stopped.
    """
    templates = _load_special(
        "_single_reading", locale, "A single result: {metric} {value}. There is no trend to read."
    )
    seed = int(hashlib.md5(run_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    template = random.Random(seed).choice(templates)
    return template.replace("{value}", f"{primary_value:.4f}").replace(
        "{metric}", _display_metric(metric)
    )


def _load_stalled(locale: str = "en") -> list[str]:
    """Templates for a run whose metric has not meaningfully moved."""
    key = f"_stalled/{locale}"
    if key in _template_cache:
        return _template_cache[key]
    for suffix in (f".{locale}.txt", ".txt"):
        path = _TEMPLATES_DIR / f"_stalled{suffix}"
        if path.exists():
            lines = [
                ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            _template_cache[key] = lines or ["The metric has not moved yet."]
            return _template_cache[key]
    fallback = ["The metric has not moved meaningfully yet."]
    _template_cache[key] = fallback
    return fallback


def narrate_stalled(
    epoch: float | None,
    primary_value: float,
    baseline: float,
    epochs_seen: int,
    run_id: str,
    locale: str = "en",
) -> str:
    """Narrate a run that is not learning — honestly, instead of encouragement.

    The phase templates are driven by how far through training we are, so a
    model stuck at chance level still got "the model is a diligent student".
    That asserts progress the data does not show; this says what is true and
    points at the usual causes.
    """
    templates = _load_stalled(locale)
    seed = int(hashlib.md5(run_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    template = random.Random(seed).choice(templates)
    return (
        template.replace("{epoch}", str(int(epoch)) if epoch is not None else "?")
        .replace("{value}", f"{primary_value:.4f}")
        .replace("{baseline}", f"{baseline:.4f}")
        .replace("{epochs_seen}", str(epochs_seen))
    )


# Most task template sets name their metric in the prose — "Accuracy
# {value_pct}", "mAP50 {value_pct}", "Perplexity {value}", "IoU {value}",
# "EER {value_pct}", "FID {value}". That sentence is only true when the run's
# primary metric IS that metric, and often it is not: a task is chosen from the
# metric NAMES a log contains, while the primary metric is the first PREFERRED
# key actually seen. The two disagree routinely.
#
# Observed, all from real log shapes:
#   * XGBoost prints its objective and nothing else. Task classification,
#     primary val_log_loss, narrated "Accuracy 41.8%" — a log loss of 0.418
#     relabelled as an accuracy and multiplied by 100.
#   * A segmentation run logging Dice was narrated "IoU 0.8900". Dice and IoU
#     are different numbers; Dice is always the larger.
#   * A summariser logging ROUGE was narrated "Perplexity falls to 0.5000"
#     while its ROUGE was RISING — wrong metric AND wrong direction.
#
# Prose with a directional verb ("falls to", "climbs to", "and rising") cannot
# be repaired by substituting a name, because the direction belongs to the
# metric too. So when the primary metric is not one a task's prose was written
# for, tell the story with the metric-neutral CUSTOM set instead, which names
# the series and claims nothing about what it measures.
_PROSE_ASSUMES: dict[TaskType, frozenset[str]] = {
    TaskType.CLASSIFICATION: frozenset({"accuracy", "val_accuracy"}),
    TaskType.DETECTION: frozenset({"mAP50", "val_mAP50"}),
    TaskType.SEGMENTATION: frozenset({"IoU", "mIoU", "val_IoU", "val_mIoU"}),
    TaskType.NLP: frozenset({"perplexity", "val_perplexity"}),
    TaskType.BIOMETRIC: frozenset({"EER", "val_EER"}),
    TaskType.GENERATIVE: frozenset({"fid", "FID", "val_fid", "val_FID"}),
    # REGRESSION and GAZE templates already say "{metric}", so they are honest
    # for whichever series they are handed. CUSTOM names no metric at all.
}


def _prose_fits_metric(task: TaskType, metric: str | None) -> bool:
    """Whether *task*'s templates can honestly describe *metric*."""
    assumed = _PROSE_ASSUMES.get(task)
    if assumed is None:
        return True
    if not metric:
        # No named series: the task's own metric is the only reading it could
        # be, which is what the templates already assume.
        return True
    return metric in assumed


def narrate(
    task: TaskType,
    phase: Phase,
    epoch: float | None,
    primary_value: float,
    delta: float,
    run_id: str,
    locale: str = "en",
    metric: str | None = None,
) -> str:
    """Select and fill a narrative template deterministically for this run + epoch.

    ``metric`` names the series the numbers came from. The regression and gaze
    templates used to write "MAE" into the sentence regardless, so an XGBoost
    run graded on RMSE was narrated as "MAE 68.0337" — a number correctly read
    and then labelled as a metric the run never logged.
    """
    prose_task = task if _prose_fits_metric(task, metric) else TaskType.CUSTOM
    templates = _load_templates(prose_task, phase, locale)

    # Deterministic variant selection: same run_id always gives same story.
    # MD5 here is a non-cryptographic seed only (not a security primitive).
    seed = int(hashlib.md5(run_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    rng = random.Random(seed)
    template = rng.choice(templates)

    epoch_str = str(int(epoch)) if epoch is not None else "?"
    delta_str = f"{delta:+.4f}" if delta != 0 else "0"

    return (
        template.replace("{epoch}", epoch_str)
        .replace("{value}", f"{primary_value:.4f}")
        .replace("{delta}", delta_str)
        .replace("{value_pct}", f"{primary_value * 100:.1f}%")
        .replace("{metric}", _display_metric(metric))
    )


# Canonical keys are stored in a machine form ("val_RMSE"); the story is a
# sentence, so it says "validation RMSE".
_METRIC_PREFIXES = (("val_", "validation "), ("train_", "training "))


def _display_metric(metric: str | None) -> str:
    if not metric:
        return "error"
    for prefix, spoken in _METRIC_PREFIXES:
        if metric.startswith(prefix):
            return spoken + metric[len(prefix) :].replace("_", " ")
    return metric.replace("_", " ")
