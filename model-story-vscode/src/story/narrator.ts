/**
 * TypeScript port of src/model_story/story_engine/narrator.py
 *
 * Uses embedded template strings rather than file I/O (no file system
 * access in the standalone VS Code extension mode).
 */
import type { Phase } from "./phases";
import type { TaskType } from "./grader";

// ── Template library ──────────────────────────────────────────────────────────
// Each key is "taskType/phase" → array of template strings.

const TEMPLATES: Record<string, string[]> = {
  "classification/awakening": [
    "The model is seeing its first examples. Everything looks the same to it.",
    "At epoch {epoch}, the model has just opened its eyes. It cannot yet tell the difference between classes.",
    "The journey begins. The model is overwhelmed by what it sees, scoring just {value_pct}.",
  ],
  "classification/learning": [
    "Patterns are starting to click. The easy cases are falling into place. Accuracy is now {value_pct}.",
    "The model is building its vocabulary of patterns. It now recognises the straightforward examples.",
    "At epoch {epoch}, the most obvious differences between classes are becoming clear. Score: {value_pct}.",
  ],
  "classification/understanding": [
    "The model is beginning to see beyond the obvious. Subtler distinctions are emerging. Score: {value_pct}.",
    "Hard examples are no longer all wrong. The model is developing a real understanding at epoch {epoch}.",
    "Accuracy has reached {value_pct}. The model has moved from memorising to generalising.",
  ],
  "classification/mastering": [
    "The model is performing at a high level — {value_pct} accuracy. Only the trickiest cases remain.",
    "At epoch {epoch}, nearly every example is classified correctly. The model is polishing the edges.",
    "Mastery is close. Accuracy of {value_pct} puts this model in solid territory.",
  ],
  "classification/polishing": [
    "The model has reached expert level: {value_pct} accuracy. Fine-tuning is all that remains.",
    "At epoch {epoch}, the model is making micro-adjustments. It has essentially solved the task.",
    "Peak performance: {value_pct}. The model is as good as this training run can make it.",
  ],

  "detection/awakening": [
    "The model can tell something is there, but not what or exactly where. mAP: {value_pct}.",
    "At epoch {epoch}, the detector is just beginning to localise objects. Most boxes are far off target.",
  ],
  "detection/learning": [
    "Rough bounding boxes are appearing. The model is beginning to guess at object locations.",
    "At epoch {epoch}, the detector has found {value_pct} mAP. Objects are starting to take shape.",
  ],
  "detection/understanding": [
    "Boxes are tightening. The model understands where most objects live. mAP: {value_pct}.",
    "At epoch {epoch}, the detector can locate and classify common objects reliably.",
  ],
  "detection/mastering": [
    "The detector achieves {value_pct} mAP. Difficult, overlapping objects are being handled.",
    "At epoch {epoch}, the model is producing tight, accurate boxes across nearly all classes.",
  ],
  "detection/polishing": [
    "Detection performance has plateaued at {value_pct} mAP — this is excellent.",
    "Epoch {epoch}: the detector is polishing the hardest edge cases.",
  ],

  "regression/awakening": [
    "Predictions are scattered. The model has not yet found the signal in epoch {epoch}.",
    "Error is high at {value}. The model is essentially guessing.",
  ],
  "regression/learning": [
    "Error has dropped to {value}. The model is picking up the main trend.",
    "At epoch {epoch}, the regression curve is starting to converge.",
  ],
  "regression/understanding": [
    "The model understands the core relationship. Error is now {value}.",
    "Non-linear patterns are emerging. Epoch {epoch} shows solid progress.",
  ],
  "regression/mastering": [
    "Predictions are close. Error of {value} puts this model in strong territory.",
    "At epoch {epoch}, the model is fitting complex structure well.",
  ],
  "regression/polishing": [
    "Fine-grained adjustment. Error is down to {value} — near the noise floor.",
    "Epoch {epoch}: tiny residual errors are being squeezed out.",
  ],

  "nlp/awakening": [
    "The language model is learning its first words. Perplexity is very high at {value}.",
    "At epoch {epoch}, every sentence still surprises the model.",
  ],
  "nlp/learning": [
    "Common phrases are no longer surprising. Rare ones still are. Perplexity: {value}.",
    "The model is building a working vocabulary of likely word sequences.",
  ],
  "nlp/understanding": [
    "The model grasps context and common idioms. Perplexity: {value}.",
    "At epoch {epoch}, long-range dependencies are beginning to be captured.",
  ],
  "nlp/mastering": [
    "Language fluency is high — perplexity down to {value}. Rare constructions are handled.",
    "Epoch {epoch}: the model generates coherent, contextually appropriate language.",
  ],
  "nlp/polishing": [
    "Near-human fluency. Perplexity of {value} is remarkable.",
    "Epoch {epoch}: the model is a skilled writer. Fine-tuning is all that remains.",
  ],

  "biometric/awakening": [
    "The biometric system cannot yet distinguish users. EER: {value}.",
    "At epoch {epoch}, the model sees everyone as the same.",
  ],
  "biometric/learning": [
    "Broad identity clusters are forming. EER has dropped to {value}.",
    "The model begins to tell users apart at a coarse level.",
  ],
  "biometric/understanding": [
    "Most users are reliably distinguished. EER: {value}.",
    "At epoch {epoch}, fine-grained identity features are being learned.",
  ],
  "biometric/mastering": [
    "The biometric system is highly accurate with an EER of {value}.",
    "Epoch {epoch}: even similar-looking users are correctly separated.",
  ],
  "biometric/polishing": [
    "Exceptional biometric accuracy — EER of {value}. Production-ready.",
    "Epoch {epoch}: final edge cases are being resolved.",
  ],

  "gaze/awakening": [
    "The gaze estimator is pointing in random directions. MAE: {value}°.",
    "At epoch {epoch}, no reliable gaze signal has been found yet.",
  ],
  "gaze/learning": [
    "Rough gaze direction is detected. MAE is now {value}°.",
    "The model understands the general direction the eye is pointing.",
  ],
  "gaze/understanding": [
    "Gaze estimation is becoming useful. MAE: {value}°.",
    "At epoch {epoch}, fixation zones can be reliably predicted.",
  ],
  "gaze/mastering": [
    "Precise gaze estimation — MAE of {value}° is impressive.",
    "Epoch {epoch}: fine-grained gaze patterns are being captured.",
  ],
  "gaze/polishing": [
    "Near-perfect gaze estimation. MAE: {value}°. This is research-grade accuracy.",
    "Epoch {epoch}: residual errors are in the sub-degree range.",
  ],

  "generative/awakening": [
    "The generator produces noise. Creativity has not yet emerged.",
    "At epoch {epoch}, every output looks the same.",
  ],
  "generative/learning": [
    "Rough structure is appearing in the outputs. The generator is learning the data distribution.",
    "Epoch {epoch}: basic patterns are taking shape.",
  ],
  "generative/understanding": [
    "Generated samples are recognisable. The model understands the domain.",
    "At epoch {epoch}, diversity and quality are both improving.",
  ],
  "generative/mastering": [
    "High-quality generation. Most outputs would pass casual inspection.",
    "Epoch {epoch}: the generator has mastered the core patterns.",
  ],
  "generative/polishing": [
    "State-of-the-art generation quality. Fine details are being perfected.",
    "Epoch {epoch}: the generative model is producing exceptional samples.",
  ],

  "custom/awakening": [
    "Training has begun. The model is processing its first examples at epoch {epoch}.",
  ],
  "custom/learning": [
    "The model is making progress. Metric: {value} at epoch {epoch}.",
  ],
  "custom/understanding": [
    "Good progress. The model has learned the main patterns. Value: {value}.",
  ],
  "custom/mastering": [
    "Strong performance. Metric value {value} at epoch {epoch}.",
  ],
  "custom/polishing": [
    "Excellent results. The model is being fine-tuned at epoch {epoch}.",
  ],
};

// ── Deterministic selection ───────────────────────────────────────────────────

/** Simple hash → index, matching the Python md5-based selection. */
function pickIndex(runId: string, n: number): number {
  // djb2 hash of the run ID
  let h = 5381;
  for (let i = 0; i < runId.length; i++) {
    h = ((h * 33) ^ runId.charCodeAt(i)) >>> 0;
  }
  return h % n;
}

// ── Public API ────────────────────────────────────────────────────────────────

export interface NarrateOptions {
  task: TaskType;
  phase: Phase;
  epoch: number | null;
  primaryValue: number;
  delta: number;
  runId: string;
}

export function narrate(opts: NarrateOptions): string {
  const key = `${opts.task}/${opts.phase}`;
  const templates = TEMPLATES[key] ?? TEMPLATES[`custom/${opts.phase}`] ?? [
    `Training in progress (epoch ${opts.epoch ?? "?"}).`,
  ];

  const template = templates[pickIndex(opts.runId, templates.length)];

  const epochStr = opts.epoch !== null ? String(Math.round(opts.epoch)) : "?";
  const valuePct = `${(opts.primaryValue * 100).toFixed(1)}%`;
  const deltaStr = opts.delta !== 0 ? (opts.delta >= 0 ? "+" : "") + opts.delta.toFixed(4) : "0";

  return template
    .replace(/\{epoch\}/g, epochStr)
    .replace(/\{value\}/g, opts.primaryValue.toFixed(4))
    .replace(/\{delta\}/g, deltaStr)
    .replace(/\{value_pct\}/g, valuePct);
}
