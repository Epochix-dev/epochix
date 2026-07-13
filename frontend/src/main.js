/**
 * main.js — application bootstrap.
 *
 * Responsibilities:
 *  1. Import CSS (base + active theme)
 *  2. Read locale from URL / localStorage
 *  3. Detect run mode: export (inline JSON) vs live (fetch + WS)
 *  4. Fetch snapshot → populate store
 *  5. Open WebSocket (or SSE fallback) for live runs
 *  6. Mount panels
 *  7. Wire up header controls (theme toggle, export button)
 */

import './themes/dark.css';
import './themes/light.css';
import './themes/base.css';

import { store, pushFrame }                from './store.js';
import { connect, disconnect }              from './ws-client.js';
import { connectSSE, disconnectSSE }        from './sse-client.js';
import { HeroPanel }                        from './panels/HeroPanel.js';
import { JourneyPanel }                     from './panels/JourneyPanel.js';
import { SkillsPanel }                      from './panels/SkillsPanel.js';
import { TechPanel }                        from './panels/TechPanel.js';
import { TrainingDiagnostics }              from './visualizations/TrainingDiagnostics.js';
import { PhaseJourney }                     from './visualizations/PhaseJourney.js';
import { CompareView }                      from './visualizations/CompareView.js';
import { Distributions }                    from './visualizations/Distributions.js';
import { Educational }                       from './visualizations/Educational.js';

// ── i18n ─────────────────────────────────────────────────────────────────────

import en from './i18n/en.json';
import fa from './i18n/fa.json';
import fr from './i18n/fr.json';
import { applyStaticI18n } from './i18n/apply.js';

const LOCALES = { en, fa, fr };

function loadI18n(locale) {
  return LOCALES[locale] ?? LOCALES.en;
}

// ── utilities ─────────────────────────────────────────────────────────────────

function getRunId() {
  // /v/<run_id> or /v/<run_id>/embed
  const m = location.pathname.match(/\/v\/([^/]+)/);
  return m ? m[1] : null;
}

function getParam(name) {
  return new URLSearchParams(location.search).get(name);
}

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = `toast${type ? ` ${type}` : ''}`;
  el.textContent = msg;
  document.getElementById('toasts')?.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── theme ─────────────────────────────────────────────────────────────────────

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('ms-theme', theme);
  store.set({ theme });
}

function initTheme() {
  const saved  = localStorage.getItem('ms-theme');
  const system = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  const param  = getParam('theme');
  applyTheme(param ?? saved ?? system);
}

// ── connection status UI ──────────────────────────────────────────────────────

store.subscribe((s) => {
  const dot = document.getElementById('connection-dot');
  if (!dot) return;
  dot.className = `connection-dot${s.connected ? ' live' : s.live ? ' error' : ''}`;
  dot.title     = s.connected ? 'Live' : s.live ? 'Reconnecting…' : 'Offline';
});

// ── export mode detection ─────────────────────────────────────────────────────

function readInlineRunData() {
  const el = document.getElementById('run-data');
  if (!el || !el.textContent.trim()) return null;
  try {
    return JSON.parse(el.textContent);
  } catch {
    return null;
  }
}

// ── snapshot fetch ────────────────────────────────────────────────────────────

async function fetchSnapshot(runId) {
  const [snapRes, metricsRes] = await Promise.all([
    fetch(`/api/snapshot/${runId}`),
    fetch(`/api/metrics/${runId}`),
  ]);

  if (!snapRes.ok) throw new Error(`Snapshot ${snapRes.status}`);

  const { frames = [], run = null } = await snapRes.json();
  const metrics = metricsRes.ok ? (await metricsRes.json()).events ?? [] : [];

  return { frames, run, metrics };
}

async function fetchRunMeta(runId) {
  const r = await fetch(`/api/runs/${runId}`);
  if (!r.ok) return null;
  return (await r.json()).run ?? null;
}

// ── WS with SSE fallback ──────────────────────────────────────────────────────

function openLiveStream(runId, lastSeq) {
  if ('WebSocket' in window) {
    connect(runId, lastSeq);
  } else {
    connectSSE(runId, lastSeq);
  }
}

// ── main ──────────────────────────────────────────────────────────────────────

async function main() {
  initTheme();

  const locale = getParam('locale') ?? localStorage.getItem('ms-locale') ?? 'en';
  const i18n   = loadI18n(locale);
  store.set({ locale });
  applyStaticI18n(i18n, locale);  // localise chrome + set text direction (RTL for fa)

  // Mount panels early so they show skeleton state
  const hero    = new HeroPanel(store);
  const journey = new JourneyPanel(store, i18n);
  const skills  = new SkillsPanel(store);
  const tech    = new TechPanel(store);

  hero.mount();
  journey.mount();
  skills.mount();
  tech.mount();   // async but non-blocking

  // New dashboards: phase-journey ribbon + interpreted diagnostics
  const phaseJourneyEl = document.getElementById('phase-journey');
  if (phaseJourneyEl) new PhaseJourney(phaseJourneyEl).mount(store);

  const diagnosticsEl = document.getElementById('training-diagnostics');
  if (diagnosticsEl) new TrainingDiagnostics(diagnosticsEl).mount(store);

  const distributionsEl = document.getElementById('distributions');
  if (distributionsEl) new Distributions(distributionsEl).mount(store);

  const educationalEl = document.getElementById('educational');
  if (educationalEl) new Educational(educationalEl).mount(store);

  // Sidebar navigation (smooth scroll to section + scrollspy)
  setupSidebarNav();

  // Honour a #section deep-link once canvases have settled (their late resize
  // shifts offsets, so the browser's initial hash scroll undershoots).
  if (location.hash) {
    const target = document.getElementById(location.hash.slice(1));
    if (target) setTimeout(() => target.scrollIntoView({ block: 'start' }), 600);
  }

  // ── header controls ────────────────────────────────────────────────────────

  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const cur = store.get().theme;
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });

  document.getElementById('export-btn')?.addEventListener('click', () => {
    const runId = getRunId();
    if (runId) window.open(`/api/export/${runId}/json`, '_blank');
  });

  // ── data loading ───────────────────────────────────────────────────────────

  // Case 0: VS Code standalone webview — data arrives via postMessage, not HTTP.
  if (window.__EPOCHIX_VSCODE__) {
    const { startVscodeBridge } = await import('./vscode-bridge.js');
    if (startVscodeBridge(applyTheme)) return;
  }

  // Case 1: Export mode — run data is inlined in the HTML
  const inline = readInlineRunData();
  if (inline) {
    const { run, frames = [], events = [] } = inline;
    store.set({ run, metrics: events, live: false });
    for (const f of frames) pushFrame(f);
    return; // no WS needed
  }

  // Case 2: Multi-run comparison view
  if (location.pathname === '/compare') {
    await showCompare();
    return;
  }

  // Case 3: Live / batch view — load from API
  const runId = getRunId();
  if (!runId) {
    // Landing page — show run list
    await showRunList();
    return;
  }

  try {
    const { frames, run, metrics } = await fetchSnapshot(runId);
    const lastSeq = frames.length > 0 ? (frames.at(-1).seq ?? frames.length - 1) : -1;

    // Architecture and the latest activation snapshot are stored in run.config
    // by the pipeline / LiveReporter, so a run opened mid/after training still
    // shows real values before any live WS message arrives.
    const architecture = run?.config?.architecture ?? null;
    const activations = run?.config?.activations ?? null;
    store.set({ run, metrics, architecture, activations });
    for (const f of frames) pushFrame(f);

    // If run is not finished, open live stream
    const isLive = !run?.finished_at;
    if (isLive) {
      store.set({ live: true });
      openLiveStream(runId, lastSeq);
    }
  } catch (err) {
    console.error('[main] failed to load run:', err);
    toast(`Failed to load run: ${err.message}`, 'error');
  }

  // Handle page unload
  window.addEventListener('beforeunload', () => {
    disconnect();
    disconnectSSE();
  });
}

// ── sidebar navigation ─────────────────────────────────────────────────────────

function setupSidebarNav() {
  const nav     = document.getElementById('sidebar-nav');
  const body    = document.getElementById('app-body');
  if (!nav || !body) return;

  const items = [...nav.querySelectorAll('.nav-item[data-target]')];

  // Click → smooth-scroll the section to the top of the scroll container.
  for (const item of items) {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const id = item.dataset.target;
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // Scrollspy → highlight the section nearest the top.
  const targets = items
    .map((it) => ({ item: it, el: document.getElementById(it.dataset.target) }))
    .filter((t) => t.el);

  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const top = body.scrollTop;
      let active = targets[0];
      for (const t of targets) {
        if (t.el.offsetTop - 120 <= top) active = t;
      }
      for (const t of targets) t.item.classList.toggle('is-active', t === active);
      ticking = false;
    });
  };
  body.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

// ── multi-run comparison view ───────────────────────────────────────────────────

async function showCompare() {
  _adaptShellForLanding();
  const title = document.getElementById('run-name');
  if (title) title.textContent = 'Compare runs';

  const ids = (getParam('runs') ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  const sub = document.querySelector('.greet-sub');
  if (sub) sub.textContent = ids.length ? `${ids.length} runs` : 'Pick runs to compare';

  const main = document.getElementById('app-main');
  if (!main) return;
  main.innerHTML = `
    <section class="compare-row">
      <div class="panel panel-compare">
        <div class="panel-label">Run Comparison
          <span class="panel-label-sub">overlay metrics across runs · click a run to toggle it</span>
        </div>
        <div id="compare-view"></div>
      </div>
    </section>`;

  const el = document.getElementById('compare-view');
  if (!el) return;
  if (ids.length === 0) {
    el.innerHTML = `<div class="cmp-loading">Select runs from the
      <a href="/">runs list</a> and click “Compare”.</div>`;
    return;
  }
  await new CompareView(el).load(ids);
}

// ── run list (landing page) ───────────────────────────────────────────────────

/** Adapt the sidebar/topbar for the landing (no single run loaded). */
function _adaptShellForLanding() {
  const title = document.getElementById('run-name');
  if (title) title.textContent = 'Training Runs';

  // Section nav items don't apply on the landing page — hide them, highlight "All runs".
  document.querySelectorAll('.nav-item[data-target]').forEach((el) => {
    el.style.display = 'none';
    el.classList.remove('is-active');
  });
  const allRuns = [...document.querySelectorAll('.nav-item')]
    .find((el) => el.getAttribute('href') === '/');
  if (allRuns) allRuns.classList.add('is-active');

  // The grade summary card is run-specific — hide it on the landing.
  const foot = document.getElementById('sidebar-foot');
  if (foot) foot.style.display = 'none';
}

async function showRunList() {
  const main = document.getElementById('app-main');
  if (!main) return;

  _adaptShellForLanding();

  main.innerHTML = `
    <div class="run-list-wrap">
      <div id="run-list" class="run-grid">
        <div class="run-list-loading">Loading…</div>
      </div>
    </div>
    <div class="compare-bar" id="compare-bar" hidden>
      <span class="cb-count">0 selected</span>
      <button class="cb-go" id="compare-go">Compare →</button>
    </div>
  `;

  try {
    const r = await fetch('/api/runs?limit=50');
    if (!r.ok) throw new Error(`${r.status}`);
    const { runs = [] } = await r.json();

    const listEl = document.getElementById('run-list');
    if (!listEl) return;

    // Update greeting count
    const sub = document.querySelector('.greet-sub');
    if (sub) sub.textContent = runs.length
      ? `${runs.length} model run${runs.length !== 1 ? 's' : ''}`
      : 'All your model runs';

    if (runs.length === 0) {
      listEl.classList.remove('run-grid');
      listEl.innerHTML = `
        <div class="run-list-empty">
          No training runs yet.<br>
          Run <code>epochix &lt;log.txt&gt;</code> to get started.
        </div>`;
      return;
    }

    listEl.innerHTML = runs.map((run) => {
      const grade    = run.final_grade ?? '—';
      const gradeKey = String(grade).replace('+', '-plus').replace('-', '-minus').toLowerCase();
      const name     = run.name ?? run.id.slice(0, 12);
      const task     = run.task_type ?? 'custom';
      const finished = !!run.finished_at;
      const date     = finished
        ? new Date(run.finished_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
        : 'In progress';
      return `
        <div class="run-card" style="--g: var(--grade-${gradeKey}, var(--accent-primary))">
          <input type="checkbox" class="run-pick" data-id="${_esc(run.id)}"
                 title="Select to compare" aria-label="Select ${_esc(name)} to compare">
          <a class="run-open" href="/v/${run.id}">
            <span class="rc-grade">${_esc(grade)}</span>
            <div class="rc-body">
              <div class="rc-name">${_esc(name)}</div>
              <div class="rc-meta">
                <span class="rc-chip">${_esc(task)}</span>
                <span class="${finished ? '' : 'rc-live'}">${_esc(date)}</span>
              </div>
            </div>
            <span class="rc-arrow">→</span>
          </a>
        </div>
      `;
    }).join('');

    _wireCompareSelection(listEl);

  } catch (err) {
    document.getElementById('run-list').innerHTML =
      `<div class="run-list-empty">Could not load runs: ${_esc(err.message)}</div>`;
  }
}

/** Wire run-card checkboxes → the sticky "Compare" bar. */
function _wireCompareSelection(listEl) {
  const selected = new Set();
  const bar   = document.getElementById('compare-bar');
  const count = bar?.querySelector('.cb-count');
  const go    = document.getElementById('compare-go');

  listEl.querySelectorAll('.run-pick').forEach((cb) => {
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(cb.dataset.id);
      else selected.delete(cb.dataset.id);
      const n = selected.size;
      if (count) count.textContent = `${n} selected`;
      if (bar) bar.hidden = n < 2;
    });
  });
  go?.addEventListener('click', () => {
    if (selected.size >= 2) {
      window.location.href = `/compare?runs=${[...selected].join(',')}`;
    }
  });
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── kick off ──────────────────────────────────────────────────────────────────
main().catch((err) => {
  console.error('[main] unhandled error:', err);
  toast(`Unexpected error: ${err.message}`, 'error');
});
