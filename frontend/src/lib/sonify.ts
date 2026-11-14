/** Spectrum sonification (not a real telescope sound). */

export interface SonifyPoint {
  wavelength_um: number;
  flux: number;
}

export function describeSonification(points: SonifyPoint[]): string {
  if (!points.length) return "No spectrum loaded to sonify.";
  const sorted = [...points].sort((a, b) => a.wavelength_um - b.wavelength_um);
  const lo = sorted[0].wavelength_um;
  const hi = sorted[sorted.length - 1].wavelength_um;
  return (
    `Sonification: true wavelength ${lo.toFixed(2)}–${hi.toFixed(2)} µm mapped to pitch ` +
    `(not point index); flux mapped to volume. Auditory display only — not a physical sky sound. ` +
    `${sorted.length} points.`
  );
}

export async function playSpectrum(
  points: SonifyPoint[],
  opts: { volume?: number; durationSec?: number; signal?: AbortSignal } = {},
): Promise<void> {
  const valid = points.filter((p) => Number.isFinite(p.flux) && Number.isFinite(p.wavelength_um));
  if (!valid.length) return;
  const volume = opts.volume ?? 0.2;
  const sorted = [...valid].sort((a, b) => a.wavelength_um - b.wavelength_um);
  const durationSec = opts.durationSec ?? Math.min(8, Math.max(2, sorted.length * 0.45));
  const ctx = new AudioContext();
  let closed = false;
  const closeOnce = async () => {
    if (closed) return;
    closed = true;
    try {
      await ctx.close();
    } catch {
      /* already closed */
    }
  };

  const gain = ctx.createGain();
  gain.gain.value = volume;
  gain.connect(ctx.destination);

  const fluxes = sorted.map((p) => p.flux);
  const fmin = Math.min(...fluxes);
  const fmax = Math.max(...fluxes);
  const fluxSpan = fmax - fmin || 1;
  const w0 = sorted[0].wavelength_um;
  const w1 = sorted[sorted.length - 1].wavelength_um;
  const wSpan = w1 - w0 || 1;
  const t0 = ctx.currentTime;
  const dt = durationSec / sorted.length;

  for (let i = 0; i < sorted.length; i++) {
    if (opts.signal?.aborted) break;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    // Map true wavelength → pitch (2 octaves across λ range)
    const wFrac = (sorted[i].wavelength_um - w0) / wSpan;
    const freq = 220 * Math.pow(2, wFrac * 2);
    const amp = volume * (0.05 + 0.95 * ((sorted[i].flux - fmin) / fluxSpan));
    if (!Number.isFinite(freq) || !Number.isFinite(amp)) continue;
    osc.frequency.value = freq;
    osc.type = "sine";
    g.gain.value = 0;
    osc.connect(g);
    g.connect(gain);
    const start = t0 + i * dt;
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(Math.max(amp, 0), start + 0.02);
    g.gain.linearRampToValueAtTime(0, start + dt * 0.9);
    osc.start(start);
    osc.stop(start + dt);
  }

  await new Promise<void>((resolve) => {
    const id = window.setTimeout(() => resolve(), durationSec * 1000 + 100);
    opts.signal?.addEventListener("abort", () => {
      window.clearTimeout(id);
      void closeOnce();
      resolve();
    });
  });
  await closeOnce();
}
