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
 * `model.summary()` and a plain torch `print(model)` module repr.
 */

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

const MAX_LAYERS = 24;

/** Ordered most-specific first; matched as a substring of the lowered type. */
const TYPE_MAP: [string, [string, string, ArchLayer["visual_type"]]][] = [
  ["convtranspose", ["UPCONV", "Upsampler", "conv"]],
  ["separableconv", ["CONV", "Spatial patterns", "conv"]],
  ["depthwiseconv", ["CONV", "Spatial patterns", "conv"]],
  ["conv3d", ["CONV", "Volumetric patterns", "conv"]],
  ["conv2d", ["CONV", "Spatial patterns", "conv"]],
  ["conv1d", ["CONV", "Sequence patterns", "conv"]],
  ["conv", ["CONV", "Pattern finder", "conv"]],
  ["bilstm", ["MEMORY", "Bi-directional memory", "recurrent"]],
  ["lstm", ["MEMORY", "Remembers context", "recurrent"]],
  ["gru", ["MEMORY", "Remembers context", "recurrent"]],
  ["rnn", ["MEMORY", "Sequence memory", "recurrent"]],
  ["multiheadattention", ["FOCUS", "Multi-head attention", "attention"]],
  ["attention", ["FOCUS", "Reads full context", "attention"]],
  ["transformer", ["FOCUS", "Transformer", "attention"]],
  ["embedding", ["EMBED", "Turns tokens into vectors", "dense"]],
  ["batchnorm", ["NORM", "Keeps signals stable", "norm"]],
  ["layernorm", ["NORM", "Keeps signals stable", "norm"]],
  ["groupnorm", ["NORM", "Keeps signals stable", "norm"]],
  ["instancenorm", ["NORM", "Keeps signals stable", "norm"]],
  ["normalization", ["NORM", "Keeps signals stable", "norm"]],
  ["maxpool", ["POOL", "Keeps the strongest signal", "norm"]],
  ["avgpool", ["POOL", "Averages the signal", "norm"]],
  ["pooling", ["POOL", "Shrinks the picture", "norm"]],
  ["dropout", ["DROP", "Prevents memorising", "norm"]],
  ["flatten", ["SHAPE", "Reshapes the data", "generic"]],
  ["linear", ["DENSE", "Combines everything", "dense"]],
  ["dense", ["DENSE", "Combines everything", "dense"]],
];

function classify(layerType: string): Pick<
  ArchLayer,
  "tech_label" | "plain_label" | "visual_type"
> {
  const key = layerType.toLowerCase().replace(/[\s_-]/g, "");
  for (const [needle, [tech, plain, visual]] of TYPE_MAP) {
    if (key.includes(needle)) {
      return { tech_label: tech, plain_label: plain, visual_type: visual };
    }
  }
  return { tech_label: "LAYER", plain_label: "Processing step", visual_type: "generic" };
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
    if (out.length >= MAX_LAYERS) break;
  }
  return out;
}

// ── torch print(model) ───────────────────────────────────────────────────────
// `  (0): Conv2d(1, 32, kernel_size=(3, 3), stride=(1, 1))`
const REPR_CHILD = /^\s{2,4}\(([\w.]+)\):\s*([A-Za-z][\w.]*)\s*\(/;
const REPR_OPEN = /^[A-Za-z][\w.]*\s*\(\s*$/;

function parseModuleRepr(lines: string[]): ArchLayer[] {
  const out: ArchLayer[] = [];
  let seenOpen = false;
  for (const raw of lines) {
    if (!seenOpen) {
      if (REPR_OPEN.test(raw.trim())) seenOpen = true;
      continue;
    }
    const m = REPR_CHILD.exec(raw);
    if (!m) continue;
    let type = m[2];
    if (/bidirectional=true/i.test(raw) && /^(lstm|gru|rnn)$/i.test(type)) {
      type = `Bi${type}`;
    }
    // A repr carries no parameter counts, and an invented 0 would be a false
    // claim — the Python side derives them from the layer's own shapes; here we
    // report the count as unknown rather than guess.
    out.push(makeLayer(out.length, m[1], type, ""));
    if (out.length >= MAX_LAYERS) break;
  }
  return out;
}

/** Best-effort architecture from log lines; empty when nothing is recognised. */
export function parseArchitecture(lines: string[]): ArchLayer[] {
  const keras = parseKeras(lines);
  if (keras.length) return keras;
  return parseModuleRepr(lines);
}
