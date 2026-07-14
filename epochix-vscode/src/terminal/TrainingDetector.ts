/**
 * Heuristic detector: does a block of terminal output look like an ML training run?
 *
 * Returns a 0.0–1.0 confidence score.  The extension opens the dashboard when
 * the score exceeds OPEN_THRESHOLD.
 */

const OPEN_THRESHOLD = 0.45;

// Strong signals — any one of these is probably ML training
const STRONG_PATTERNS: RegExp[] = [
  /Epoch\s+\d+\/\d+/,                           // PyTorch Lightning / Keras
  /\{'?loss'?\s*:/,                              // HuggingFace JSON row
  /^\s*\d+\/\d+\s+[\d.]+[GMK]?\s+[\d.]+/m,      // YOLO training row
  /train_loss\s+valid_loss/,                     // FastAI header
  /\bepoch\b.*\bloss\b/i,                        // generic "epoch … loss"
  /Training epoch/i,
  /Step\s+\d+.*loss=/i,
];

// Supporting signals — need several of these
const SOFT_PATTERNS: RegExp[] = [
  /loss\s*[=:]\s*[\d.e+-]+/i,
  /accuracy\s*[=:]\s*[\d.]+/i,
  /val_loss|val_acc|eval_loss/i,
  /learning_rate|lr\s*[=:]/i,
  /\d+\/\d+\s+\[=+/,                             // Keras progress bar
  /mAP|precision|recall/i,
  /perplexity/i,
  /EER|equal.error/i,
];

/** Strip ANSI colour codes from terminal output. */
export function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1b\[[0-9;]*[mGKHFJ]/g, "");
}

/**
 * Sniff a tail of terminal output for ML training signals.
 *
 * @param text  Last N characters of terminal output (4096 bytes is fine).
 * @returns     0.0–1.0 confidence score.
 */
export function sniff(text: string): number {
  const clean = stripAnsi(text);

  // Any strong signal → high confidence
  for (const pat of STRONG_PATTERNS) {
    if (pat.test(clean)) return 0.90;
  }

  // Count soft signals.
  //
  // Scored in integers and scaled at the end: `soft * 0.15` drifts in IEEE
  // (3 * 0.15 === 0.4499999999999999), so a log with exactly three soft signals
  // — loss=, accuracy=, val_loss, which is a completely ordinary key=value
  // training log — landed a hair UNDER the 0.45 threshold and the dashboard
  // never opened. It silently took four signals to trigger.
  const soft = SOFT_PATTERNS.filter((p) => p.test(clean)).length;
  return Math.min(soft * 15, 80) / 100;
}

/** Return true if the text looks like ML training (above threshold). */
export function isTraining(text: string): boolean {
  return sniff(text) >= OPEN_THRESHOLD;
}
