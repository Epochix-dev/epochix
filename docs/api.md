# Python SDK reference

Everything below is importable straight from the top-level package:

```python
from epochix import parse, parse_string, compare, export, visualize, LiveReporter
```

A parsed run can be handed straight to the others:

```python
from epochix import parse, compare, export

run = parse("train.log")                 # kept in memory; nothing is written to disk
export(run, "md", output="report.md")
print(compare(run, parse("baseline.log")).narrative)
```

`parse()` stores a run in memory unless it is given `db=`. `export()`,
`compare()` and `visualize()` read it from wherever it was parsed into, for as
long as the `Run` object is kept. For a run from anywhere else (an earlier
session, the CLI, `LiveReporter`), they read the configured database, or the
one passed as `db=`.

## Parsing

::: epochix.sdk.parse.parse

::: epochix.sdk.parse.parse_string

## Live reporting

::: epochix.sdk.live_reporter.LiveReporter

## Comparison

::: epochix.sdk.compare.compare

## Export

::: epochix.sdk.export.export

## Visualisation

::: epochix.sdk.visualize.visualize

::: epochix.sdk.visualize.serve

## Core models

::: epochix.models.Run
    options:
      members: false

::: epochix.models.MetricEvent
    options:
      members: false

::: epochix.models.StoryFrame
    options:
      members: false

## Plugin interface

::: epochix.parsers.base.BaseParser

::: epochix.parsers.registry.register_parser
