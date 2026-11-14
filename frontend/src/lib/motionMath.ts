/** Illustrative Planet X reach estimates. Marked as assumptions in UI. */

export const PIXEL_SCALE_ARCSEC = 6.15;

/** Parallax semi-amplitude ≈ 206265 / d arcsec for distance d in AU. */
export function parallaxSemiAmplitudeArcsec(distanceAu: number): number {
  if (distanceAu <= 0) return Infinity;
  return 206265 / distanceAu;
}

/** Max shift over ~6-month baseline up to ~2× parallax (geometry-dependent). */
export function maxShiftSixMonthArcsec(distanceAu: number): number {
  return 2 * parallaxSemiAmplitudeArcsec(distanceAu);
}

export function arcsecToSpherexPixels(arcsec: number): number {
  return arcsec / PIXEL_SCALE_ARCSEC;
}

/**
 * Rough reflected-light brightness scale ∝ R² A / d⁴ (illustrative).
 * Returns relative factor vs a reference at 100 AU, R=Earth, A=0.5.
 */
export function reflectedLightRelative(opts: {
  distanceAu: number;
  radiusEarth: number;
  albedo: number;
}): number {
  const ref = Math.pow(1, 2) * 0.5 / Math.pow(100, 4);
  const val =
    Math.pow(opts.radiusEarth, 2) * opts.albedo / Math.pow(Math.max(opts.distanceAu, 1), 4);
  return val / ref;
}
