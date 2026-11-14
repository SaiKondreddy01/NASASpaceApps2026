/** Client-side display stretch for float SPHEREx cutouts. */

export type StretchMode = "linear" | "log" | "asinh";

export function percentileClip(data: Float32Array, lo: number, hi: number): [number, number] {
  const finite = Array.from(data).filter((v) => Number.isFinite(v));
  if (!finite.length) return [0, 1];
  finite.sort((a, b) => a - b);
  const at = (p: number) => finite[Math.min(finite.length - 1, Math.floor((p / 100) * finite.length))];
  return [at(lo), at(hi)];
}

export function stretchToRgba(
  data: Float32Array,
  width: number,
  height: number,
  opts: {
    mode: StretchMode;
    vmin: number;
    vmax: number;
    flags?: Uint16Array | null;
  },
): ImageData {
  const { mode, vmin, vmax, flags } = opts;
  const out = new ImageData(width, height);
  const span = Math.max(vmax - vmin, 1e-12);
  for (let i = 0; i < data.length; i++) {
    const v = data[i];
    const o = i * 4;
    const flagged = flags ? flags[i] !== 0 : false;
    const bad = !Number.isFinite(v);
    if (bad || flagged) {
      // Hatched-ish magenta/gray for masked/NaN — not a black hole
      const hatch = ((i % width) + Math.floor(i / width)) % 4 === 0;
      out.data[o] = hatch ? 180 : 40;
      out.data[o + 1] = hatch ? 60 : 40;
      out.data[o + 2] = hatch ? 160 : 50;
      out.data[o + 3] = flagged || bad ? 200 : 255;
      continue;
    }
    let x = Math.min(Math.max(v, vmin), vmax);
    let y: number;
    if (mode === "linear") y = (x - vmin) / span;
    else if (mode === "log") y = Math.log1p(x - vmin) / Math.log1p(span);
    else {
      y = Math.asinh((x - vmin) / (span / 3)) / Math.asinh(3);
    }
    y = Math.min(Math.max(y, 0), 1);
    const g = Math.round(y * 255);
    out.data[o] = g;
    out.data[o + 1] = g;
    out.data[o + 2] = g;
    out.data[o + 3] = 255;
  }
  return out;
}
