import type {
  ChangeMetric,
  ChangeReference,
  ChangeScoresResponse,
  CutoutFrame,
  CutoutsResponse,
} from "../types";

export async function loadDemoCutouts(targetId: string): Promise<CutoutsResponse | null> {
  try {
    const r = await fetch(`/demo-data/${targetId}/manifest.json`);
    if (!r.ok) return null;
    const man = await r.json();
    const frames: CutoutFrame[] = (man.frames ?? []).map((f: Record<string, unknown>) => ({
      epoch_id: String(f.epoch_id),
      obs_id: String(f.obs_id ?? ""),
      mjd: Number(f.mjd),
      time_iso: String(f.time_iso ?? ""),
      bandpass: String(f.bandpass ?? "SPHEREx-D1"),
      detector: Number(f.detector ?? 1),
      image_url: `/demo-data/${targetId}/${f.png}`,
      central_wavelength_um: f.central_wavelength_um as number | undefined,
      flag_summary: (f.flag_summary as Record<string, number>) ?? {},
      is_synthetic: Boolean(man.is_synthetic),
      float_bin: f.float_bin ? `/demo-data/${targetId}/${f.float_bin}` : undefined,
      float_shape: f.float_shape as [number, number] | undefined,
      flags_bin: f.flags_bin ? `/demo-data/${targetId}/${f.flags_bin}` : undefined,
      bunit: f.bunit as string | undefined,
      collection: f.collection as string | undefined,
      native_dtype: f.native_dtype as string | undefined,
      png_unique_gray_levels: f.png_unique_gray_levels as number | undefined,
    }));
    return {
      ra: man.ra,
      dec: man.dec,
      fov_deg: man.fov_deg ?? 0.05,
      frames,
      source: "cached-demo",
      pixel_scale_arcsec: man.pixel_scale_arcsec ?? 6.15,
      note: "Using cached demo data",
    };
  } catch {
    return null;
  }
}

/** Offline change scores from precomputed demo JSON (no backend required). */
export async function loadDemoChangeScores(
  targetId: string,
  opts: {
    ra: number;
    dec: number;
    radius: number;
    metric: ChangeMetric;
    reference: ChangeReference;
  },
): Promise<ChangeScoresResponse | null> {
  try {
    const r = await fetch(`/demo-data/${targetId}/change_scores.json`);
    if (!r.ok) return null;
    const cached = await r.json();
    const key = `${opts.metric}|${opts.reference}|${opts.radius}`;
    const payload = cached.by_key?.[key] ?? cached.default;
    if (!payload?.frames) return null;
    return {
      ra: opts.ra,
      dec: opts.dec,
      radius_pix: opts.radius,
      metric: opts.metric,
      reference: opts.reference,
      frames: payload.frames,
      motion: payload.motion ?? {},
      source: "cached-demo",
      pixel_scale_arcsec: 6.15,
      aperture_x_pix: payload.aperture_x_pix,
      aperture_y_pix: payload.aperture_y_pix,
      is_synthetic: Boolean(payload.is_synthetic),
      banner: "using cached demo data",
      metric_note:
        payload.note ??
        "Change = difference from reference in the aperture (candidates only).",
    };
  } catch {
    return null;
  }
}
