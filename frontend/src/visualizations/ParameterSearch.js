/**
 * ParameterSearch.js — every setting a cross-validation tried, ranked.
 *
 * The learning curve can carry one number per metric — the chosen setting's
 * mean — and until now that was all the dashboard showed of a GridSearchCV:
 * the reports listed every setting, the page they were exported from did not.
 * Reads store.crossValidation (run.config.cross_validation from the server, or
 * the VS Code extension's engine) and hides its whole section when a run has
 * none, rather than showing an empty table.
 */
import { escapeHtml as _esc } from '../escape.js';
import { t } from '../i18n/apply.js';
import { isSearch, summarise } from '../crossValidation.js';

const fmt = (v) => (Number.isFinite(v) ? Number(v.toPrecision(4)).toString() : '');

export class ParameterSearch {
  /**
   * @param {HTMLElement} container  where the table goes
   * @param {HTMLElement|null} section  hidden while there is nothing to show
   */
  constructor(container, section = null) {
    this._el = container;
    this._section = section;
    this._shown = undefined;
    this._unsub = null;
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._render(store.get());
    this._unsub = store.subscribe((s) => this._render(s));
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  _render(s) {
    const cv = s.crossValidation ?? null;
    if (cv === this._shown) return;
    this._shown = cv;
    const rows = cv ? summarise(cv) : [];
    if (this._section) this._section.hidden = rows.length === 0;
    if (rows.length === 0) {
      this._el.innerHTML = '';
      return;
    }
    const search = isSearch(cv);
    const head = [
      ...(search ? [t('cv.setting', 'Setting')] : []),
      t('cv.metric', 'Metric'),
      t('cv.mean', 'Mean'),
      t('cv.spread', '± std'),
      t('cv.range', 'Range'),
      t('cv.folds', 'Folds'),
    ];
    const chosen = ` <span class="cv-chosen">${_esc(t('cv.chosen', 'chosen'))}</span>`;
    const body = rows.map((r) => {
      const cells = [
        ...(search ? [`<td class="cv-setting"><code>${_esc(r.setting)}</code>${r.chosen ? chosen : ''}</td>`] : []),
        `<td><code>${_esc(r.metric)}</code></td>`,
        `<td class="cv-num">${_esc(fmt(r.mean))}</td>`,
        `<td class="cv-num">${r.std === null ? '' : _esc(fmt(r.std))}</td>`,
        `<td class="cv-num">${_esc(`${fmt(r.lowest)} – ${fmt(r.highest)}`)}</td>`,
        `<td class="cv-num">${r.folds}</td>`,
      ];
      return `<tr${r.chosen ? ' class="is-chosen"' : ''}>${cells.join('')}</tr>`;
    }).join('');
    const title = search
      ? t('cv.title_search', 'Parameter search')
      : t('cv.title_cv', 'Cross-validation');
    const note = search
      ? t('cv.note_search', 'Only the chosen setting is charted and graded: the highest mean, as scikit-learn scorers are higher-is-better. Fold order carries no meaning.')
      : t('cv.note_cv', 'Folds are reported here rather than charted: their order carries no meaning, so they have no trend.');
    this._el.innerHTML = `
      <h3 class="cv-title">${_esc(title)}</h3>
      <div class="cv-table-wrap">
        <table class="cv-table">
          <thead><tr>${head.map((h) => `<th>${_esc(h)}</th>`).join('')}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <p class="cv-note">${_esc(note)}</p>`;
  }
}
