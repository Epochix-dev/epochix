/**
 * Every parser reads every recorded line as its Python original does.
 *
 * The parsers are ported by hand, and the ports drifted behind and brought
 * back bugs Python had fixed. Corpus parity compares whole logs through the
 * whole engine, where a line one parser reads differently can be covered by
 * another. src/test/fixtures/parsers.golden.json is every call the Python
 * tests make to a parser directly — the lines they feed it, in order, on one
 * context, and what came back: the metrics, whether the line was claimed, and
 * the epoch, step and epoch count after it; and every sniff score.
 * scripts/gen_ts_engine_tables.py records it (scripts/parser_recorder.py) and
 * tests/unit/test_ts_engine_tables_sync.py replays it through Python, so it
 * is Python's answer. This replays it through the ports.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { AccelerateParser } from "../../parsers/accelerate";
import { makeContext, type Parser, type RawMetric } from "../../parsers/base";
import { BoostingParser } from "../../parsers/boosting";
import { FastAIParser } from "../../parsers/fastai";
import { HuggingFaceParser } from "../../parsers/huggingface";
import { KerasParser } from "../../parsers/keras";
import { PytorchLightningParser } from "../../parsers/pytorchLightning";
import { UniversalParser } from "../../parsers/universal";
import { YoloParser } from "../../parsers/yolo";

type Num = number | string | null;
type Out = [string, Num, Num, number | null, number][];
type State = [Num, number | null, number | null];
type LineRow = [string, number, string, Out, boolean, State];
type FlushRow = [string, "flush", Out];

interface Sniff {
  sniff: string;
  lines: string[];
  score: number;
}
interface Sequence {
  start: State;
  events: (LineRow | FlushRow)[];
}
type Golden = Record<string, (Sniff | Sequence)[]>;

const PARSERS: Record<string, () => Parser> = {
  accelerate: () => new AccelerateParser(),
  boosting: () => new BoostingParser(),
  fastai: () => new FastAIParser(),
  huggingface: () => new HuggingFaceParser(),
  keras_tensorflow: () => new KerasParser(),
  pytorch_lightning: () => new PytorchLightningParser(),
  universal: () => new UniversalParser(),
  ultralytics_yolo: () => new YoloParser(),
};

function golden(): Golden {
  const ext = vscode.extensions.getExtension("epochix.epochix");
  assert.ok(ext, "extension epochix.epochix not found");
  const file = path.join(ext.extensionPath, "src", "test", "fixtures", "parsers.golden.json");
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Golden;
}

/** JSON has no NaN or infinity; the recorder writes them as strings. */
function num(v: Num): number | null {
  if (v === "nan") return NaN;
  if (v === "inf") return Infinity;
  if (v === "-inf") return -Infinity;
  return v as number | null;
}

function encode(v: number | null): Num {
  if (v === null || Number.isFinite(v)) return v;
  return Number.isNaN(v) ? "nan" : v > 0 ? "inf" : "-inf";
}

function rows(out: RawMetric[]): Out {
  return out.map((m) => [m.key, encode(m.value), encode(m.epoch), m.step, m.seq]);
}

/** Every difference for one parser, as a readable line. */
function replay(g: Golden, only: string): { calls: number; wrong: string[] } {
  let calls = 0;
  const wrong: string[] = [];
  for (const [node, sequences] of Object.entries(g)) {
    sequences.forEach((sequence, n) => {
      const where = `${node} #${n}`;
      if ("sniff" in sequence) {
        if (sequence.sniff !== only) return;
        calls++;
        const got = PARSERS[only]().sniff(sequence.lines);
        if (Math.abs(got - sequence.score) > 1e-12) {
          wrong.push(`${where}: sniff ${got} != ${sequence.score}`);
        }
        return;
      }
      if (!sequence.events.some((e) => e[0] === only)) return;
      // The whole sequence is replayed — a parser's line can depend on what
      // another parser did to the shared context — but only this parser's
      // calls are judged here.
      const ctx = makeContext();
      ctx.currentEpoch = num(sequence.start[0]);
      ctx.currentStep = sequence.start[1];
      ctx.totalEpochs = sequence.start[2];
      const parsers = new Map<string, Parser>();
      for (const event of sequence.events) {
        const name = event[0];
        let parser = parsers.get(name);
        if (parser === undefined) {
          parser = PARSERS[name]();
          parsers.set(name, parser);
        }
        if (event[1] === "flush") {
          const got = rows(parser.flush ? parser.flush(ctx) : []);
          if (name !== only) continue;
          calls++;
          if (JSON.stringify(got) !== JSON.stringify(event[2])) {
            wrong.push(`${where} flush: ${JSON.stringify(got)} != ${JSON.stringify(event[2])}`);
          }
          continue;
        }
        const [, seq, line, out, claimed, state] = event;
        ctx.seq = seq;
        ctx.lineClaimed = false;
        const got = rows(parser.parseLine(line, ctx));
        const gotState: State = [encode(ctx.currentEpoch), ctx.currentStep, ctx.totalEpochs];
        if (name !== only) continue;
        calls++;
        const said = JSON.stringify([got, ctx.lineClaimed, gotState]);
        const want = JSON.stringify([out, claimed, state]);
        if (said !== want) wrong.push(`${where} ${JSON.stringify(line)}:\n    got  ${said}\n    want ${want}`);
      }
    });
  }
  return { calls, wrong };
}

suite("Parsers read every recorded line as Python does", () => {
  const g = golden();

  test("the golden names only parsers the extension has", () => {
    const names = new Set<string>();
    for (const sequences of Object.values(g)) {
      for (const s of sequences) {
        if ("sniff" in s) names.add(s.sniff);
        else s.events.forEach((e) => names.add(e[0]));
      }
    }
    assert.deepStrictEqual([...names].filter((n) => !(n in PARSERS)), []);
    // Every port meets real lines, or its replay passes by doing nothing.
    assert.deepStrictEqual(Object.keys(PARSERS).filter((n) => !names.has(n)), []);
  });

  for (const name of Object.keys(PARSERS)) {
    test(name, () => {
      const { calls, wrong } = replay(g, name);
      assert.ok(calls > 0, `${name}: no recorded call`);
      assert.deepStrictEqual(wrong.slice(0, 15), [], `${name}: ${wrong.length} of ${calls} calls differ`);
    });
  }
});
