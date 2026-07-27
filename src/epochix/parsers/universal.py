from __future__ import annotations

import contextlib
import json
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# Pattern 1: key=value
# Key capture is bounded ({1,64}) so a long run of word characters before a
# missing delimiter can't trigger O(n²) backtracking (a 100k-char line used to
# hang the parser for seconds). A real metric key is never that long.
_KV_EQ = re.compile(r"(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 2: key: value
_KV_COLON = re.compile(r"(\w{1,64})\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 3: JSON-ish dict anywhere in the line
_JSON_FRAG = re.compile(r"\{[^{}]+\}")
# Bare "Epoch N" / "Epoch N/M" header (common when the epoch is printed on the
# same line as the metrics, e.g. "Epoch 1/8: loss=…"). Digit runs bounded to
# stay linear. Captures the epoch and, when present, the total for the progress
# bar. This is NOT a key=value pair, so the KV patterns miss it otherwise.
_EPOCH_HEADER = re.compile(r"\bepoch\s+(\d{1,9})(?:\s*/\s*(\d{1,9}))?\b", re.IGNORECASE)

_EPOCH_KEYS = frozenset({"epoch", "ep", "e"})
_STEP_KEYS = frozenset({"step", "iter", "iteration", "batch"})
# Never charted as metrics. Beyond obvious run metadata these cover the keyword
# arguments in a torch `print(model)` dump — following our own `epochix check`
# advice to print the model used to inject kernel_size/in_features/... into the
# dashboard as a fake "custom" metric series next to real accuracy.
_SKIP_KEYS = frozenset(
    {
        "pid",
        "port",
        "seed",
        "rank",
        "world_size",
        "node",
        # Run configuration, not performance. These are constants for the whole
        # run, so charting them produced a flat "custom" series sitting next to
        # real accuracy as though it were something the model was doing.
        "batch_size",
        "batchsize",
        "bs",
        "num_workers",
        "workers",
        "img_size",
        "imgsz",
        "epochs",
        "num_epochs",
        "max_epochs",
        "total_epochs",
        "gpus",
        "devices",
        "precision",
        "accumulate_grad_batches",
        "log_every_n_steps",
        "save_top_k",
        "patience",
        "verbose",
        # nn.Module repr kwargs
        "kernel_size",
        "stride",
        "padding",
        "dilation",
        "groups",
        "ceil_mode",
        "in_features",
        "out_features",
        "in_channels",
        "out_channels",
        "bias",
        "num_features",
        "eps",
        "momentum",
        "affine",
        "track_running_stats",
        "inplace",
        "output_padding",
        "padding_mode",
        "num_embeddings",
        "embedding_dim",
        "hidden_size",
        "num_layers",
        "nhead",
        "dropout",
        "batch_first",
        "return_indices",
        "count_include_pad",
    }
)

# tqdm / download progress bars ("Downloading: 100%|####| 26.4M/26.4M [00:03…]")
# yielded bogus "Downloading=100" and "00=3" metrics. Whole line is noise.
_PROGRESS_BAR = re.compile(r"\d{1,3}%\|")


@register_parser
class UniversalParser:
    name = "universal"
    priority = 1  # lowest — always a fallback

    def sniff(self, sample_lines: list[str]) -> float:  # noqa: ARG002
        return 0.10  # always weakly confident; format detector uses this as floor

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        if _PROGRESS_BAR.search(line):
            return []
        # Bare epoch header ("Epoch 1/8: …") — set the epoch/total so metrics on
        # the same line are stamped with it and the progress bar advances.
        eh = _EPOCH_HEADER.search(line)
        if eh is not None:
            ctx.current_epoch = float(eh.group(1))
            if eh.group(2) is not None:
                ctx.total_epochs = int(eh.group(2))

        # Collect every candidate first, in confidence order (JSON > key=value >
        # key: value), so the two passes below see the whole line.
        candidates: list[tuple[str, float, float]] = []

        for frag in _JSON_FRAG.finditer(line):
            text = frag.group().replace("'", '"')
            try:
                obj: dict[str, object] = json.loads(text)
            except json.JSONDecodeError:
                continue
            for k, v in obj.items():
                if isinstance(v, (int, float)):
                    candidates.append((k, float(v), 0.65))

        for m in _KV_EQ.finditer(line):
            with contextlib.suppress(ValueError):
                candidates.append((m.group(1), float(m.group(2)), 0.55))

        for m in _KV_COLON.finditer(line):
            with contextlib.suppress(ValueError):
                candidates.append((m.group(1), float(m.group(2)), 0.45))

        # Pass 1 — control keys (epoch/step) take effect BEFORE any metric on
        # this line is stamped. They can legitimately appear last: the SDK
        # serialises log(**kwargs) in call order, and frameworks emit e.g.
        # "loss=0.3 … epoch=3". Stamping as we scanned would have attributed
        # those metrics to the *previous* epoch (and dropped the first epoch
        # entirely, as epoch=None).
        claimed: set[str] = set()
        for key, val, _conf in candidates:
            key_lo = key.lower()
            if key_lo in claimed:
                continue
            if key_lo in _EPOCH_KEYS:
                claimed.add(key_lo)
                ctx.current_epoch = val
            elif key_lo in _STEP_KEYS:
                claimed.add(key_lo)
                ctx.current_step = int(val)

        # Pass 2 — emit the metrics; first occurrence of a key wins.
        metrics: list[RawMetric] = []
        seen_keys: set[str] = set()
        for key, val, conf in candidates:
            key_lo = key.lower()
            if (
                key_lo in seen_keys
                or key_lo in _SKIP_KEYS
                or key_lo in _EPOCH_KEYS
                or key_lo in _STEP_KEYS
            ):
                continue
            seen_keys.add(key_lo)
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=val,
                    parser_name=self.name,
                    confidence=conf,
                )
            )

        return metrics
