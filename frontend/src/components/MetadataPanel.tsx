import type { CutoutFrame } from "../types";

export function MetadataPanel({ frame, source }: { frame?: CutoutFrame; source?: string }) {
  if (!frame) return <aside className="panel">No frame selected.</aside>;
  const flags = frame.flag_summary ?? {};
  const top = Object.entries(flags)
    .filter(([k, v]) => k !== "total_pixels" && v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  return (
    <aside className="panel" aria-label="Data provenance">
      <h2>Data</h2>
      <p className="hint">
        Provenance for the pixels on screen — proves archive origin when float arrays are present.
      </p>
      <dl>
        <dt>Source</dt>
        <dd>{source ?? "—"}</dd>
        <dt>Archive collection</dt>
        <dd>{frame.collection ?? "see manifest / SIA"}</dd>
        <dt>Observation ID</dt>
        <dd className="mono">{frame.obs_id || "—"}</dd>
        <dt>Detector / bandpass</dt>
        <dd>
          D{frame.detector} · {frame.bandpass}
        </dd>
        <dt>Native pixel scale</dt>
        <dd>6.15″/pix (SPHEREx Spectral Image)</dd>
        <dt>Array shape / dtype</dt>
        <dd>
          {frame.float_shape
            ? `${frame.float_shape[0]}×${frame.float_shape[1]}`
            : "PNG display only"}{" "}
          · {frame.native_dtype ?? "uint8 PNG"}
        </dd>
        <dt>Units (BUNIT)</dt>
        <dd>{frame.bunit ?? "MJy/sr (IMAGE) — no uncertainty on display stretch"}</dd>
        <dt>Epoch</dt>
        <dd>{frame.time_iso || `MJD ${frame.mjd}`}</dd>
        <dt>λ (target pixel)</dt>
        <dd>
          {frame.central_wavelength_um != null
            ? `${frame.central_wavelength_um.toFixed(3)} µm`
            : "not available"}
        </dd>
        <dt>PNG gray levels (if thumbnail)</dt>
        <dd>
          {frame.png_unique_gray_levels != null
            ? `${frame.png_unique_gray_levels} unique 8-bit values (lossy vs float IMAGE)`
            : "—"}
        </dd>
        <dt>Float array URL</dt>
        <dd className="mono">{frame.float_bin ?? "not packed for this frame"}</dd>
      </dl>
      <h3>Contamination / quality flags</h3>
      <p className="hint">
        FLAGS bitmask counts (Explanatory Supplement). Masked pixels render hatched, not black.
      </p>
      <ul>
        {top.length === 0 && <li>No flagged pixels summarized.</li>}
        {top.map(([k, v]) => (
          <li key={k}>
            {k}: {v}
          </li>
        ))}
      </ul>
      <p className="hint" role="note">
        Legend: magenta hatch = flagged or NaN; grayscale = stretched IMAGE (− ZODI when applied
        upstream).
      </p>
    </aside>
  );
}
