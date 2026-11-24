/**
 * Numbers as the Python engine writes them into a sentence: `f"{x:.4f}"`,
 * `f"{x:.2e}"`, `f"{x:.4g}"`.
 *
 * `toFixed` and `toExponential` round a value exactly halfway up, and Python
 * rounds it to even. A Keras run's 0.7325 was "73.3%" in VS Code and "73.2%"
 * everywhere else (nine frames of the corpus, in three languages). Both round
 * the double's exact binary value, so the rounding here is done on that value,
 * in BigInt arithmetic, and a tie is the exact halfway point it is in Python.
 * Python's answers are replayed in format.golden.json.
 */

/** The double as a sign and an exact fraction num / den. */
function exact(x: number): { negative: boolean; num: bigint; den: bigint } {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, x);
  const hi = view.getUint32(0);
  const lo = view.getUint32(4);
  const negative = hi >>> 31 === 1;
  const biased = (hi >>> 20) & 0x7ff;
  let mantissa = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let power: number;
  if (biased === 0) {
    power = -1074; // subnormal
  } else {
    mantissa |= 1n << 52n;
    power = biased - 1075;
  }
  return power >= 0
    ? { negative, num: mantissa << BigInt(power), den: 1n }
    : { negative, num: mantissa, den: 1n << BigInt(-power) };
}

/** num / den to the nearest integer, an exact half to the even one. */
function roundHalfEven(num: bigint, den: bigint): bigint {
  const q = num / den;
  const twice = (num % den) * 2n;
  if (twice > den) return q + 1n;
  if (twice < den) return q;
  return q % 2n === 0n ? q : q + 1n;
}

function special(x: number): string | null {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  return null;
}

/** Python's `f"{x:.{digits}f}"`. */
export function fixed(x: number, digits: number): string {
  const s = special(x);
  if (s !== null) return s;
  const { negative, num, den } = exact(x);
  const n = roundHalfEven(num * 10n ** BigInt(digits), den);
  let text = n.toString().padStart(digits + 1, "0");
  if (digits > 0) text = `${text.slice(0, -digits)}.${text.slice(-digits)}`;
  return negative ? `-${text}` : text;
}

/** The significant digits and power of ten of |x| to `digits + 1` figures. */
function scientific(x: number, digits: number): { negative: boolean; figures: string; power: number } {
  const { negative, num, den } = exact(x);
  if (num === 0n) return { negative, figures: "0".repeat(digits + 1), power: 0 };
  // The power of ten of |x|, from an estimate made exact by comparison.
  let power = Math.floor(Math.log10(Math.abs(x)));
  const atLeast = (p: number): boolean =>
    p >= 0 ? num >= den * 10n ** BigInt(p) : num * 10n ** BigInt(-p) >= den;
  while (!atLeast(power)) power -= 1;
  while (atLeast(power + 1)) power += 1;
  const shift = digits - power;
  let n =
    shift >= 0
      ? roundHalfEven(num * 10n ** BigInt(shift), den)
      : roundHalfEven(num, den * 10n ** BigInt(-shift));
  if (n === 10n ** BigInt(digits + 1)) {
    // 9.995 to three figures is 1.00e+01.
    n /= 10n;
    power += 1;
  }
  return { negative, figures: n.toString(), power };
}

function exponent(power: number): string {
  return `e${power < 0 ? "-" : "+"}${String(Math.abs(power)).padStart(2, "0")}`;
}

/** Python's `f"{x:.{digits}e}"`. */
export function sci(x: number, digits: number): string {
  const s = special(x);
  if (s !== null) return s;
  const { negative, figures, power } = scientific(x, digits);
  const mantissa = digits > 0 ? `${figures[0]}.${figures.slice(1)}` : figures;
  return `${negative ? "-" : ""}${mantissa}${exponent(power)}`;
}

/** Python's `f"{x:.{precision}g}"`. */
export function general(x: number, precision: number): string {
  const s = special(x);
  if (s !== null) return s;
  const p = Math.max(precision, 1);
  const { negative, figures, power } = scientific(x, p - 1);
  const sign = negative ? "-" : "";
  const trim = (t: string): string => (t.includes(".") ? t.replace(/\.?0+$/, "") : t);
  if (power < -4 || power >= p) {
    const mantissa = trim(p > 1 ? `${figures[0]}.${figures.slice(1)}` : figures);
    return `${sign}${mantissa}${exponent(power)}`;
  }
  // Fixed notation, from the same rounded figures: p - 1 - power decimals.
  let text: string;
  if (power >= 0) {
    const whole = figures.slice(0, power + 1);
    const rest = figures.slice(power + 1);
    text = rest ? `${whole}.${rest}` : whole;
  } else {
    text = `0.${"0".repeat(-power - 1)}${figures}`;
  }
  return `${sign}${trim(text)}`;
}
