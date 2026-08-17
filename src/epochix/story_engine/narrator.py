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
    templates = _load_templates(task, phase, locale)

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
