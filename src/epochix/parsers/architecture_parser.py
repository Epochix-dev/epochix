"""
architecture_parser.py — extract model layer info from training-log headers.

Detects the model architecture from whatever summary a framework prints at the
top of a run, across the common formats:

* **PyTorch Lightning** ``ModelSummary`` table  (``| Name | Type | Params``)
* **Keras / TF** ``model.summary()``  (classic and Keras-3 box-drawing styles)
* **torchinfo / torchsummary** tables  (``Layer (type:depth-idx)`` / ``Conv2d-1``)
* **Plain ``print(model)``** module repr  (``(name): Type(args)``)

Each is parsed into :class:`ArchLayer` records (stored in
``run.config["architecture"]`` and shipped to the frontend). Layer *types* are
mapped to a small set of visual archetypes (conv / recurrent / attention / dense
/ norm / generic) used by the Network-State visualization. Unknown types degrade
gracefully to a generic block rather than being dropped.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TypedDict

# Cap how many layers we visualise — keeps deep models legible.
_MAX_LAYERS = 24


# ── layer-type → (tech_label, plain_label, visual_type) ─────────────────────


class _LayerMeta(TypedDict):
    tech_label: str
    plain_label: str
    visual_type: str  # conv | dense | recurrent | attention | norm | generic


_CONV_ENCODER: _LayerMeta = {
    "tech_label": "ENCODER",
    "plain_label": "Feature extractor",
    "visual_type": "conv",
}
_VIS_XFORMER: _LayerMeta = {
    "tech_label": "ENCODER",
    "plain_label": "Vision transformer",
    "visual_type": "attention",
}

# Ordered most-specific → most-generic. Keys are matched as substrings against the
# layer type after lowercasing and stripping spaces/dashes/underscores.
_TYPE_MAP: list[tuple[str, _LayerMeta]] = [
    # ── Conv backbones / detectors (named models) ──────────────────────────
    ("resnext", _CONV_ENCODER),
    ("resnet", _CONV_ENCODER),
    ("vgg", _CONV_ENCODER),
    ("efficientnet", _CONV_ENCODER),
    ("mobilenet", _CONV_ENCODER),
    ("inception", _CONV_ENCODER),
    ("densenet", _CONV_ENCODER),
    ("convnext", _CONV_ENCODER),
    ("regnet", _CONV_ENCODER),
    ("squeezenet", _CONV_ENCODER),
    ("shufflenet", _CONV_ENCODER),
    ("mnasnet", _CONV_ENCODER),
    ("nasnet", _CONV_ENCODER),
    ("alexnet", _CONV_ENCODER),
    ("googlenet", _CONV_ENCODER),
    ("xception", _CONV_ENCODER),
    ("cspdarknet", _CONV_ENCODER),
    ("darknet", _CONV_ENCODER),
    ("retinanet", _CONV_ENCODER),
    ("fasterrcnn", _CONV_ENCODER),
    ("maskrcnn", _CONV_ENCODER),
    ("fpn", {"tech_label": "NECK", "plain_label": "Feature pyramid", "visual_type": "conv"}),
    # ── Vision transformers ────────────────────────────────────────────────
    ("swin", _VIS_XFORMER),
    ("deit", _VIS_XFORMER),
    ("beit", _VIS_XFORMER),
    ("vit", _VIS_XFORMER),
    # ── YOLO / detection blocks ────────────────────────────────────────────
    ("sppf", {"tech_label": "POOL", "plain_label": "Pyramid pooling", "visual_type": "norm"}),
    ("spp", {"tech_label": "POOL", "plain_label": "Pyramid pooling", "visual_type": "norm"}),
    ("bottleneck", {"tech_label": "BLOCK", "plain_label": "Residual block", "visual_type": "conv"}),
    ("c2f", {"tech_label": "BLOCK", "plain_label": "Feature block", "visual_type": "conv"}),
    ("c3", {"tech_label": "BLOCK", "plain_label": "Feature block", "visual_type": "conv"}),
    ("detect", {"tech_label": "DETECT", "plain_label": "Object detector", "visual_type": "dense"}),
    ("yolo", _CONV_ENCODER),
    ("focusblock", {"tech_label": "STEM", "plain_label": "Input stem", "visual_type": "conv"}),
    # ── Conv primitives ────────────────────────────────────────────────────
    ("convtranspose", {"tech_label": "UPCONV", "plain_label": "Upsampler", "visual_type": "conv"}),
    (
        "depthwiseconv",
        {"tech_label": "CONV", "plain_label": "Spatial patterns", "visual_type": "conv"},
    ),
    (
        "separableconv",
        {"tech_label": "CONV", "plain_label": "Spatial patterns", "visual_type": "conv"},
    ),
    ("conv3d", {"tech_label": "CONV", "plain_label": "Volumetric patterns", "visual_type": "conv"}),
    ("conv2d", {"tech_label": "CONV", "plain_label": "Spatial patterns", "visual_type": "conv"}),
    ("conv1d", {"tech_label": "CONV", "plain_label": "Sequence patterns", "visual_type": "conv"}),
    ("conv", {"tech_label": "CONV", "plain_label": "Pattern finder", "visual_type": "conv"}),
    # ── Recurrent ──────────────────────────────────────────────────────────
    (
        "bilstm",
        {
            "tech_label": "MEMORY",
            "plain_label": "Bi-directional memory",
            "visual_type": "recurrent",
        },
    ),
    (
        "bigru",
        {
            "tech_label": "MEMORY",
            "plain_label": "Bi-directional memory",
            "visual_type": "recurrent",
        },
    ),
    (
        "lstm",
        {"tech_label": "MEMORY", "plain_label": "Remembers context", "visual_type": "recurrent"},
    ),
    (
        "gru",
        {"tech_label": "MEMORY", "plain_label": "Remembers context", "visual_type": "recurrent"},
    ),
    ("rnn", {"tech_label": "MEMORY", "plain_label": "Sequence memory", "visual_type": "recurrent"}),
    # ── Attention / transformers ───────────────────────────────────────────
    (
        "multiheadattention",
        {"tech_label": "FOCUS", "plain_label": "Multi-head attention", "visual_type": "attention"},
    ),
    (
        "multiheadattn",
        {"tech_label": "FOCUS", "plain_label": "Multi-head attention", "visual_type": "attention"},
    ),
    (
        "crossattention",
        {"tech_label": "FOCUS", "plain_label": "Cross attention", "visual_type": "attention"},
    ),
    (
        "selfattention",
        {"tech_label": "FOCUS", "plain_label": "Self attention", "visual_type": "attention"},
    ),
    (
        "attention",
        {"tech_label": "FOCUS", "plain_label": "Reads full context", "visual_type": "attention"},
    ),
    (
        "transformerencoder",
        {"tech_label": "FOCUS", "plain_label": "Transformer encoder", "visual_type": "attention"},
    ),
    (
        "transformerdecoder",
        {"tech_label": "FOCUS", "plain_label": "Transformer decoder", "visual_type": "attention"},
    ),
    (
        "transformer",
        {"tech_label": "FOCUS", "plain_label": "Transformer", "visual_type": "attention"},
    ),
    (
        "distilbert",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "roberta",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "deberta",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "electra",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "albert",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "bert",
        {"tech_label": "FOCUS", "plain_label": "Language understander", "visual_type": "attention"},
    ),
    (
        "llama",
        {"tech_label": "FOCUS", "plain_label": "Language generator", "visual_type": "attention"},
    ),
    (
        "mistral",
        {"tech_label": "FOCUS", "plain_label": "Language generator", "visual_type": "attention"},
    ),
    (
        "qwen",
        {"tech_label": "FOCUS", "plain_label": "Language generator", "visual_type": "attention"},
    ),
    (
        "gpt",
        {"tech_label": "FOCUS", "plain_label": "Language generator", "visual_type": "attention"},
    ),
    (
        "t5",
        {"tech_label": "FOCUS", "plain_label": "Seq2seq transformer", "visual_type": "attention"},
    ),
    (
        "bart",
        {"tech_label": "FOCUS", "plain_label": "Seq2seq transformer", "visual_type": "attention"},
    ),
    (
        "encoderlayer",
        {"tech_label": "FOCUS", "plain_label": "Transformer block", "visual_type": "attention"},
    ),
    (
        "decoderlayer",
        {"tech_label": "FOCUS", "plain_label": "Transformer block", "visual_type": "attention"},
    ),
    # ── Embeddings ─────────────────────────────────────────────────────────
    (
        "patchembed",
        {"tech_label": "EMBED", "plain_label": "Patch embedder", "visual_type": "dense"},
    ),
    (
        "positionalencoding",
        {"tech_label": "EMBED", "plain_label": "Position encoder", "visual_type": "dense"},
    ),
    (
        "posencoding",
        {"tech_label": "EMBED", "plain_label": "Position encoder", "visual_type": "dense"},
    ),
    ("embedding", {"tech_label": "EMBED", "plain_label": "Symbol mapper", "visual_type": "dense"}),
    # ── Dense / FC / heads ─────────────────────────────────────────────────
    ("feedforward", {"tech_label": "FFN", "plain_label": "Feed-forward", "visual_type": "dense"}),
    ("classifier", {"tech_label": "HEAD", "plain_label": "Decision maker", "visual_type": "dense"}),
    ("linear", {"tech_label": "HEAD", "plain_label": "Decision maker", "visual_type": "dense"}),
    ("dense", {"tech_label": "HEAD", "plain_label": "Decision maker", "visual_type": "dense"}),
    ("mlp", {"tech_label": "MLP", "plain_label": "Dense block", "visual_type": "dense"}),
    ("ffn", {"tech_label": "FFN", "plain_label": "Feed-forward", "visual_type": "dense"}),
    # ── Normalisation / regularisation / pooling ───────────────────────────
    ("batchnorm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("layernorm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("groupnorm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("instancenorm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("rmsnorm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("norm", {"tech_label": "NORM", "plain_label": "Stabiliser", "visual_type": "norm"}),
    ("dropout", {"tech_label": "DROP", "plain_label": "Regulariser", "visual_type": "norm"}),
    ("droppath", {"tech_label": "DROP", "plain_label": "Regulariser", "visual_type": "norm"}),
    ("pool", {"tech_label": "POOL", "plain_label": "Compressor", "visual_type": "norm"}),
    ("upsample", {"tech_label": "UPSAMP", "plain_label": "Upsampler", "visual_type": "norm"}),
]

# Structurally-uninteresting layers: dropped from the diagram when richer layers
# exist (they carry no parameters and add visual noise).
_TRIVIAL = (
    "flatten",
    "identity",
    "reshape",
    "permute",
    "view",
    "relu",
    "gelu",
    "silu",
    "swish",
    "sigmoid",
    "tanh",
    "softmax",
    "leakyrelu",
    "elu",
    "mish",
    "hardswish",
    "hardtanh",
    "prelu",
    "activation",
)


def _norm(layer_type: str) -> str:
    return layer_type.lower().replace(" ", "").replace("-", "").replace("_", "")


def _classify(layer_type: str) -> _LayerMeta:
    lt = _norm(layer_type)
    for keyword, meta in _TYPE_MAP:
        if keyword in lt:
            return meta
    return {"tech_label": "LAYER", "plain_label": "Processing unit", "visual_type": "generic"}


def _is_trivial(layer_type: str) -> bool:
    lt = _norm(layer_type)
    return any(k in lt for k in _TRIVIAL)


def _parse_params(raw: str) -> int:
    """Turn '23.5 M', '2.1 K', '25,728' into an integer."""
    s = raw.strip().upper().replace(",", "").replace(" ", "")
    for suffix, mult in (
        ("B", 1_000_000_000),
        ("G", 1_000_000_000),
        ("M", 1_000_000),
        ("K", 1_000),
    ):
        if s.endswith(suffix):
            try:
                return int(float(s[:-1]) * mult)
            except ValueError:
                pass
    try:
        return int(float(s))
    except ValueError:
        return 0


# ── data class ────────────────────────────────────────────────────────────────


@dataclass
class ArchLayer:
    idx: int
    name: str
    layer_type: str
    params: int
    params_str: str
    tech_label: str
    plain_label: str
    visual_type: str  # conv | dense | recurrent | attention | norm | generic

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _make_layer(idx: int, name: str, layer_type: str, params_str: str) -> ArchLayer:
    params = _parse_params(params_str)
    return ArchLayer(
        idx=idx,
        name=name,
        layer_type=layer_type,
        params=params,
        params_str=params_str.strip(),
        **_classify(layer_type),
    )


# ── PyTorch Lightning ModelSummary ──────────────────────────────────────────────

_PL_HEADER = re.compile(r"\|\s*Name\s*\|\s*Type\s*\|\s*Params", re.IGNORECASE)
_PL_ROW = re.compile(
    r"^\s*(\d+)\s*\|\s*([\w][\w.\-/]*)\s*\|\s*([\w.\-/]+"
    r"(?:\s+[\w.\-/]+)*)\s*\|\s*([\d,.]+\s*[KMBGkmb]?)\s*$"
)
_SEPARATOR = re.compile(r"^\s*-{5,}")


def _parse_pytorch_lightning(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    in_table = False
    sep_count = 0
    for line in lines:
        if _PL_HEADER.search(line):
            in_table, sep_count, result = True, 0, []
            continue
        if not in_table:
            continue
        if _SEPARATOR.match(line):
            sep_count += 1
            if sep_count >= 2 and result:
                break
            continue
        m = _PL_ROW.match(line)
        if m:
            result.append(
                _make_layer(int(m.group(1)), m.group(2).strip(), m.group(3).strip(), m.group(4))
            )
        elif result and not re.match(
            r"^\s*[\d,.]+\s*(K|M|B|G|Trainable|Non|Total)", line, re.IGNORECASE
        ):
            in_table = False
    return result


# ── Keras / TF model.summary() ───────────────────────────────────────────────

_KERAS_HEADER = re.compile(r"Layer\s*\(type\).*Param", re.IGNORECASE)
_KERAS_END = re.compile(r"^[=_]{3,}|Total params|Trainable params", re.IGNORECASE)
# classic row:  conv2d (Conv2D)      (None, 26, 26, 32)      320
_KERAS_ROW = re.compile(r"^\s*([\w./-]+)\s*\(([\w.]+)")
_INT_TOKEN = re.compile(r"(\d[\d,]*)")


def _parse_keras_summary(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    in_table = False
    idx = 0
    for raw in lines:
        if _KERAS_HEADER.search(raw):
            in_table, result, idx = True, [], 0
            continue
        if not in_table:
            continue
        line = raw.strip("│┃ \t\r\n")
        if not line or set(line) <= set("=_-─━ "):
            continue
        if _KERAS_END.match(line):
            if result:
                break
            continue
        # Box-drawing (Keras 3) splits cells on │/┃/|; classic uses whitespace.
        cells = [c.strip() for c in re.split(r"[│┃|]", raw) if c.strip()]
        head = cells[0] if cells else line
        m = _KERAS_ROW.match(head)
        if not m:
            continue
        name, layer_type = m.group(1), m.group(2)
        # Some Keras builds omit the "(Type)" and the first parens is the output
        # shape, e.g. "max_pooling2d   (None, 15, 15, 32)". Fall back to the
        # layer name (which encodes the type, e.g. max_pooling2d → pool).
        if layer_type.lower() == "none" or layer_type[:1].isdigit():
            layer_type = name
        nums = _INT_TOKEN.findall(raw)
        params_str = nums[-1] if nums else "0"
        result.append(_make_layer(idx, name, layer_type, params_str))
        idx += 1
    return result


# ── torchinfo / torchsummary tables ──────────────────────────────────────────

_TI_HEADER = re.compile(r"Layer\s*\(type", re.IGNORECASE)
# matches `├─Conv2d: 1-1`, `Conv2d-1`, `│    └─Linear: 2-3`
_TI_ROW = re.compile(r"^[\s│├└─|+`-]*([A-Za-z][\w.]*?)(?::\s*[\d-]+|-\d+)\b")


def _parse_torchinfo(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    in_table = False
    idx = 0
    for raw in lines:
        if _TI_HEADER.search(raw):
            in_table, result, idx = True, [], 0
            continue
        if not in_table:
            continue
        line = raw.strip()
        if not line or set(line) <= set("=_-─ "):
            continue
        if re.match(
            r"^(Total params|Trainable params|Non-trainable|Estimated)", line, re.IGNORECASE
        ):
            if result:
                break
            continue
        m = _TI_ROW.match(raw)
        if not m:
            continue
        layer_type = m.group(1)
        nums = _INT_TOKEN.findall(raw.split("]")[-1]) or _INT_TOKEN.findall(raw)
        params_str = nums[-1] if nums else "0"
        result.append(_make_layer(idx, layer_type.lower(), layer_type, params_str))
        idx += 1
    return result


# ── Plain print(model) module repr ───────────────────────────────────────────

# Top-level child:  `  (encoder): ResNet(`  /  `  (lstm): LSTM(256, 512, ...)`
_REPR_CHILD = re.compile(r"^\s{2,4}\(([\w.]+)\):\s*([A-Za-z][\w.]*)\s*\(")
_REPR_OPEN = re.compile(r"^[A-Za-z][\w.]*\s*\(\s*$")


def _parse_module_repr(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    seen_open = False
    idx = 0
    for raw in lines:
        if not seen_open:
            if _REPR_OPEN.match(raw.strip()):
                seen_open = True
            continue
        m = _REPR_CHILD.match(raw)
        if not m:
            continue
        name, layer_type = m.group(1), m.group(2)
        # Detect bi-directional recurrent layers for a richer label.
        if "bidirectional=true" in raw.lower() and layer_type.lower() in ("lstm", "gru", "rnn"):
            layer_type = "Bi" + layer_type
        result.append(_make_layer(idx, name, layer_type, "0"))
        idx += 1
    return result


# ── Ultralytics YOLO verbose layer table ─────────────────────────────────────

#                    from  n    params  module                          arguments
#   0                  -1  1       928  ultralytics.nn.modules.conv.Conv [3, 32, 3, 2]
#  22        [15, 18, 21]  1    751507  ultralytics.nn.modules.head.Detect ...
_ULTRA_HEADER = re.compile(r"\bfrom\s+n\s+params\s+module", re.IGNORECASE)
_ULTRA_ROW = re.compile(r"^\s*(\d+)\s+(?:-?\d+|\[[\d,\s]+\])\s+\d+\s+(\d+)\s+([\w.]+)")


def _parse_ultralytics(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    in_table = False
    idx = 0
    for raw in lines:
        if _ULTRA_HEADER.search(raw):
            in_table, result, idx = True, [], 0
            continue
        if not in_table:
            continue
        m = _ULTRA_ROW.match(raw)
        if not m:
            if result and raw.strip():
                break  # table ended
            continue
        module = m.group(3).split(".")[-1]  # ...modules.head.Detect → Detect
        result.append(_make_layer(idx, module, module, m.group(2)))
        idx += 1
    return result


# ── one-line model summary fallback ──────────────────────────────────────────

# "Ultralytics YOLOv8n summary: 225 layers, 3157200 parameters"
_SUMMARY_LINE = re.compile(r"([A-Za-z][\w/+-]*)\s+summary:.*?([\d,]+)\s+param", re.IGNORECASE)


def _parse_summary_line(lines: list[str]) -> list[ArchLayer]:
    """Last-resort: name the model from a one-line summary (no per-layer table)."""
    for raw in lines:
        m = _SUMMARY_LINE.search(raw)
        if m:
            return [_make_layer(0, m.group(1), m.group(1), m.group(2))]
    return []


# ── public API ────────────────────────────────────────────────────────────────

_PARSERS = (
    _parse_pytorch_lightning,
    _parse_keras_summary,
    _parse_torchinfo,
    _parse_ultralytics,
    _parse_module_repr,
)


def _downsample(layers: list[ArchLayer], k: int) -> list[ArchLayer]:
    """Keep *k* evenly-spaced layers, always including the first and last so the
    overall input→…→head shape of a deep model is preserved."""
    n = len(layers)
    idxs = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [layers[i] for i in idxs]


def _clean(layers: list[ArchLayer]) -> list[ArchLayer]:
    """Drop trivial layers (unless that empties it) and cap the count."""
    if not layers:
        return layers
    filtered = [lyr for lyr in layers if not _is_trivial(lyr.layer_type)]
    layers = filtered or layers
    if len(layers) > _MAX_LAYERS:
        layers = _downsample(layers, _MAX_LAYERS)
    for i, lyr in enumerate(layers):
        lyr.idx = i
    return layers


def parse_architecture(lines: list[str]) -> list[ArchLayer]:
    """Detect the model architecture from any supported summary format.

    Runs every format parser and keeps the richest result (most layers), so a
    log can contain any of: PyTorch Lightning, Keras ``model.summary()``,
    torchinfo/torchsummary, Ultralytics YOLO, or a plain ``print(model)`` dump.
    Falls back to naming the model from a one-line summary when no per-layer
    table is present.
    """
    best: list[ArchLayer] = []
    for parser in _PARSERS:
        try:
            layers = _clean(parser(lines))
        except Exception:  # noqa: BLE001 — a malformed table must never break ingest
            layers = []
        if len(layers) > len(best):
            best = layers
    if not best:
        best = _parse_summary_line(lines)
    return best
