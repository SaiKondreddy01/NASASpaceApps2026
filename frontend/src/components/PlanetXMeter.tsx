import { useMemo, useState } from "react";
import {
  PIXEL_SCALE_ARCSEC,
  arcsecToSpherexPixels,
  maxShiftSixMonthArcsec,
  reflectedLightRelative,
} from "../lib/motionMath";

export function PlanetXMeter() {
  const [d, setD] = useState(400);
  const [r, setR] = useState(1);
  const [a, setA] = useState(0.5);

  const stats = useMemo(() => {
    const shift = maxShiftSixMonthArcsec(d);
    const pix = arcsecToSpherexPixels(shift);
    const bright = reflectedLightRelative({ distanceAu: d, radiusEarth: r, albedo: a });
    return { shift, pix, bright };
  }, [d, r, a]);

  return (
    <section className="panel" aria-label="Planet X reach meter">
      <h2>Planet X reach meter</h2>
      <p className="hint">
        Illustrative only — assumptions shown. Motion is easy at these distances; brightness is the hard
        part. Not a search result.
      </p>
      <label>
        Distance {d} AU
        <input type="range" min={50} max={1000} value={d} onChange={(e) => setD(Number(e.target.value))} />
      </label>
      <label>
        Radius {r} R⊕
        <input type="range" min={0.2} max={5} step={0.1} value={r} onChange={(e) => setR(Number(e.target.value))} />
      </label>
      <label>
        Albedo {a.toFixed(2)}
        <input type="range" min={0.05} max={0.9} step={0.05} value={a} onChange={(e) => setA(Number(e.target.value))} />
      </label>
      <dl>
        <dt>Max ~6-month shift</dt>
        <dd>
          {stats.shift.toFixed(2)}″ ≈ {stats.pix.toFixed(2)} SPHEREx pixels ({PIXEL_SCALE_ARCSEC}″/pix)
        </dd>
        <dt>Reflected-light factor</dt>
        <dd>
          {stats.bright.toExponential(2)}× vs 100 AU Earth/albedo-0.5 reference (∝ R²A/d⁴) — illustrative
        </dd>
      </dl>
      <p>
        <strong>Honest takeaway:</strong> parallax/motion is measurable in SPHEREx pixels at hundreds of AU;
        reflected sunlight falls as d⁻⁴, so brightness — not motion — is the bottleneck. Depth comparison
        needs verified SPHEREx sensitivity from the Explanatory Supplement (see SCIENCE_LIMITS.md).
      </p>
    </section>
  );
}
