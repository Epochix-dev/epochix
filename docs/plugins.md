# Plugins

epochix supports external plugins via Python entry points (PEP 517/660).
You can add custom parsers, metaphor packs, exporters, and task types without
modifying the core package.

---

## Entry-point groups

| Group | Purpose |
|--|--|
| `epochix.parsers` | Register a custom log parser |
| `epochix.metaphor_packs` | Add domain-specific metaphor cards |
| `epochix.exporters` | Add a custom export format |
| `epochix.tasks` | Register a custom task type with grade thresholds |

---

## Writing a custom parser

### 1. Implement the `BaseParser` protocol

```python
# my_package/my_parser.py
import re
from epochix.models import RawMetric
from epochix.parsers.base import ParserContext

_MY_PATTERN = re.compile(r"step=(\d+)\s+my_metric=([\d.]+)")

class MyFrameworkParser:
    name = "my_framework"
    priority = 75  # between HuggingFace (80) and universal (1)

    def sniff(self, sample_lines: list[str]) -> float:
        hits = sum(1 for l in sample_lines if _MY_PATTERN.search(l))
        return min(hits / max(len(sample_lines), 1) * 3, 0.90)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        m = _MY_PATTERN.search(line)
        if not m:
            return []
        ctx.current_step = int(m.group(1))
        return [RawMetric(
            seq=ctx.seq, epoch=ctx.current_epoch, step=ctx.current_step,
            key="my_metric", value=float(m.group(2)),
            parser_name=self.name, confidence=0.88,
        )]
```

### 2. Register the entry point in `pyproject.toml`

```toml
[project.entry-points."epochix.parsers"]
my_framework = "my_package.my_parser:MyFrameworkParser"
```

### 3. Install

```bash
pip install -e .
```

epochix discovers the parser automatically on next run.

---

## Writing a metaphor pack

A metaphor pack is a Python package that provides a YAML file with
alternative narrative cards for a domain.

```yaml
# my_pack/metaphors.yaml
task: biometric
cards:
  awakening:
    - title: "Identity awakens"
      body: "The system sees everyone as the same. EER: {value}."
      icon: "👁️"
  learning:
    - title: "Faces take shape"
      body: "Broad identity clusters are forming. EER: {value}."
      icon: "🔍"
```

Register as:

```toml
[project.entry-points."epochix.metaphor_packs"]
my_biometric_pack = "my_pack:METAPHORS_YAML_PATH"
```

---

## Writing a custom exporter

```python
# my_package/my_exporter.py
from pathlib import Path
from epochix.models import Run, StoryFrame, MetricEvent
from typing import Sequence

def export_latex(
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
    output_path: str,
) -> None:
    """Export a run as a LaTeX report."""
    ...

EXPORTER = export_latex
```

```toml
[project.entry-points."epochix.exporters"]
latex = "my_package.my_exporter:EXPORTER"
```

Then use via CLI:

```bash
epochix export <run-id> --format latex --output report.tex
```

---

## Example: `epochix-fairseq`

A complete example plugin package for Facebook's Fairseq framework:

```
epochix-fairseq/
├── pyproject.toml
└── epochix_fairseq/
    ├── __init__.py
    └── parser.py         # FairseqParser class
```

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "epochix-fairseq"
version = "0.1.0"
dependencies = ["epochix>=0.1.0"]

[project.entry-points."epochix.parsers"]
fairseq = "epochix_fairseq.parser:FairseqParser"
```
