"""Strings the Python side prints, in every locale the project ships.

The narrative templates and the dashboard UI have been translated into English,
Farsi and French from the start. The **exports** never were: `build_pdf`,
`build_markdown` and friends took `(run_id, store)` and nothing else, so a run
narrated in Farsi produced a report whose headings were all English. The
sentences were translated and the structure around them was not.

Keys are flat and named after what they label, so a missing one is obvious in a
diff rather than hidden three levels down a nested dict.

Falling back is deliberate: an untranslated key returns the English rather than
the key name or an empty string. A partially translated locale should read a
little English, not break.
"""

from __future__ import annotations

# Locales whose text runs right to left. Mirrors RTL_LOCALES in
# frontend/src/i18n/apply.js — the two must agree or the same run reads one way
# in the dashboard and the other in its export.
RTL_LOCALES = frozenset({"fa"})

_EN: dict[str, str] = {
    "pdf.skills": "Skills",
    "pdf.architecture": "The model",
    "pdf.total_params": "total parameters",
    "col.metric": "metric",
    "col.final": "final",
    "col.layer": "layer",
    "col.type": "type",
    "col.params": "parameters",
    "col.does": "what it does",
    "phase.covers": "epochs",
    # PDF section titles
    "pdf.charts": "How the run moved",
    "pdf.epochs": "Every epoch",
    "pdf.epochs_continued": "Every epoch (continued)",
    "pdf.continued": "continued",
    "pdf.final_metrics": "Final metrics",
    "pdf.chart.loss": "Loss",
    "pdf.chart.quality": "Quality",
    "pdf.chart.error": "Error",
    # PDF table columns
    "col.epoch": "epoch",
    "col.value": "value",
    "col.change": "change",
    "col.phase": "phase",
    "col.grade": "grade",
    "col.best": "best",
    # PDF cover facts
    "cover.final": "final",
    "cover.best": "best",
    "cover.since_best": "since best",
    "cover.epochs": "epochs",
    "cover.read_by": "read by",
    "cover.worse": "worse",
    "cover.better": "better",
    "cover.epoch_n": "epoch",
    # Markdown
    "md.field": "Field",
    "md.value": "Value",
    "md.grade": "Grade",
    "md.task": "Task",
    "cmp.title": "Run comparison",
    "cmp.run": "Run",
    "cv.title": "Cross-validation",
    "cv.search_title": "Parameter search",
    "cv.setting": "Setting",
    "cv.metric": "Metric",
    "cv.mean": "Mean",
    "cv.spread": "± std",
    "cv.range": "Range",
    "cv.folds": "Folds",
    "cv.chosen": "chosen",
    "cv.search_note": "Only the chosen setting is charted and graded: the highest mean, as "
    "scikit-learn scorers are higher-is-better. Fold order carries no meaning.",
    "cv.note": "Folds are reported here rather than charted: their order carries no meaning, "
    "so they have no trend.",
    "md.grade_note": "About the grade",
    "md.grade_basis": "How it was graded",
    "grade_basis.thresholds": "Against fixed thresholds for this metric.",
    "grade_basis.improvement": "On how far this metric improved since its first reading.",
    "grade_note.few_readings": "Provisional: this grade rests on fewer than five "
    "readings of the metric.",
    "grade_note.still_improving": "Still improving at the last reading — the grade "
    "shows where the run got to, not where it was heading.",
    "grade_note.unsteady": "Not graded: this metric's readings rise and fall too much "
    "from one to the next for a single reading to place the run.",
    "grade_note.running_mean": "Not graded: this metric is a running average over the most "
    "recent batches. Each reading shares all but one batch with the one before, and the first "
    "readings average fewer batches than the rest, so no reading is a baseline to grade against.",
    "md.final_phase": "Final phase",
    "md.primary_metric": "Primary metric",
    "md.epochs": "Epochs",
    "md.framework": "Framework",
    "md.finished": "Finished",
    "md.summary": "Summary",
    "md.final_state": "Final State",
    "md.key_metrics": "Key Metrics",
    "md.metric": "Metric",
    "md.final_value": "Final Value",
    "md.milestones": "Milestones",
    "md.warnings": "Warnings",
    # A comparison's count of readings, where its runs do not all count epochs.
    "cmp.readings": "Readings",
}

_FA: dict[str, str] = {
    "pdf.skills": "مهارت‌ها",
    "pdf.architecture": "مدل",
    "pdf.total_params": "مجموع پارامترها",
    "col.metric": "معیار",
    "col.final": "نهایی",
    "col.layer": "لایه",
    "col.type": "نوع",
    "col.params": "پارامترها",
    "col.does": "کارکرد",
    "phase.covers": "دوره‌ها",
    "pdf.charts": "روند اجرا",
    "pdf.epochs": "همه دوره‌ها",
    "pdf.epochs_continued": "همه دوره‌ها (ادامه)",
    "pdf.continued": "ادامه",
    "pdf.final_metrics": "معیارهای نهایی",
    "pdf.chart.loss": "خطا",
    "pdf.chart.quality": "کیفیت",
    "pdf.chart.error": "میزان خطا",
    "col.epoch": "دوره",
    "col.value": "مقدار",
    "col.change": "تغییر",
    "col.phase": "مرحله",
    "col.grade": "نمره",
    "col.best": "بهترین",
    "cover.final": "نهایی",
    "cover.best": "بهترین",
    "cover.since_best": "از بهترین تاکنون",
    "cover.epochs": "دوره‌ها",
    "cover.read_by": "خوانده‌شده با",
    "cover.worse": "بدتر",
    "cover.better": "بهتر",
    "cover.epoch_n": "دوره",
    "md.field": "فیلد",
    "md.value": "مقدار",
    "md.grade": "نمره",
    "md.task": "وظیفه",
    "cmp.title": "مقایسهٔ اجراها",
    "cmp.run": "اجرا",
    "cmp.readings": "خوانش‌ها",
    "cv.title": "اعتبارسنجی متقابل",
    "cv.search_title": "جست‌وجوی پارامتر",
    "cv.setting": "تنظیم",
    "cv.metric": "سنجه",
    "cv.mean": "میانگین",
    "cv.spread": "± انحراف معیار",
    "cv.range": "بازه",
    "cv.folds": "تعداد بخش‌ها",
    "cv.chosen": "انتخاب‌شده",
    "cv.search_note": "تنها تنظیم انتخاب‌شده رسم و نمره‌دهی می‌شود: بیشترین میانگین، چون "
    "امتیازدهنده‌های scikit-learn هرچه بیشتر بهتر هستند. ترتیب بخش‌ها معنایی ندارد.",
    "cv.note": "بخش‌ها این‌جا گزارش می‌شوند، نه در نمودار: ترتیبشان معنایی ندارد، پس روندی هم ندارند.",
    "md.grade_note": "دربارهٔ نمره",
    "md.grade_basis": "نحوهٔ نمره‌دهی",
    "grade_basis.thresholds": "در برابر آستانه‌های ثابت برای این سنجه.",
    "grade_basis.improvement": "بر پایهٔ میزان بهبود این سنجه از نخستین اندازه‌گیری.",
    "grade_note.few_readings": "موقت: این نمره بر کمتر از پنج خوانش از سنجه تکیه دارد.",
    "grade_note.still_improving": "در آخرین خوانش هنوز در حال بهبود بود — نمره نشان "
    "می‌دهد اجرا به کجا رسید، نه به کجا می‌رفت.",
    "grade_note.unsteady": "نمره داده نشد: خوانش‌های این سنجه از یکی به بعدی بیش از آن بالا و "
    "پایین می‌روند که یک خوانش جای اجرا را نشان دهد.",
    "grade_note.running_mean": "نمره داده نشد: این سنجه میانگینی متحرک روی تازه‌ترین دسته‌هاست. "
    "هر خوانش جز در یک دسته با خوانش قبلی یکی است، و خوانش‌های نخست میانگین دسته‌های کمتری از "
    "بقیه‌اند؛ پس هیچ خوانشی مبنایی برای نمره‌دادن نیست.",
    "md.final_phase": "مرحله نهایی",
    "md.primary_metric": "معیار اصلی",
    "md.epochs": "دوره‌ها",
    "md.framework": "چارچوب",
    "md.finished": "پایان",
    "md.summary": "خلاصه",
    "md.final_state": "وضعیت نهایی",
    "md.key_metrics": "معیارهای کلیدی",
    "md.metric": "معیار",
    "md.final_value": "مقدار نهایی",
    "md.milestones": "نقاط عطف",
    "md.warnings": "هشدارها",
}

_FR: dict[str, str] = {
    "pdf.skills": "Compétences",
    "pdf.architecture": "Le modèle",
    "pdf.total_params": "paramètres au total",
    "col.metric": "métrique",
    "col.final": "final",
    "col.layer": "couche",
    "col.type": "type",
    "col.params": "paramètres",
    "col.does": "rôle",
    "phase.covers": "époques",
    "pdf.charts": "L'évolution du run",
    "pdf.epochs": "Chaque époque",
    "pdf.epochs_continued": "Chaque époque (suite)",
    "pdf.continued": "suite",
    "pdf.final_metrics": "Métriques finales",
    "pdf.chart.loss": "Perte",
    "pdf.chart.quality": "Qualité",
    "pdf.chart.error": "Erreur",
    "col.epoch": "époque",
    "col.value": "valeur",
    "col.change": "variation",
    "col.phase": "phase",
    "col.grade": "note",
    "col.best": "meilleur",
    "cover.final": "final",
    "cover.best": "meilleur",
    "cover.since_best": "depuis le meilleur",
    "cover.epochs": "époques",
    "cover.read_by": "lu par",
    "cover.worse": "moins bon",
    "cover.better": "meilleur",
    "cover.epoch_n": "époque",
    "md.field": "Champ",
    "md.value": "Valeur",
    "md.grade": "Note",
    "md.task": "Tâche",
    "cmp.title": "Comparaison des exécutions",
    "cmp.run": "Exécution",
    "cv.title": "Validation croisée",
    "cv.search_title": "Recherche de paramètres",
    "cv.setting": "Réglage",
    "cv.metric": "Métrique",
    "cv.mean": "Moyenne",
    "cv.spread": "± écart-type",
    "cv.range": "Plage",
    "cv.folds": "Plis",
    "cv.chosen": "choisi",
    "cv.search_note": "Seul le réglage choisi est tracé et noté : la moyenne la plus haute, les "
    "scores de scikit-learn étant « plus haut = mieux ». L'ordre des plis n'a pas "
    "de sens.",
    "cv.note": "Les plis sont rapportés ici plutôt que tracés : leur ordre n'a pas de sens, "
    "ils n'ont donc pas de tendance.",
    "md.grade_note": "À propos de la note",
    "md.grade_basis": "Mode de notation",
    "grade_basis.thresholds": "Selon des seuils fixes pour cette métrique.",
    "grade_basis.improvement": "Selon la progression de cette métrique depuis sa première mesure.",
    "grade_note.few_readings": "Provisoire : cette note repose sur moins de cinq "
    "mesures de la métrique.",
    "grade_note.still_improving": "Encore en progrès à la dernière mesure — la note "
    "montre où l'exécution est arrivée, pas où elle allait.",
    "grade_note.unsteady": "Non noté : les mesures de cette métrique montent et descendent "
    "trop de l'une à la suivante pour qu'une seule situe l'entraînement.",
    "grade_note.running_mean": "Non noté : cette métrique est une moyenne glissante sur les lots "
    "les plus récents. Chaque mesure partage tous ses lots sauf un avec la précédente, et les "
    "premières moyennent moins de lots que les autres : aucune ne sert de référence pour noter.",
    "md.final_phase": "Phase finale",
    "md.primary_metric": "Métrique principale",
    "md.epochs": "Époques",
    "md.framework": "Framework",
    "md.finished": "Terminé",
    "md.summary": "Résumé",
    "md.final_state": "État final",
    "md.key_metrics": "Métriques clés",
    "md.metric": "Métrique",
    "md.final_value": "Valeur finale",
    "md.milestones": "Jalons",
    "md.warnings": "Avertissements",
    "cmp.readings": "Mesures",
}

_LOCALES: dict[str, dict[str, str]] = {"en": _EN, "fa": _FA, "fr": _FR}


def _counted(one: str, many: str, title: str, every: str, continued: str) -> dict[str, str]:
    """The labels that name the counter, for one kind of counter in one language."""
    return {
        "col.epoch": one,
        "cover.epoch_n": one,
        "cover.epochs": many,
        "phase.covers": many,
        "md.epochs": title,
        # The table has a row for every reading. That is a row an epoch only
        # for a run read once an epoch: a run told every 250 steps has nine.
        "pdf.epochs": every,
        "pdf.epochs_continued": continued,
    }


# The same labels for a run that does not count epochs. A report on a nanoGPT
# run had a column headed "epoch" running to 2000, and a CatBoost run's sixty
# rounds were listed under "Every epoch". Whole words per language and kind,
# as the story's own are (story_engine.messages.COUNTER_FORMS).
_COUNTED: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "step": _counted("step", "steps", "Steps", "Every reading", "Every reading (continued)"),
        "iteration": _counted(
            "iteration", "iterations", "Iterations", "Every reading", "Every reading (continued)"
        ),
        "round": _counted(
            "round", "rounds", "Rounds", "Every reading", "Every reading (continued)"
        ),
    },
    "fa": {
        "step": _counted("گام", "گام‌ها", "گام‌ها", "همه خوانش‌ها", "همه خوانش‌ها (ادامه)"),
        "iteration": _counted("تکرار", "تکرارها", "تکرارها", "همه خوانش‌ها", "همه خوانش‌ها (ادامه)"),
        "round": _counted("دور", "دورها", "دورها", "همه خوانش‌ها", "همه خوانش‌ها (ادامه)"),
    },
    "fr": {
        "step": _counted("étape", "étapes", "Étapes", "Chaque mesure", "Chaque mesure (suite)"),
        "iteration": _counted(
            "itération", "itérations", "Itérations", "Chaque mesure", "Chaque mesure (suite)"
        ),
        "round": _counted("tour", "tours", "Tours", "Chaque mesure", "Chaque mesure (suite)"),
    },
}

SUPPORTED_LOCALES = tuple(_LOCALES)


def t(key: str, locale: str = "en", counter: str | None = None) -> str:
    """Translate *key*, falling back to English and then to the key itself.

    An unknown locale is not an error: a run created by a newer client, or a
    user passing ``de``, gets English rather than a crash in the middle of an
    export.

    *counter* is what the run counts by (StoryFrame.counter), for a label
    that names it: "step" where an epoch run's report says "epoch". None, or
    "epoch", is the label as it has always read.
    """
    if counter not in (None, "epoch"):
        counted = _COUNTED.get(locale, _COUNTED["en"]).get(counter or "", {})
        if key in counted:
            return counted[key]
    table = _LOCALES.get(locale, _EN)
    return table.get(key) or _EN.get(key) or key


def is_rtl(locale: str) -> bool:
    return locale in RTL_LOCALES
