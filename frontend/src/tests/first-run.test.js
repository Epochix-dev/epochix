/**
 * Someone with nothing loaded is told what Epochix reads before being handed
 * an empty bug form.
 *
 * Both reports that reached the tracker from outside in the first month (#35,
 * #101) were filed from an empty panel with the form left blank; one was
 * titled "my code project" — its author expected Epochix to read their code.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { setActiveI18n, t } from '../i18n/apply.js';
import en from '../i18n/en.json';
import fa from '../i18n/fa.json';
import fr from '../i18n/fr.json';
import { JourneyPanel } from '../panels/JourneyPanel.js';
import { dashboardReportBody, nothingLoadedPrompt } from '../report.js';

const CATALOGUES = { en, fa, fr };

describe('the empty panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="narrative-text"></div>';
  });
  afterEach(() => setActiveI18n(null));

  for (const [locale, cat] of Object.entries(CATALOGUES)) {
    it(`says what Epochix reads, before how to load a run (${locale})`, () => {
      setActiveI18n(cat);
      const panel = Object.create(JourneyPanel.prototype);
      panel._i18n = {};
      panel._render({ host: 'vscode', attached: false, live: true, frames: [], currentFrame: null, run: null });
      const text = document.getElementById('narrative-text').textContent;
      expect(cat.labels.empty_what).toBeTruthy();
      expect(text).toContain(cat.labels.empty_what);
      expect(text.indexOf(cat.labels.empty_what)).toBeLessThan(text.indexOf(cat.labels.empty_hint));
    });
  }

  it('the English sentence names both what it reads and what it does not', () => {
    expect(en.labels.empty_what).toMatch(/what a training run prints/);
    expect(en.labels.empty_what).toMatch(/not your source code/);
  });
});

describe('the report button with nothing loaded', () => {
  afterEach(() => setActiveI18n(null));

  it('in VS Code offers the demo and a log file before a report', () => {
    setActiveI18n(en);
    const prompt = nothingLoadedPrompt({ inVsCode: true, t });
    const buttons = [...prompt.querySelectorAll('button')];
    expect(buttons.map((b) => b.dataset.command ?? 'report')).toEqual([
      'epochix.tryDemo',
      'epochix.openLogFile',
      'report',
    ]);
    expect(prompt.textContent).toContain(en.report.nothing_body);
    expect(buttons.at(-1).classList.contains('report-anyway')).toBe(true);
  });

  it('in a browser says how to load a run from a terminal', () => {
    setActiveI18n(en);
    const prompt = nothingLoadedPrompt({ inVsCode: false, t });
    expect([...prompt.querySelectorAll('button[data-command]')]).toEqual([]);
    expect(prompt.textContent).toContain('epochix demo');
    expect(prompt.querySelector('.report-anyway')).not.toBeNull();
  });

  for (const [locale, cat] of Object.entries(CATALOGUES)) {
    it(`is in the reader's language (${locale})`, () => {
      setActiveI18n(cat);
      const prompt = nothingLoadedPrompt({ inVsCode: true, t });
      for (const key of ['nothing_title', 'nothing_body', 'anyway']) {
        expect(cat.report[key]).toBeTruthy();
        expect(prompt.textContent).toContain(cat.report[key]);
      }
    });
  }

  it('nothing in it is HTML from a translation', () => {
    // Built with textContent: a translation can never inject markup.
    setActiveI18n({ ...en, report: { ...en.report, nothing_title: '<img src=x onerror=alert(1)>' } });
    const prompt = nothingLoadedPrompt({ inVsCode: false, t });
    expect(prompt.querySelector('img')).toBeNull();
    expect(prompt.textContent).toContain('<img');
  });
});

describe('the report itself', () => {
  const base = { diag: '0.7.31 (vs code extension)', run: {}, frames: [] };

  it('with nothing loaded asks what the person was trying to do', () => {
    const body = dashboardReportBody({ ...base, hasRun: false });
    expect(body).toContain('### What were you trying to do?');
    expect(body).toContain('training output');
    expect(body).toContain('run loaded   no');
    expect(body).not.toContain('### What looks wrong?');
  });

  it('with a run asks what looks wrong, as before', () => {
    const frames = [{ primary_metric_value: 0.91, grade: 'A' }];
    const body = dashboardReportBody({
      ...base,
      hasRun: true,
      run: { primary_metric: 'val_accuracy', task_type: 'classification' },
      frames,
    });
    expect(body).toContain('### What looks wrong?');
    expect(body).toContain('run loaded   yes');
    expect(body).toContain('last value   0.91');
    expect(body).toContain('metric       val_accuracy');
  });

  it('never carries a run name or a path', () => {
    const body = dashboardReportBody({
      ...base,
      hasRun: true,
      run: { name: 'secret-project', primary_metric: 'loss' },
      frames: [{ primary_metric_value: 1 }],
    });
    expect(body).not.toContain('secret-project');
    expect(body).toContain('No run name, file path or log content is included');
  });
});
