/**
 * Model architecture from a training log, for the standalone engine.
 *
 * The Python package has parsed model summaries since early on, but the
 * extension's built-in engine never did — so with no Python installed (or in an
 * untrusted folder) the Network State panel always read "no architecture to
 * display", including on our own bundled demo, whose log starts with a Keras
 * summary. The demo command's comment even claimed the panel "lights up".
 *
 * Covers the two formats people actually paste into a log: Keras
 * `model.summary()` and a plain torch `print(model)` module repr. The layer
 * labels, the trivial-layer list and the layer cap are generated from
 * parsers/architecture_parser.py; the `print(model)` answers are pinned by
 * src/test/fixtures/architecture.golden.json, which Python writes.
 */

import {
  ARCH_FALLBACK,
  ARCH_MAX_LAYERS,
  ARCH_REPR_CONTAINERS,
  ARCH_TRIVIAL,
  ARCH_TYPE_MAP,
} from "./engineTables.generated";

/** One layer, shaped exactly like the Python `ArchLayer.to_dict()`. */
export interface ArchLayer {
  idx: number;
  name: string;
  layer_type: string;
  params: number;
  params_str: string;
  tech_label: string;
  plain_label: string;
  visual_type: "conv" | "dense" | "recurrent" | "attention" | "norm" | "generic";
}

/** Python's `_norm`: lower-cased, without spaces, dashes or underscores. */
function norm(layerType: string): string {
  return layerType.toLowerCase().replace(/[ _-]/g, "");
}

function classify(layerType: string): Pick<
  ArchLayer,
  "tech_label" | "plain_label" | "visual_type"
> {
  const key = norm(layerType);
  for (const [needle, [tech, plain, visual]] of ARCH_TYPE_MAP) {
    if (key.includes(needle)) {
      return { tech_label: tech, plain_label: plain, visual_type: visual as ArchLayer["visual_type"] };
    }
  }
  const [tech, plain, visual] = ARCH_FALLBACK;
  return { tech_label: tech, plain_label: plain, visual_type: visual as ArchLayer["visual_type"] };
}

/** "23.5 M" / "2.1 K" / "25,728" -> integer. Empty string means "unknown". */
export function parseParams(raw: string): number {
  const s = raw.trim().toUpperCase().replace(/,/g, "").replace(/\s/g, "");
  if (!s) return 0;
  const mult: [string, number][] = [
    ["B", 1e9],
    ["G", 1e9],
    ["M", 1e6],
    ["K", 1e3],
  ];
  for (const [suffix, factor] of mult) {
    if (s.endsWith(suffix)) {
      const n = Number.parseFloat(s.slice(0, -1));
      if (Number.isFinite(n)) return Math.round(n * factor);
    }
  }
  const n = Number.parseFloat(s);
  return Number.isFinite(n) ? Math.round(n) : 0;
}

function makeLayer(
  idx: number,
  name: string,
  layerType: string,
  paramsStr: string,
): ArchLayer {
  return {
    idx,
    name,
    layer_type: layerType,
    params: parseParams(paramsStr),
    params_str: paramsStr.trim(),
    ...classify(layerType),
  };
}

// ── Keras model.summary() ────────────────────────────────────────────────────
// ` conv2d (Conv2D)             (None, 30, 30, 32)        896`
// The "(Type)" column is optional: Keras omits it for layers whose name
// already is the type (`max_pooling2d`), and dropping those rows lost a layer.
const KERAS_ROW = /^[\s|│]*([\w./-]+)\s*(?:\(([\w.]+)\))?\s{2,}(.*)$/;
const KERAS_END = /^[=_─]{3,}|Total params|Trainable params/i;

function parseKeras(lines: string[]): ArchLayer[] {
  const out: ArchLayer[] = [];
  let started = false;
  for (const raw of lines) {
    if (/Layer\s*\(type\)/i.test(raw)) {
      started = true;
      continue;
    }
    if (!started) continue;
    if (KERAS_END.test(raw.trim()) && out.length) break;
    const m = KERAS_ROW.exec(raw);
    if (!m) continue;
    // Trailing numbers on the row; the last one is the parameter count.
    // Require a shape-ish column so prose lines cannot masquerade as rows.
    if (!/\(|\d/.test(m[3])) continue;
    const nums = m[3].match(/[\d,]+/g);
    out.push(
      makeLayer(out.length, m[1], m[2] ?? m[1], nums ? nums[nums.length - 1] : "0"),
    );
  }
  return out;
}

// ── torch print(model) ───────────────────────────────────────────────────────
// A child at any depth:  `  (encoder): ResNet(`  /  `    (0): BasicBlock(`, and
// PyTorch's folded repeats:  `    (0-3): 4 x TransformerEncoderLayer(`
const REPR_CHILD = /^( {1,32})\(([\w.-]{1,64})\):\s*(?:\d{1,6} x )?([A-Za-z][\w.]{0,64})\s*\(/;
const REPR_OPEN = /^[A-Za-z][\w.]*\s*\(\s*$/;

/**
 * Top-level modules of a `print(model)` dump, containers opened one level.
 *
 * Any child indented two to four spaces used to count, so a torchvision
 * ResNet-18 listed its stages *and* the blocks inside them. Only the first
 * child's depth is the top level; a `Sequential` there is replaced by its own
 * children — a stem, eight BasicBlocks, a classifier.
 */
function parseModuleRepr(lines: string[]): ArchLayer[] {
  const out: ArchLayer[] = [];
  let seenOpen = false;
  let top: number | null = null;
  let container: [string, number] | null = null;
  for (const raw of lines) {
    if (!seenOpen) {
      if (REPR_OPEN.test(raw.trim())) seenOpen = true;
      continue;
    }
    const m = REPR_CHILD.exec(raw);
    if (!m) continue;
    const indent = m[1].length;
    let name = m[2];
    let type = m[3];
    if (top === null) {
      if (indent > 4) continue;
      top = indent;
    }
    if (indent === top) {
      container = null;
      if (ARCH_REPR_CONTAINERS.has(type.toLowerCase()) && raw.trimEnd().endsWith("(")) {
        container = [name, indent];
        continue;
      }
    } else if (container !== null && indent === container[1] + 2) {
      name = `${container[0]}.${name}`;
    } else {
      continue; // inside a module: its parts, not the model's
    }
    if (/bidirectional=true/i.test(raw) && /^(lstm|gru|rnn)$/i.test(type)) {
      type = `Bi${type}`;
    }
    // A repr carries no parameter counts, and an invented 0 would be a false
    // claim — the Python side derives them from the layer's own shapes; here we
    // report the count as unknown rather than guess.
    out.push(makeLayer(out.length, name, type, ""));
  }
  return out;
}

/** Python's round(): halves go to the even neighbour. */
function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/** Python's `_clean`: drop trivial layers (unless that empties it), then cap
 *  the count by keeping evenly spaced layers, first and last included. */
function clean(layers: ArchLayer[]): ArchLayer[] {
  if (!layers.length) return layers;
  const filtered = layers.filter((l) => !ARCH_TRIVIAL.some((k) => norm(l.layer_type).includes(k)));
  let kept = filtered.length ? filtered : layers;
  if (kept.length > ARCH_MAX_LAYERS) {
    const n = kept.length;
    const k = ARCH_MAX_LAYERS;
    const idxs = [...new Set(Array.from({ length: k }, (_, i) => pyRound((i * (n - 1)) / (k - 1))))]
      .sort((a, b) => a - b);
    kept = idxs.map((i) => kept[i]);
  }
  return kept.map((l, i) => ({ ...l, idx: i }));
}

/** Best-effort architecture from log lines; empty when nothing is recognised.
 *  Like Python, the richer of the two readings wins. */
export function parseArchitecture(lines: string[]): ArchLayer[] {
  const keras = clean(parseKeras(lines));
  const repr = clean(parseModuleRepr(lines));
  return repr.length > keras.length ? repr : keras;
}
