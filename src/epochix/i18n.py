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
    "grade_note.few_readings": "Provisional: this grade rests on fewer than five "
    "readings of the metric.",
    "grade_note.still_improving": "Still improving at the last reading — the grade "
    "shows where the run got to, not where it was heading.",
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
    "grade_note.few_readings": "موقت: این نمره بر کمتر از پنج خوانش از سنجه تکیه دارد.",
    "grade_note.still_improving": "در آخرین خوانش هنوز در حال بهبود بود — نمره نشان "
    "می‌دهد اجرا به کجا رسید، نه به کجا می‌رفت.",
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
    "grade_note.few_readings": "Provisoire : cette note repose sur moins de cinq "
    "mesures de la métrique.",
    "grade_note.still_improving": "Encore en progrès à la dernière mesure — la note "
    "montre où l'exécution est arrivée, pas où elle allait.",
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
}

_LOCALES: dict[str, dict[str, str]] = {"en": _EN, "fa": _FA, "fr": _FR}

SUPPORTED_LOCALES = tuple(_LOCALES)


def t(key: str, locale: str = "en") -> str:
    """Translate *key*, falling back to English and then to the key itself.

    An unknown locale is not an error: a run created by a newer client, or a
    user passing ``de``, gets English rather than a crash in the middle of an
    export.
    """
    table = _LOCALES.get(locale, _EN)
    return table.get(key) or _EN.get(key) or key


def is_rtl(locale: str) -> bool:
    return locale in RTL_LOCALES
