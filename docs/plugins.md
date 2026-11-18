# Plugins

epochix reads plugins through Python entry points: install a package that
declares one and epochix finds it, with no change to epochix itself. Two
groups work today. Two more have a loader and are read by nothing yet.

---

## Entry-point groups

| Group | Purpose | Read |
|--|--|--|
| `epochix.parsers` | Register a custom log parser | Yes |
| `epochix.exporters` | Add a custom export format | Yes |
| `epochix.metaphor_packs` | Add domain-specific metaphor cards | **No**: installing one changes nothing |
| `epochix.tasks` | Register a custom task type with grade thresholds | **No**: installing one changes nothing |

Plugins are read by the Python package: the CLI, the server and the dashboard
it serves. The VS Code extension tells a run with its own engine, written in
TypeScript, which cannot load a Python package. Its export command offers the
built-in formats only.

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

**Not read yet.** Nothing loads the `epochix.metaphor_packs` group: an
installed pack changes no card. A frame's cards are the engine's own (its
phase and its grade). A pack's cards would be free text placed beside the
grade, and epochix holds its own words to what the numbers support, so how a
pack's words could be held to the same rule is an open question, not a
missing line of code. The format below is what the loader accepts.

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

An exporter is a callable that is given the stored run, its story frames and
its metric events, and writes one file to the path it is given.

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
epochix train.log --headless --export latex
```

or from the server, which returns the file as a download:

```text
GET /api/export/<run-id>/latex
```

- The names of the built-in formats (`html`, `pdf`, `md`, `json`, `gif`) are
  taken. A plugin that declares one of them is not loaded, and a warning is
  logged.
- An exporter that raises, or returns without writing its file, is reported
  as a failure, naming the package it came from. Nothing is reported as
  written that was not.
- `epochix export --format <anything>` for a format nobody writes lists every
  format that can be written, the installed plugins' included.

---

## Writing a custom task type

**Not read yet.** `epochix.plugins.task_registry.TaskDefinition` and the
`epochix.tasks` group exist, and nothing reads them: no grading, detection or
narration code consults the registry, and an installed task changes no grade.
Task types are a fixed list (`epochix.enums.TaskType`), and the extension's
engine grades from tables generated from the Python, so a task added by a
Python plugin would grade one way in the dashboard and another in VS Code.
To change the thresholds of a task epochix already has, use the project's
`.epochix.yaml` (see `.epochix.example.yaml`), which both engines read.

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
