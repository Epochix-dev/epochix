/**
 * SkillRadar.js — D3-based radar / spider chart for skill_dimensions.
 *
 * Uses only d3-path and d3-scale to keep the bundle small. Path morphs
 * smoothly between epochs via CSS transitions on SVG paths.
 */

const SIZE = 200;
const MARGIN = 40;
const R = (SIZE - MARGIN * 2) / 2;
const CX = SIZE / 2;
const CY = SIZE / 2;

const ACCENT = getComputedStyle(document.documentElement)
  .getPropertyValue('--accent-primary').trim() || '#7c6dff';

export class SkillRadar {
  /** @param {HTMLCanvasElement|HTMLElement} container */
  constructor(container) {
    this._container = container;
    this._svg = null;
    this._dataPath = null;
    this._unsub = null;
    this._currentSkills = {};
    this._axes = [];
    this._build();
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const skills = s.currentFrame?.skill_dimensions ?? null;
      if (skills) this._update(skills);
    });
    const s = store.get();
    if (s.currentFrame?.skill_dimensions) {
      this._update(s.currentFrame.skill_dimensions);
    }
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _build() {
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${SIZE} ${SIZE}`);
    svg.style.width  = '100%';
    svg.style.height = '100%';

    // Vibrant gradient fill for the data area (matches the reference donuts)
    const defs = document.createElementNS(svgNS, 'defs');
    const grad = document.createElementNS(svgNS, 'radialGradient');
    grad.setAttribute('id', 'radar-grad');
    grad.setAttribute('cx', '50%');
    grad.setAttribute('cy', '50%');
    grad.setAttribute('r', '65%');
    const stops = [
      ['0%',   '#22d3ee', 0.55],
      ['45%',  '#7c6dff', 0.45],
      ['100%', '#f472b6', 0.30],
    ];
    for (const [off, col, op] of stops) {
      const s = document.createElementNS(svgNS, 'stop');
      s.setAttribute('offset', off);
      s.setAttribute('stop-color', col);
      s.setAttribute('stop-opacity', String(op));
      grad.appendChild(s);
    }
    defs.appendChild(grad);
    // Stroke gradient (linear, cool→warm)
    const lgrad = document.createElementNS(svgNS, 'linearGradient');
    lgrad.setAttribute('id', 'radar-stroke');
    lgrad.setAttribute('x1', '0%'); lgrad.setAttribute('y1', '0%');
    lgrad.setAttribute('x2', '100%'); lgrad.setAttribute('y2', '100%');
    for (const [off, col] of [['0%', '#22d3ee'], ['50%', '#7c6dff'], ['100%', '#f472b6']]) {
      const s = document.createElementNS(svgNS, 'stop');
      s.setAttribute('offset', off);
      s.setAttribute('stop-color', col);
      lgrad.appendChild(s);
    }
    defs.appendChild(lgrad);
    svg.appendChild(defs);

    // Background rings
    for (let level = 1; level <= 4; level++) {
      const r = (level / 4) * R;
      const ring = document.createElementNS(svgNS, 'circle');
      ring.setAttribute('cx', CX);
      ring.setAttribute('cy', CY);
      ring.setAttribute('r', r);
      ring.setAttribute('fill', 'none');
      ring.setAttribute('stroke', 'currentColor');
      ring.setAttribute('stroke-opacity', '0.08');
      ring.setAttribute('stroke-width', '1');
      svg.appendChild(ring);
    }

    // Data area
    this._dataPath = document.createElementNS(svgNS, 'path');
    this._dataPath.setAttribute('fill', 'url(#radar-grad)');
    this._dataPath.setAttribute('stroke', 'url(#radar-stroke)');
    this._dataPath.setAttribute('stroke-width', '2');
    this._dataPath.setAttribute('stroke-linejoin', 'round');
    this._dataPath.style.transition = 'd 400ms ease';
    svg.appendChild(this._dataPath);

    // Labels group
    this._labelsG = document.createElementNS(svgNS, 'g');
    svg.appendChild(this._labelsG);

    this._svg = svg;
    this._container.appendChild(svg);
  }

  /** @param {Record<string, number>} skills */
  _update(skills) {
    const keys = Object.keys(skills);
    if (keys.length === 0) return;

    const svgNS = 'http://www.w3.org/2000/svg';
    const n = keys.length;

    // Re-render axis labels when axes change
    if (JSON.stringify(keys) !== JSON.stringify(this._axes)) {
      this._axes = keys;
      this._labelsG.innerHTML = '';
      keys.forEach((key, i) => {
        const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
        const lx = CX + (R + 16) * Math.cos(angle);
        const ly = CY + (R + 16) * Math.sin(angle);

        // Axis line
        const line = document.createElementNS(svgNS, 'line');
        line.setAttribute('x1', CX);
        line.setAttribute('y1', CY);
        line.setAttribute('x2', CX + R * Math.cos(angle));
        line.setAttribute('y2', CY + R * Math.sin(angle));
        line.setAttribute('stroke', 'currentColor');
        line.setAttribute('stroke-opacity', '0.15');
        line.setAttribute('stroke-width', '1');
        this._labelsG.appendChild(line);

        // Label
        const txt = document.createElementNS(svgNS, 'text');
        txt.setAttribute('x', lx);
        txt.setAttribute('y', ly + 4);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('font-size', '9');
        txt.setAttribute('fill', 'currentColor');
        txt.setAttribute('opacity', '0.5');
        txt.textContent = key.replace(/_/g, ' ').slice(0, 10);
        this._labelsG.appendChild(txt);
      });
    }

    // Build polygon path
    let d = '';
    keys.forEach((key, i) => {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      const v = Math.max(0, Math.min(1, skills[key] ?? 0));
      const x = CX + R * v * Math.cos(angle);
      const y = CY + R * v * Math.sin(angle);
      d += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
    });
    d += ' Z';

    this._dataPath.setAttribute('d', d);
    this._currentSkills = skills;
  }
}
