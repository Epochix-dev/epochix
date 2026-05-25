"""
architecture_parser.py — extract model layer info from training log headers.

Supported formats
-----------------
PyTorch Lightning (default):
  | Name    | Type       | Params
  -----------------------------------
  0 | encoder | ResNet50   | 23.5 M
  1 | head    | Linear     | 2.1 K

Keras / TF (partial — detects but reads layer type + params):
  Layer (type)          Output Shape      Param #
  dense (Dense)         (None, 128)       25,728

The output is a list of :class:`ArchLayer` dicts ready to be stored
in ``run.config["architecture"]`` and shipped to the frontend as JSON.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TypedDict

# ── layer-type → (tech_label, plain_label, visual_type) ─────────────────────

class _LayerMeta(TypedDict):
    tech_label: str
    plain_label: str
    visual_type: str   # conv | dense | recurrent | attention | norm | generic


_TYPE_MAP: list[tuple[str, _LayerMeta]] = [
    # Convolutional backbones (keyword in type name)
    ("resnet",        {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("vgg",           {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("efficientnet",  {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("mobilenet",     {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("inception",     {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("densenet",      {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("convnext",      {"tech_label": "ENCODER",  "plain_label": "Feature extractor",   "visual_type": "conv"}),
    ("swin",          {"tech_label": "ENCODER",  "plain_label": "Vision transformer",  "visual_type": "attention"}),
    ("vit",           {"tech_label": "ENCODER",  "plain_label": "Vision transformer",  "visual_type": "attention"}),
    ("conv2d",        {"tech_label": "CONV",     "plain_label": "Spatial patterns",    "visual_type": "conv"}),
    ("conv1d",        {"tech_label": "CONV",     "plain_label": "Sequence patterns",   "visual_type": "conv"}),
    ("conv",          {"tech_label": "CONV",     "plain_label": "Pattern finder",      "visual_type": "conv"}),
    # Recurrent
    ("lstm",          {"tech_label": "MEMORY",   "plain_label": "Remembers context",   "visual_type": "recurrent"}),
    ("gru",           {"tech_label": "MEMORY",   "plain_label": "Remembers context",   "visual_type": "recurrent"}),
    ("rnn",           {"tech_label": "MEMORY",   "plain_label": "Sequence memory",     "visual_type": "recurrent"}),
    # Attention / Transformers
    ("multiheadattn", {"tech_label": "FOCUS",    "plain_label": "Multi-head attention","visual_type": "attention"}),
    ("attention",     {"tech_label": "FOCUS",    "plain_label": "Reads full context",  "visual_type": "attention"}),
    ("transformer",   {"tech_label": "FOCUS",    "plain_label": "Language understander","visual_type": "attention"}),
    ("bert",          {"tech_label": "FOCUS",    "plain_label": "Language understander","visual_type": "attention"}),
    ("gpt",           {"tech_label": "FOCUS",    "plain_label": "Language generator",  "visual_type": "attention"}),
    # Dense / FC
    ("embedding",     {"tech_label": "EMBED",    "plain_label": "Symbol mapper",       "visual_type": "dense"}),
    ("linear",        {"tech_label": "HEAD",     "plain_label": "Decision maker",      "visual_type": "dense"}),
    ("dense",         {"tech_label": "HEAD",     "plain_label": "Decision maker",      "visual_type": "dense"}),
    # Normalisation / regularisation
    ("batchnorm",     {"tech_label": "NORM",     "plain_label": "Stabiliser",          "visual_type": "norm"}),
    ("layernorm",     {"tech_label": "NORM",     "plain_label": "Stabiliser",          "visual_type": "norm"}),
    ("groupnorm",     {"tech_label": "NORM",     "plain_label": "Stabiliser",          "visual_type": "norm"}),
    ("dropout",       {"tech_label": "DROP",     "plain_label": "Regulariser",         "visual_type": "norm"}),
    ("pool",          {"tech_label": "POOL",     "plain_label": "Compressor",          "visual_type": "norm"}),
]


def _classify(layer_type: str) -> _LayerMeta:
    lt = layer_type.lower().replace(" ", "").replace("-", "").replace("_", "")
    for keyword, meta in _TYPE_MAP:
        if keyword in lt:
            return meta
    return {"tech_label": "LAYER", "plain_label": "Processing unit", "visual_type": "generic"}


def _parse_params(raw: str) -> int:
    """Turn '23.5 M', '2.1 K', '25,728' into an integer."""
    s = raw.strip().upper().replace(",", "").replace(" ", "")
    for suffix, mult in (("B", 1_000_000_000), ("G", 1_000_000_000),
                          ("M", 1_000_000), ("K", 1_000)):
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
    visual_type: str   # conv | dense | recurrent | attention | norm | generic

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ── PyTorch Lightning parser ──────────────────────────────────────────────────

# Header:  `| Name    | Type       | Params`
_PL_HEADER = re.compile(r"\|\s*Name\s*\|\s*Type\s*\|\s*Params", re.IGNORECASE)

# Data row: `0 | encoder | ResNet50   | 23.5 M`
_PL_ROW = re.compile(
    r"^\s*(\d+)\s*\|\s*([\w][\w.\-/]*)\s*\|\s*([\w.\-/]+"
    r"(?:\s+[\w.\-/]+)*)\s*\|\s*([\d,.]+\s*[KMBGkmb]?)\s*$"
)

# Separator: `---...---`
_SEPARATOR = re.compile(r"^\s*-{5,}")


def _parse_pytorch_lightning(lines: list[str]) -> list[ArchLayer]:
    result: list[ArchLayer] = []
    in_table = False
    sep_count = 0

    for line in lines:
        if _PL_HEADER.search(line):
            in_table = True
            sep_count = 0
            result = []           # use the *last* table found
            continue

        if not in_table:
            continue

        if _SEPARATOR.match(line):
            sep_count += 1
            if sep_count >= 2 and result:  # trailing separator = end
                break
            continue

        m = _PL_ROW.match(line)
        if m:
            idx        = int(m.group(1))
            name       = m.group(2).strip()
            layer_type = m.group(3).strip()
            params_str = m.group(4).strip()
            params     = _parse_params(params_str)
            meta       = _classify(layer_type)
            result.append(ArchLayer(
                idx=idx, name=name, layer_type=layer_type,
                params=params, params_str=params_str,
                **meta,
            ))
        # Any non-matching line after first row probably means end of table
        elif result and not re.match(
            r"^\s*[\d,.]+\s*(K|M|B|G|Trainable|Non|Total)", line, re.IGNORECASE
        ):
            in_table = False

    return result


# ── public API ────────────────────────────────────────────────────────────────

def parse_architecture(lines: list[str]) -> list[ArchLayer]:
    """Scan up to *lines* for model summary tables; return layer list or []."""
    layers = _parse_pytorch_lightning(lines)
    # Future: add Keras / TF / torchinfo parsers here
    return layers
