from __future__ import annotations

import hashlib
import random
from pathlib import Path

from model_story.enums import Phase, TaskType

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


def narrate(
    task: TaskType,
    phase: Phase,
    epoch: float | None,
    primary_value: float,
    delta: float,
    run_id: str,
    locale: str = "en",
) -> str:
    """Select and fill a narrative template deterministically for this run + epoch."""
    templates = _load_templates(task, phase, locale)

    # Deterministic variant selection: same run_id always gives same story
    seed = int(hashlib.md5(run_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    template = rng.choice(templates)

    epoch_str = str(int(epoch)) if epoch is not None else "?"
    delta_str = f"{delta:+.4f}" if delta != 0 else "0"

    return (
        template
        .replace("{epoch}", epoch_str)
        .replace("{value}", f"{primary_value:.4f}")
        .replace("{delta}", delta_str)
        .replace("{value_pct}", f"{primary_value * 100:.1f}%")
    )
