/**
 * model-story Claude Artifact
 * ════════════════════════════════════════════════════════════════════════════
 * Single-file React artifact that parses ML training logs and renders an
 * animated storytelling dashboard — no Python backend required.
 *
 * Features
 *   • Drag-and-drop or paste any training log (PL / Keras / HF / YOLO / universal)
 *   • Animated BrainCanvas hero (Canvas 2D) with phase colours
 *   • Skill radar, line charts (recharts), grade card
 *   • Epoch scrubber — replay training history frame-by-frame
 *   • One-click HTML export (Blob URL, < 500 KB)
 *   • ?panel=hero|skills|engineer|timeline embed param
 *   • "pip install model-story" marketing banner after first parse
 *   • Optional LLM fallback via Claude API (set CLAUDE_API_KEY prop)
 *
 * Usage in an artifact:
 *   <ModelStoryArtifact />
 *   <ModelStoryArtifact panel="hero" />
 */

import React, {
  useState, useEffect, useRef, useCallback, useMemo, useReducer,
} from 'react';
import {
  LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, ResponsiveContainer, CartesianGrid, XAxis, YAxis,
  Tooltip, Legend,
} from 'recharts';

// ════════════════════════════════════════════════════════════════════════════
// SECTION 1 — PARSERS
// ════════════════════════════════════════════════════════════════════════════

const RE = {
  PL_HEADER:  /Epoch\s+(\d+)\/(\d+)/i,
  PL_METRIC:  /(\w+)=([\d.e+\-]+)/g,
  PL_BAR:     /Epoch\s+\d+\/\d+.*?[\]|].*?loss=/i,

  KERAS_EPOCH: /^Epoch\s+(\d+)\/(\d+)\s*$/i,
  KERAS_BAR:   /(\d+)\/(\d+)\s+\[.*?\]\s+-\s+(\d+)/,
  KERAS_KV:    /(\w+):\s*([\d.e+\-]+)/g,

  HF_DICT:    /\{[^}]+(?:'loss'|'eval_loss'|'epoch')[^}]+\}/,

  YOLO_TRAIN: /^\s+(\d+)\/(\d+)\s+([\d.]+G?)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)/,
  YOLO_VAL:   /all\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/,

  UNIV_KV_EQ:    /(\w[\w./-]*)=([\d.e+\-]+)/g,
  UNIV_KV_COLON: /(\w[\w./-]*)\s*:\s*([\d.e+\-]+)/g,
  ANSI:          /\x1b\[[0-9;]*m/g,
};

function stripAnsi(s) { return s.replace(RE.ANSI, ''); }

function parseFloat2(s) {
  const v = parseFloat(s);
  return isNaN(v) ? null : v;
}

// --- PyTorch Lightning Parser ---
function parsePL(line) {
  const clean = stripAnsi(line);
  if (!RE.PL_BAR.test(clean)) return null;
  const header = RE.PL_HEADER.exec(clean);
  const metrics = {};
  let m;
  RE.PL_METRIC.lastIndex = 0;
  while ((m = RE.PL_METRIC.exec(clean))) {
    const v = parseFloat2(m[2]);
    if (v !== null) metrics[m[1]] = v;
  }
  if (!Object.keys(metrics).length) return null;
  return {
    epoch: header ? parseInt(header[1], 10) : null,
    totalEpochs: header ? parseInt(header[2], 10) : null,
    metrics,
    parser: 'pytorch_lightning',
  };
}

function sniffPL(lines) {
  const hits = lines.filter(l => RE.PL_BAR.test(l)).length;
  return Math.min(hits / Math.max(lines.length, 1) * 4, 0.95);
}

// --- Keras Parser ---
let _kerasEpoch = null, _kerasTotalEpochs = null;
function parseKeras(line) {
  const clean = stripAnsi(line);
  const epochM = RE.KERAS_EPOCH.exec(clean);
  if (epochM) {
    _kerasEpoch = parseInt(epochM[1], 10);
    _kerasTotalEpochs = parseInt(epochM[2], 10);
    return null;
  }
  if (!RE.KERAS_BAR.test(clean)) return null;
  const metrics = {};
  let m;
  RE.KERAS_KV.lastIndex = 0;
  while ((m = RE.KERAS_KV.exec(clean))) {
    const v = parseFloat2(m[2]);
    if (v !== null) metrics[m[1]] = v;
  }
  if (!Object.keys(metrics).length) return null;
  return {
    epoch: _kerasEpoch,
    totalEpochs: _kerasTotalEpochs,
    metrics,
    parser: 'keras',
  };
}

function sniffKeras(lines) {
  const hits = lines.filter(l => RE.KERAS_EPOCH.test(l)).length;
  return Math.min(hits / Math.max(lines.length, 1) * 10, 0.95);
}

// --- HuggingFace Parser ---
function parseHF(line) {
  const clean = stripAnsi(line);
  if (!RE.HF_DICT.test(clean)) return null;
  try {
    const json = clean.trim().replace(/'/g, '"').replace(/(\w+):/g, '"$1":');
    const obj = JSON.parse(json);
    const metrics = {};
    for (const [k, v] of Object.entries(obj)) {
      const n = parseFloat2(String(v));
      if (n !== null) metrics[k] = n;
    }
    if (!Object.keys(metrics).length) return null;
    return {
      epoch: obj.epoch != null ? parseFloat2(String(obj.epoch)) : null,
      totalEpochs: null,
      metrics,
      parser: 'huggingface',
    };
  } catch { return null; }
}

function sniffHF(lines) {
  const hits = lines.filter(l => RE.HF_DICT.test(l)).length;
  return Math.min(hits / Math.max(lines.length, 1) * 5, 0.95);
}

// --- YOLO Parser ---
let _yoloEpoch = null, _yoloTotalEpochs = null;
function parseYOLO(line) {
  const clean = stripAnsi(line);
  const trainM = RE.YOLO_TRAIN.exec(clean);
  if (trainM) {
    _yoloEpoch = parseInt(trainM[1], 10);
    _yoloTotalEpochs = parseInt(trainM[2], 10);
    return {
      epoch: _yoloEpoch, totalEpochs: _yoloTotalEpochs,
      metrics: {
        box_loss: parseFloat2(trainM[4]),
        cls_loss: parseFloat2(trainM[5]),
        dfl_loss: parseFloat2(trainM[6]),
      },
      parser: 'yolo',
    };
  }
  const valM = RE.YOLO_VAL.exec(clean);
  if (valM) {
    return {
      epoch: _yoloEpoch, totalEpochs: _yoloTotalEpochs,
      metrics: {
        precision: parseFloat2(valM[1]),
        recall: parseFloat2(valM[2]),
        mAP50: parseFloat2(valM[3]),
        mAP50_95: parseFloat2(valM[4]),
      },
      parser: 'yolo',
    };
  }
  return null;
}

function sniffYOLO(lines) {
  const hits = lines.filter(l => RE.YOLO_TRAIN.test(l) || RE.YOLO_VAL.test(l)).length;
  return Math.min(hits / Math.max(lines.length, 1) * 5, 0.95);
}

// --- Universal Parser ---
function parseUniversal(line) {
  const clean = stripAnsi(line);
  const metrics = {};

  // Try JSON-fragment first
  try {
    const jsonM = /\{[^}]{5,200}\}/.exec(clean);
    if (jsonM) {
      const obj = JSON.parse(jsonM[0].replace(/'/g, '"').replace(/(\w+):/g, '"$1":'));
      for (const [k, v] of Object.entries(obj)) {
        const n = parseFloat2(String(v));
        if (n !== null) metrics[k] = n;
      }
    }
  } catch { /* ignore */ }

  // key=value
  let m;
  RE.UNIV_KV_EQ.lastIndex = 0;
  while ((m = RE.UNIV_KV_EQ.exec(clean))) {
    const v = parseFloat2(m[2]);
    if (v !== null) metrics[m[1]] = v;
  }

  // key: value (only if no = hits to avoid duplicates)
  if (!Object.keys(metrics).length) {
    RE.UNIV_KV_COLON.lastIndex = 0;
    while ((m = RE.UNIV_KV_COLON.exec(clean))) {
      const v = parseFloat2(m[2]);
      if (v !== null) metrics[m[1]] = v;
    }
  }

  // Epoch hint from line
  const epochM = /[Ee]poch\s+(\d+)(?:\/(\d+))?/.exec(clean);

  if (!Object.keys(metrics).length) return null;
  return {
    epoch: epochM ? parseInt(epochM[1], 10) : null,
    totalEpochs: epochM && epochM[2] ? parseInt(epochM[2], 10) : null,
    metrics,
    parser: 'universal',
  };
}

// --- Parser auto-selection ---
const PARSERS = [
  { sniff: sniffPL,     parse: parsePL,     name: 'pytorch_lightning' },
  { sniff: sniffKeras,  parse: parseKeras,  name: 'keras' },
  { sniff: sniffHF,     parse: parseHF,     name: 'huggingface' },
  { sniff: sniffYOLO,   parse: parseYOLO,   name: 'yolo' },
];

function selectParser(lines) {
  let best = null, bestScore = 0;
  for (const p of PARSERS) {
    const score = p.sniff(lines.slice(0, 50));
    if (score > bestScore) { bestScore = score; best = p; }
  }
  return bestScore >= 0.25 ? best : { parse: parseUniversal, name: 'universal' };
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 2 — CANONICAL KEY NORMALISATION
// ════════════════════════════════════════════════════════════════════════════

const CANONICAL = {
  acc: 'val_accuracy', accuracy: 'val_accuracy', val_acc: 'val_accuracy',
  val_accuracy: 'val_accuracy', train_accuracy: 'train_accuracy',
  loss: 'train_loss', train_loss: 'train_loss', val_loss: 'val_loss',
  eval_loss: 'val_loss', mAP50: 'mAP50', map50: 'mAP50',
  lr: 'lr', learning_rate: 'lr', epoch: 'epoch',
  perplexity: 'perplexity', f1: 'f1', precision: 'precision', recall: 'recall',
  mAP50_95: 'mAP50_95',
};

function canonicalise(raw) {
  return CANONICAL[raw] || raw;
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 3 — STORY ENGINE
// ════════════════════════════════════════════════════════════════════════════

// --- Task detection ---
const TASK_KEYS = {
  classification: ['val_accuracy', 'train_accuracy', 'accuracy'],
  detection:      ['mAP50', 'mAP50_95', 'box_loss', 'cls_loss'],
  nlp:            ['perplexity', 'bleu', 'eval_loss'],
  regression:     ['MAE', 'MSE', 'RMSE'],
  generative:     ['fid', 'inception_score'],
};

function detectTask(metricKeys) {
  const keySet = new Set(metricKeys);
  let best = 'classification', bestHits = 0;
  for (const [task, keys] of Object.entries(TASK_KEYS)) {
    const hits = keys.filter(k => keySet.has(k)).length;
    if (hits > bestHits) { bestHits = hits; best = task; }
  }
  return best;
}

// --- Primary metric per task ---
const PRIMARY_METRIC = {
  classification: 'val_accuracy',
  detection:      'mAP50',
  nlp:            'perplexity',
  regression:     'MAE',
  generative:     'fid',
};

// --- Phase ---
const PHASES = ['awakening', 'learning', 'understanding', 'mastering', 'polishing'];
const PHASE_EMOJI = {
  awakening: '🌱', learning: '📚', understanding: '💡',
  mastering: '🎯', polishing: '✨',
};
const PHASE_COLOR = {
  awakening: '#6366f1', learning: '#3b82f6', understanding: '#10b981',
  mastering: '#f59e0b', polishing: '#ec4899',
};

function computePhase(progress, primaryValue, baseline, target) {
  const relImprove = target > baseline
    ? (primaryValue - baseline) / (target - baseline)
    : 0;
  const combined = progress * 0.6 + relImprove * 0.4;
  if (combined < 0.10) return 'awakening';
  if (combined < 0.30) return 'learning';
  if (combined < 0.60) return 'understanding';
  if (combined < 0.85) return 'mastering';
  return 'polishing';
}

// --- Grade ---
const GRADE_THRESHOLDS = {
  classification: [
    ['A+', 0.95], ['A', 0.90], ['A-', 0.87], ['B+', 0.82], ['B', 0.75],
    ['B-', 0.70], ['C+', 0.65], ['C', 0.60], ['C-', 0.55], ['D', 0.50], ['F', 0],
  ],
  detection: [
    ['A+', 0.75], ['A', 0.65], ['A-', 0.58], ['B+', 0.50], ['B', 0.42],
    ['B-', 0.35], ['C+', 0.28], ['C', 0.20], ['C-', 0.15], ['D', 0.08], ['F', 0],
  ],
  nlp: [
    ['A+', 10], ['A', 20], ['A-', 30], ['B+', 50], ['B', 80],
    ['B-', 120], ['C+', 180], ['C', 250], ['C-', 350], ['D', 500], ['F', Infinity],
  ],
};
GRADE_THRESHOLDS.regression = GRADE_THRESHOLDS.nlp;
GRADE_THRESHOLDS.generative = GRADE_THRESHOLDS.nlp;

const LOWER_BETTER = new Set(['nlp', 'regression', 'generative']);

function computeGrade(task, value) {
  const thresholds = GRADE_THRESHOLDS[task] || GRADE_THRESHOLDS.classification;
  const lower = LOWER_BETTER.has(task);
  for (const [grade, threshold] of thresholds) {
    if (lower ? value <= threshold : value >= threshold) return grade;
  }
  return 'F';
}

const GRADE_COLOR = {
  'A+': '#10b981', A: '#22c55e', 'A-': '#84cc16',
  'B+': '#eab308', B: '#f59e0b', 'B-': '#f97316',
  'C+': '#ef4444', C: '#dc2626', 'C-': '#b91c1c',
  D: '#7f1d1d', F: '#450a0a', I: '#6b7280',
};

// --- Narrative templates ---
const NARRATIVES = {
  'classification/awakening': [
    'The model stirs, beginning to discern patterns in epoch {epoch}. Accuracy: {value_pct}.',
    'First neurons fire. The training journey begins at {value_pct} accuracy.',
  ],
  'classification/learning': [
    'Gradients flow, features sharpen. Accuracy climbs to {value_pct} at epoch {epoch}.',
    'The model is learning the language of its data. {delta} delta this epoch.',
  ],
  'classification/understanding': [
    'Deep representations form. Accuracy {value_pct} — the model grasps the task.',
    'At epoch {epoch}, generalisation improves. Accuracy: {value_pct}.',
  ],
  'classification/mastering': [
    'Near-expert performance at {value_pct}. The model masters its domain.',
    'Epoch {epoch}: fine boundaries sharpen. Accuracy {value_pct}.',
  ],
  'classification/polishing': [
    'Polishing to {value_pct}. Final refinements bring the model to peak form.',
    'The model is ready. {value_pct} accuracy — exceptional work.',
  ],
  'detection/learning': [
    'Anchors adjust, boxes tighten. mAP50: {value_pct} at epoch {epoch}.',
  ],
  'detection/mastering': [
    'Objects snap into focus. mAP50 reaches {value_pct}.',
  ],
  'nlp/learning': [
    'Perplexity falls to {value}. The language model finds its footing.',
  ],
  'nlp/mastering': [
    'Fluency emerges. Perplexity {value} — the model speaks clearly.',
  ],
};

function djb2(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  return h;
}

function narrate(task, phase, epoch, value, delta, runId) {
  const key = `${task}/${phase}`;
  const templates = NARRATIVES[key] || NARRATIVES[`classification/${phase}`] || [
    `Training in phase ${phase}. Value: ${value.toFixed(4)}.`,
  ];
  const idx = djb2(runId) % templates.length;
  const epochStr = epoch != null ? String(Math.round(epoch)) : '?';
  const deltaStr = delta !== 0 ? (delta > 0 ? `+${delta.toFixed(4)}` : delta.toFixed(4)) : '0';
  return templates[idx]
    .replace('{epoch}', epochStr)
    .replace('{value}', value.toFixed(4))
    .replace('{value_pct}', `${(value * 100).toFixed(1)}%`)
    .replace('{delta}', deltaStr);
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 4 — LOG PROCESSING
// ════════════════════════════════════════════════════════════════════════════

function processLog(rawText) {
  // Reset stateful parsers
  _kerasEpoch = null; _kerasTotalEpochs = null;
  _yoloEpoch = null; _yoloTotalEpochs = null;

  const lines = rawText.split('\n');
  const parser = selectParser(lines);

  const rawEvents = [];
  for (const line of lines) {
    const result = parser.parse(line);
    if (!result) continue;
    for (const [k, v] of Object.entries(result.metrics)) {
      if (v == null) continue;
      rawEvents.push({
        epoch: result.epoch,
        totalEpochs: result.totalEpochs,
        key: canonicalise(k),
        rawKey: k,
        value: v,
        parser: result.parser,
      });
    }
  }

  if (!rawEvents.length) return null;

  // Detect task and primary metric
  const allKeys = [...new Set(rawEvents.map(e => e.key))];
  const task = detectTask(allKeys);
  const primaryKey = PRIMARY_METRIC[task] || allKeys[0];

  // Group by epoch for frames
  const byEpoch = new Map();
  let maxEpoch = 0;
  let totalEpochs = null;
  for (const ev of rawEvents) {
    if (ev.epoch == null) continue;
    maxEpoch = Math.max(maxEpoch, ev.epoch);
    if (ev.totalEpochs) totalEpochs = ev.totalEpochs;
    if (!byEpoch.has(ev.epoch)) byEpoch.set(ev.epoch, {});
    byEpoch.get(ev.epoch)[ev.key] = ev.value;
  }

  const sortedEpochs = [...byEpoch.keys()].sort((a, b) => a - b);
  const runId = `run-${Date.now().toString(36)}`;
  const frames = [];
  let baseline = null;
  let prevPrimary = null;

  for (const epoch of sortedEpochs) {
    const epochData = byEpoch.get(epoch);
    const primaryValue = epochData[primaryKey];
    if (primaryValue == null) continue;

    if (baseline == null) baseline = primaryValue;
    const progress = totalEpochs
      ? Math.min(epoch / totalEpochs, 1.0)
      : Math.min(epoch / Math.max(maxEpoch, 1), 1.0);

    const target = LOWER_BETTER.has(task) ? baseline * 0.1 : 1.0;
    const phase = computePhase(progress, primaryValue, baseline, target);
    const grade = computeGrade(task, primaryValue);
    const delta = prevPrimary != null ? primaryValue - prevPrimary : 0;
    const narrative = narrate(task, phase, epoch, primaryValue, delta, runId);

    frames.push({
      epoch, progress, phase, grade, primaryValue, narrative,
      metrics: epochData,
      delta,
    });

    prevPrimary = primaryValue;
  }

  // Chart data (line chart)
  const chartData = frames.map(f => ({
    epoch: f.epoch,
    ...f.metrics,
  }));

  // Skill dimensions (radar) — last frame
  const lastFrame = frames[frames.length - 1];
  const skillData = lastFrame ? [
    { axis: 'Accuracy',       value: lastFrame.metrics.val_accuracy || lastFrame.metrics.accuracy || 0 },
    { axis: 'Generalisation', value: lastFrame.metrics.val_loss ? Math.max(0, 1 - lastFrame.metrics.val_loss) : 0.5 },
    { axis: 'Fitting',        value: lastFrame.metrics.train_loss ? Math.max(0, 1 - lastFrame.metrics.train_loss) : 0.5 },
    { axis: 'Stability',      value: Math.max(0, 1 - Math.abs(lastFrame.delta) * 5) },
    { axis: 'Progress',       value: lastFrame.progress },
  ] : [];

  // Milestones
  const milestones = [];
  if (frames.length > 0) {
    milestones.push({ kind: 'first_metric', epoch: frames[0].epoch, message: 'Training began' });
    const bestIdx = frames.reduce((best, f, i) =>
      (LOWER_BETTER.has(task) ? f.primaryValue < frames[best].primaryValue : f.primaryValue > frames[best].primaryValue) ? i : best,
      0);
    milestones.push({
      kind: 'best_metric',
      epoch: frames[bestIdx].epoch,
      message: `Best ${primaryKey}: ${frames[bestIdx].primaryValue.toFixed(4)}`,
    });
  }

  return {
    runId, task, parser: parser.name, primaryKey,
    totalEpochs, maxEpoch,
    frames, chartData, skillData, milestones,
    allKeys,
    finalGrade: lastFrame ? lastFrame.grade : 'I',
    finalPhase: lastFrame ? lastFrame.phase : 'awakening',
    finalNarrative: lastFrame ? lastFrame.narrative : '',
  };
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 5 — VISUALISATION COMPONENTS
// ════════════════════════════════════════════════════════════════════════════

// --- BrainCanvas (Canvas 2D animated hero) ---
function BrainCanvas({ phase, grade, progress }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const CX = W / 2, CY = H / 2;

    // Nodes for the neural network diagram
    const layers = [3, 5, 5, 3];
    const nodes = [];
    const layerX = [0.18, 0.38, 0.62, 0.82];
    for (let li = 0; li < layers.length; li++) {
      const count = layers[li];
      for (let ni = 0; ni < count; ni++) {
        nodes.push({
          x: layerX[li] * W,
          y: ((ni + 1) / (count + 1)) * H,
          layer: li,
          activation: Math.random(),
          pulseOffset: Math.random() * Math.PI * 2,
        });
      }
    }

    let t = 0;
    function draw() {
      const ph = phaseRef.current;
      const col = PHASE_COLOR[ph] || '#6366f1';

      ctx.clearRect(0, 0, W, H);

      // Background gradient
      const grad = ctx.createRadialGradient(CX, CY, 10, CX, CY, CX);
      grad.addColorStop(0, col + '22');
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);

      // Progress arc
      ctx.beginPath();
      ctx.arc(CX, CY, CX * 0.88, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
      ctx.strokeStyle = col + 'aa';
      ctx.lineWidth = 3;
      ctx.stroke();

      // Connections
      const layerMap = [[], [], [], []];
      for (const n of nodes) layerMap[n.layer].push(n);

      for (let li = 0; li < layers.length - 1; li++) {
        for (const src of layerMap[li]) {
          for (const dst of layerMap[li + 1]) {
            const pulse = (Math.sin(t * 0.05 + src.pulseOffset) + 1) / 2;
            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            ctx.lineTo(dst.x, dst.y);
            ctx.strokeStyle = col + Math.floor(pulse * 60 + 20).toString(16).padStart(2, '0');
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }

      // Nodes
      for (const n of nodes) {
        const pulse = (Math.sin(t * 0.04 + n.pulseOffset) + 1) / 2;
        const r = 5 + pulse * 4 * progress;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.globalAlpha = 0.4 + pulse * 0.5;
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      // Grade text in centre
      ctx.font = `bold ${W * 0.12}px monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = GRADE_COLOR[grade] || '#fff';
      ctx.fillText(grade || 'I', CX, CY);

      t++;
      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [progress]);

  return (
    <canvas
      ref={canvasRef}
      width={280}
      height={280}
      style={{ borderRadius: '50%', background: '#0f0f1a' }}
    />
  );
}

// --- Grade Card ---
function GradeCard({ grade, phase, narrative }) {
  const col = GRADE_COLOR[grade] || '#6b7280';
  return (
    <div style={{
      background: `linear-gradient(135deg, ${col}22 0%, #1e1e2e 100%)`,
      border: `1px solid ${col}55`,
      borderRadius: 16,
      padding: '20px 24px',
      minHeight: 120,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
        <span style={{
          fontSize: 48, fontWeight: 900, color: col,
          fontFamily: 'monospace', lineHeight: 1,
        }}>{grade || '?'}</span>
        <div>
          <div style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 1 }}>
            {PHASE_EMOJI[phase]} {phase}
          </div>
          <div style={{ fontSize: 14, color: '#ccc', marginTop: 4 }}>Current Grade</div>
        </div>
      </div>
      <p style={{ fontSize: 14, color: '#aaa', margin: 0, lineHeight: 1.6 }}>{narrative}</p>
    </div>
  );
}

// --- Skill Radar ---
function SkillRadar({ data }) {
  if (!data || !data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart data={data}>
        <PolarGrid stroke="#333" />
        <PolarAngleAxis dataKey="axis" tick={{ fill: '#888', fontSize: 12 }} />
        <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
        <Radar dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.35} />
        <Tooltip formatter={(v) => v.toFixed(3)} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// --- Line Charts ---
function MetricCharts({ chartData, allKeys }) {
  const lossKeys = allKeys.filter(k => k.includes('loss'));
  const accKeys = allKeys.filter(k => k.includes('acc') || k.includes('mAP') || k.includes('f1'));
  const otherKeys = allKeys.filter(k => !lossKeys.includes(k) && !accKeys.includes(k) && k !== 'epoch');

  const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#3b82f6', '#ef4444'];

  function Chart({ keys, title }) {
    if (!keys.length) return null;
    return (
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: '#666', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>{title}</div>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#222" />
            <XAxis dataKey="epoch" tick={{ fill: '#666', fontSize: 11 }} />
            <YAxis tick={{ fill: '#666', fontSize: 11 }} />
            <Tooltip contentStyle={{ background: '#1e1e2e', border: '1px solid #333', borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {keys.map((k, i) => (
              <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]}
                dot={false} strokeWidth={2} name={k} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div>
      <Chart keys={lossKeys} title="Loss" />
      <Chart keys={accKeys} title="Performance" />
      {otherKeys.length > 0 && <Chart keys={otherKeys.slice(0, 3)} title="Other Metrics" />}
    </div>
  );
}

// --- Timeline ---
function Timeline({ frames, milestones, scrubIdx }) {
  const displayFrames = frames.filter((_, i) => i <= scrubIdx);
  const shown = displayFrames.slice(-4);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {milestones.map((ms, i) => (
        <div key={i} style={{
          background: '#1a1a2e', border: '1px solid #333',
          borderRadius: 10, padding: '10px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 20 }}>🏆</span>
          <div>
            <div style={{ fontSize: 12, color: '#888' }}>Epoch {ms.epoch}</div>
            <div style={{ fontSize: 14, color: '#ccc' }}>{ms.message}</div>
          </div>
        </div>
      ))}
      {shown.map((f, i) => (
        <div key={i} style={{
          background: PHASE_COLOR[f.phase] + '11',
          border: `1px solid ${PHASE_COLOR[f.phase]}44`,
          borderRadius: 10, padding: '12px 16px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 13, color: '#888' }}>
              {PHASE_EMOJI[f.phase]} Epoch {f.epoch}
            </span>
            <span style={{
              fontSize: 13, fontWeight: 700,
              color: GRADE_COLOR[f.grade] || '#888',
            }}>{f.grade}</span>
          </div>
          <p style={{ fontSize: 13, color: '#bbb', margin: 0, lineHeight: 1.5 }}>{f.narrative}</p>
        </div>
      ))}
    </div>
  );
}

// --- Marketing Banner ---
function MarketingBanner() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div style={{
      background: 'linear-gradient(135deg, #6366f122 0%, #10b98122 100%)',
      border: '1px solid #6366f155',
      borderRadius: 12, padding: '16px 20px',
      display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <span style={{ fontSize: 28 }}>⚡</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 600, marginBottom: 4 }}>
          Get the full model-story experience
        </div>
        <code style={{
          background: '#0f0f1a', padding: '4px 10px', borderRadius: 6,
          fontSize: 13, color: '#10b981',
        }}>pip install model-story</code>
        <span style={{ fontSize: 13, color: '#666', marginLeft: 12 }}>
          Live dashboard · VS Code extension · PDF export
        </span>
      </div>
      <button
        onClick={() => setDismissed(true)}
        style={{
          background: 'none', border: 'none', color: '#555',
          cursor: 'pointer', fontSize: 18, padding: 4,
        }}
      >×</button>
    </div>
  );
}

// --- Drop Zone ---
function DropZone({ onFile }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handle = useCallback((file) => {
    const reader = new FileReader();
    reader.onload = e => onFile(e.target.result, file.name);
    reader.readAsText(file);
  }, [onFile]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault(); setDragging(false);
        const f = e.dataTransfer.files[0];
        if (f) handle(f);
      }}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? '#6366f1' : '#333'}`,
        borderRadius: 16,
        padding: '48px 24px',
        textAlign: 'center',
        cursor: 'pointer',
        transition: 'border-color 0.2s',
        background: dragging ? '#6366f108' : 'transparent',
      }}
    >
      <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
      <div style={{ fontSize: 16, color: '#ccc', marginBottom: 8 }}>
        Drop a training log here
      </div>
      <div style={{ fontSize: 13, color: '#555' }}>
        .log, .txt — PyTorch Lightning, Keras, HuggingFace, YOLO, or any format
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".log,.txt"
        style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) handle(f); }}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 6 — EXPORT
// ════════════════════════════════════════════════════════════════════════════

function buildExportHtml(run, rawText) {
  const summaryJson = JSON.stringify({
    task: run.task,
    parser: run.parser,
    totalEpochs: run.maxEpoch,
    finalGrade: run.finalGrade,
    finalPhase: run.finalPhase,
    narrative: run.finalNarrative,
    milestones: run.milestones,
  }, null, 2);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>model-story Training Report</title>
<style>
  body{margin:0;background:#0a0a14;color:#e2e8f0;font-family:system-ui,sans-serif;padding:32px}
  h1{color:#6366f1;margin-bottom:4px}
  .grade{font-size:64px;font-weight:900;color:${GRADE_COLOR[run.finalGrade]}}
  .phase{font-size:14px;color:#888;text-transform:uppercase;letter-spacing:1px}
  .narrative{font-size:16px;color:#aaa;max-width:600px;line-height:1.7;margin:16px 0}
  .milestones{list-style:none;padding:0}
  .milestones li{background:#1e1e2e;border:1px solid #333;border-radius:8px;
    padding:10px 16px;margin-bottom:8px;font-size:14px;color:#ccc}
  pre{background:#1e1e2e;padding:16px;border-radius:8px;overflow:auto;
    font-size:12px;color:#888;border:1px solid #222}
  .badge{display:inline-block;background:#6366f122;border:1px solid #6366f155;
    padding:4px 12px;border-radius:20px;font-size:12px;color:#6366f1;margin-right:8px}
</style>
</head>
<body>
<h1>⚡ model-story Training Report</h1>
<span class="badge">${run.task}</span>
<span class="badge">${run.parser}</span>
<span class="badge">${run.maxEpoch} epochs</span>
<div style="margin-top:24px">
  <div class="grade">${run.finalGrade}</div>
  <div class="phase">${PHASE_EMOJI[run.finalPhase]} ${run.finalPhase}</div>
  <div class="narrative">${run.finalNarrative}</div>
</div>
<h2 style="color:#888;font-size:14px;text-transform:uppercase;letter-spacing:1px">Milestones</h2>
<ul class="milestones">
${run.milestones.map(m => `  <li>🏆 Epoch ${m.epoch} — ${m.message}</li>`).join('\n')}
</ul>
<h2 style="color:#888;font-size:14px;text-transform:uppercase;letter-spacing:1px;margin-top:32px">Summary JSON</h2>
<pre>${summaryJson}</pre>
<p style="font-size:12px;color:#444;margin-top:32px">
  Generated by <a href="https://github.com/hexorax/model-story" style="color:#6366f1">model-story</a> &bull;
  <code>pip install model-story</code>
</p>
</body>
</html>`;
}

// ════════════════════════════════════════════════════════════════════════════
// SECTION 7 — MAIN APP
// ════════════════════════════════════════════════════════════════════════════

const TABS = ['hero', 'timeline', 'skills', 'engineer'];
const TAB_LABELS = { hero: '🧠 Hero', timeline: '📖 Story', skills: '🕸 Skills', engineer: '📊 Charts' };

export default function ModelStoryArtifact({ panel = null, apiKey = null }) {
  const urlPanel = useMemo(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('panel');
    }
    return null;
  }, []);

  const forcePanel = panel || urlPanel;

  const [activeTab, setActiveTab] = useState(forcePanel || 'hero');
  const [run, setRun] = useState(null);
  const [rawText, setRawText] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [showPaste, setShowPaste] = useState(false);
  const [scrubIdx, setScrubIdx] = useState(0);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const handleLog = useCallback((text, filename = 'log') => {
    setError(null);
    const result = processLog(text);
    if (!result || !result.frames.length) {
      setError('No training metrics found. Try a different log file or paste format.');
      return;
    }
    setRun(result);
    setRawText(text);
    setScrubIdx(result.frames.length - 1);
    setActiveTab(forcePanel || 'hero');
  }, [forcePanel]);

  const handleExport = useCallback(() => {
    if (!run) return;
    setExporting(true);
    try {
      const html = buildExportHtml(run, rawText);
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `model-story-report-${run.runId}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [run, rawText]);

  const currentFrame = run?.frames[scrubIdx];

  return (
    <div style={{
      background: '#0a0a14',
      minHeight: '100vh',
      color: '#e2e8f0',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: 0,
    }}>
      {/* Header */}
      {!forcePanel && (
        <div style={{
          background: '#0f0f1a',
          borderBottom: '1px solid #1e1e2e',
          padding: '14px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 22 }}>⚡</span>
            <span style={{ fontSize: 17, fontWeight: 700, color: '#e2e8f0' }}>model-story</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {run && (
              <button
                onClick={handleExport}
                disabled={exporting}
                style={{
                  background: '#1e1e2e', border: '1px solid #333',
                  color: '#888', padding: '6px 14px',
                  borderRadius: 8, cursor: 'pointer', fontSize: 13,
                }}
              >
                {exporting ? '…' : '↓ Export HTML'}
              </button>
            )}
            <button
              onClick={() => setShowPaste(p => !p)}
              style={{
                background: '#1e1e2e', border: '1px solid #333',
                color: '#888', padding: '6px 14px',
                borderRadius: 8, cursor: 'pointer', fontSize: 13,
              }}
            >
              📋 Paste log
            </button>
          </div>
        </div>
      )}

      <div style={{ padding: forcePanel ? 0 : '24px', maxWidth: 960, margin: '0 auto' }}>
        {/* Paste input */}
        {showPaste && !forcePanel && (
          <div style={{ marginBottom: 20 }}>
            <textarea
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              placeholder="Paste your training log here…"
              style={{
                width: '100%', minHeight: 140, background: '#1e1e2e',
                border: '1px solid #333', borderRadius: 10, color: '#ccc',
                padding: 12, fontSize: 12, fontFamily: 'monospace',
                boxSizing: 'border-box', resize: 'vertical',
              }}
            />
            <button
              onClick={() => { if (pasteText.trim()) handleLog(pasteText, 'pasted'); setShowPaste(false); }}
              style={{
                marginTop: 8, background: '#6366f1', border: 'none',
                color: '#fff', padding: '8px 20px', borderRadius: 8,
                cursor: 'pointer', fontSize: 14,
              }}
            >Parse →</button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: '#ef444422', border: '1px solid #ef444455',
            borderRadius: 10, padding: '12px 16px', marginBottom: 20,
            color: '#fca5a5', fontSize: 14,
          }}>{error}</div>
        )}

        {/* No run yet — drop zone */}
        {!run && (
          <div style={{ maxWidth: 520, margin: '60px auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <div style={{ fontSize: 56, marginBottom: 12 }}>⚡</div>
              <h2 style={{ color: '#e2e8f0', margin: 0, fontSize: 22 }}>
                Visual storytelling for ML training
              </h2>
              <p style={{ color: '#666', marginTop: 8, fontSize: 14 }}>
                Drop any training log and watch your model's journey unfold
              </p>
            </div>
            <DropZone onFile={handleLog} />
          </div>
        )}

        {/* Run loaded */}
        {run && (
          <>
            {/* Info strip */}
            {!forcePanel && (
              <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                {[
                  { label: 'Task', value: run.task },
                  { label: 'Parser', value: run.parser },
                  { label: 'Epochs', value: run.maxEpoch },
                  { label: 'Grade', value: run.finalGrade },
                ].map(({ label, value }) => (
                  <div key={label} style={{
                    background: '#1e1e2e', border: '1px solid #2a2a3e',
                    borderRadius: 8, padding: '8px 16px',
                  }}>
                    <div style={{ fontSize: 11, color: '#555', marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0' }}>{value}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Tabs */}
            {!forcePanel && (
              <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #1e1e2e', paddingBottom: 4 }}>
                {TABS.map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    style={{
                      background: activeTab === tab ? '#6366f122' : 'none',
                      border: activeTab === tab ? '1px solid #6366f155' : '1px solid transparent',
                      color: activeTab === tab ? '#e2e8f0' : '#555',
                      padding: '7px 16px', borderRadius: 8, cursor: 'pointer',
                      fontSize: 13,
                    }}
                  >{TAB_LABELS[tab]}</button>
                ))}
              </div>
            )}

            {/* Scrubber */}
            {run.frames.length > 1 && (activeTab === 'hero' || forcePanel === 'hero') && (
              <div style={{ marginBottom: 20 }}>
                <input
                  type="range" min={0} max={run.frames.length - 1} value={scrubIdx}
                  onChange={e => setScrubIdx(Number(e.target.value))}
                  style={{ width: '100%', accentColor: '#6366f1' }}
                />
                <div style={{ fontSize: 12, color: '#555', textAlign: 'center', marginTop: 4 }}>
                  Epoch {currentFrame?.epoch} / {run.maxEpoch}
                </div>
              </div>
            )}

            {/* Hero tab */}
            {(activeTab === 'hero' || forcePanel === 'hero') && currentFrame && (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                gap: 24, alignItems: 'start',
                flexWrap: 'wrap',
              }}>
                <BrainCanvas
                  phase={currentFrame.phase}
                  grade={currentFrame.grade}
                  progress={currentFrame.progress}
                />
                <div>
                  <GradeCard
                    grade={currentFrame.grade}
                    phase={currentFrame.phase}
                    narrative={currentFrame.narrative}
                  />
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#444', marginBottom: 6 }}>
                      Progress
                    </div>
                    <div style={{ background: '#1e1e2e', borderRadius: 8, height: 8, overflow: 'hidden' }}>
                      <div style={{
                        width: `${currentFrame.progress * 100}%`,
                        height: '100%',
                        background: PHASE_COLOR[currentFrame.phase],
                        transition: 'width 0.3s ease',
                      }} />
                    </div>
                    <div style={{ fontSize: 11, color: '#444', marginTop: 4 }}>
                      {(currentFrame.progress * 100).toFixed(0)}% through training
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Timeline tab */}
            {(activeTab === 'timeline' || forcePanel === 'timeline') && (
              <Timeline frames={run.frames} milestones={run.milestones} scrubIdx={scrubIdx} />
            )}

            {/* Skills tab */}
            {(activeTab === 'skills' || forcePanel === 'skills') && (
              <div>
                <div style={{ fontSize: 14, color: '#888', marginBottom: 16 }}>
                  Skill dimensions — last epoch snapshot
                </div>
                <SkillRadar data={run.skillData} />
              </div>
            )}

            {/* Engineer tab */}
            {(activeTab === 'engineer' || forcePanel === 'engineer') && (
              <MetricCharts chartData={run.chartData} allKeys={run.allKeys} />
            )}

            {/* Marketing banner */}
            {!forcePanel && (
              <div style={{ marginTop: 32 }}>
                <MarketingBanner />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
