import { useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  ChangeMetric,
  ChangeReference,
  ChangeScoreFrame,
  ChangeScoresResponse,
  ChangeSortMode,
} from "../types";
import {
  biggestN,
  filterByRange,
  orderFrames,
  scoreExtents,
  scoreMagnitude,
} from "../lib/changeScoreMath";

interface Props {
  scores: ChangeScoresResponse | null;
  loading?: boolean;
  metric: ChangeMetric;
  reference: ChangeReference;
  aperture: number;
  sortMode: ChangeSortMode;
  rangeLo: number | null;
  rangeHi: number | null;
  onMetric: (m: ChangeMetric) => void;
  onReference: (r: ChangeReference) => void;
  onAperture: (r: number) => void;
  onSortMode: (s: ChangeSortMode) => void;
  onRange: (lo: number, hi: number) => void;
  onKeptEpochIds: (ids: string[]) => void;
  onJumpToEpochId: (epochId: string) => void;
  onPickMode?: (on: boolean) => void;
  pickMode?: boolean;
}

const METRIC_LABEL: Record<ChangeMetric, string> = {
  brightness_snr: "brightness change (S/N)",
  position_shift: "position shift (arcsec)",
  combined: "combined",
};

export function ChangeSlider({
  scores,
  loading,
  metric,
  reference,
  aperture,
  sortMode,
  rangeLo,
  rangeHi,
  onMetric,
  onReference,
  onAperture,
  onSortMode,
  onRange,
  onKeptEpochIds,
  onJumpToEpochId,
  onPickMode,
  pickMode,
}: Props) {
  const baseId = useId();
  const frames = scores?.frames ?? [];
  const extents = useMemo(() => scoreExtents(frames), [frames]);
  const [lo, setLo] = useState(rangeLo ?? extents.min);
  const [hi, setHi] = useState(rangeHi ?? extents.max);
  const [topN, setTopN] = useState(3);
  const [hover, setHover] = useState<ChangeScoreFrame | null>(null);
  const announceRef = useRef<HTMLDivElement>(null);

  // Sync extents when scores reload
  useEffect(() => {
    if (rangeLo != null && rangeHi != null) {
      setLo(rangeLo);
      setHi(rangeHi);
    } else {
      setLo(extents.min);
      setHi(extents.max);
    }
  }, [extents.min, extents.max, rangeLo, rangeHi, scores?.ra, scores?.dec, metric, reference]);

  const kept = useMemo(() => {
    const filtered = filterByRange(frames, Math.min(lo, hi), Math.max(lo, hi));
    return orderFrames(filtered, sortMode);
  }, [frames, lo, hi, sortMode]);

  useEffect(() => {
    onKeptEpochIds(kept.map((f) => f.epoch_id));
  }, [kept, onKeptEpochIds]);

  useEffect(() => {
    const msg = `showing ${kept.length} of ${frames.length} frames`;
    if (announceRef.current) announceRef.current.textContent = msg;
  }, [kept.length, frames.length]);

  const maxBar = Math.max(extents.max, 1e-6);
  const unit =
    frames.find((f) => f.score_unit)?.score_unit ??
    (metric === "position_shift" ? "arcsec" : "dimensionless (S/N)");

  const whyFiltered = (f: ChangeScoreFrame): string => {
    const m = scoreMagnitude(f);
    if (f.status === "not_computed") {
      return `not computed: ${f.status_reason || "no score"} · masked ${f.n_masked}/${f.n_aperture_pixels}`;
    }
    if (m == null) return "not computed";
    const inRange = m >= Math.min(lo, hi) && m <= Math.max(lo, hi);
    if (inRange) {
      return `kept: |score|=${m.toFixed(2)} ± ${f.score_err ?? "n/a"} ${unit}; masked ${f.n_masked}/${f.n_aperture_pixels}`;
    }
    return `filtered: |score|=${m.toFixed(2)} outside [${Math.min(lo, hi).toFixed(2)}, ${Math.max(lo, hi).toFixed(2)}]; masked ${f.n_masked}/${f.n_aperture_pixels}`;
  };

  return (
    <section className="change-slider panel" aria-label="Change slider" data-testid="change-slider">
      <h2>Change slider</h2>
      <p className="hint">
        Filters blink frames by how much this position differs from the reference —{" "}
        <strong>candidates only</strong>, not a discovery. Metric: aperture residual S/N with
        annulus background; see docs/SCIENCE_LIMITS.md. Unit: {unit}.
      </p>
      {scores?.banner && (
        <p className="banner-cached" role="status">
          {scores.banner}
        </p>
      )}
      {scores?.is_synthetic && (
        <p className="sim-badge" role="status">
          SIMULATED / TEST DATA
        </p>
      )}
      {loading && (
        <p className="hint" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> Computing change scores…
        </p>
      )}

      <div className="row wrap change-controls">
        <label>
          Metric
          <select
            aria-label="Change metric"
            value={metric}
            onChange={(e) => onMetric(e.target.value as ChangeMetric)}
          >
            {(Object.keys(METRIC_LABEL) as ChangeMetric[]).map((k) => (
              <option key={k} value={k}>
                {METRIC_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reference
          <select
            aria-label="Change reference"
            value={reference}
            onChange={(e) => onReference(e.target.value as ChangeReference)}
          >
            <option value="median_others">median of others (λ-matched)</option>
            <option value="first_epoch">first epoch</option>
            <option value="previous_epoch">previous epoch</option>
          </select>
        </label>
        <label>
          Aperture (pix)
          <input
            type="number"
            min={0.5}
            max={6}
            step={0.25}
            value={aperture}
            aria-label="Aperture radius in pixels"
            onChange={(e) => onAperture(Number(e.target.value))}
            style={{ width: "4.5rem" }}
          />
        </label>
        <label>
          Sort
          <select
            aria-label="Change sort mode"
            value={sortMode}
            onChange={(e) => onSortMode(e.target.value as ChangeSortMode)}
          >
            <option value="time">time order</option>
            <option value="change">sorted by change</option>
          </select>
        </label>
        {onPickMode && (
          <label className="check">
            <input
              type="checkbox"
              checked={!!pickMode}
              onChange={(e) => onPickMode(e.target.checked)}
            />
            Pick aperture on image
          </label>
        )}
      </div>

      {sortMode === "change" && (
        <p className="banner-warn" role="status" data-testid="sort-banner">
          frames not in time order
        </p>
      )}

      <div className="change-range" role="group" aria-labelledby={`${baseId}-label`}>
        <div id={`${baseId}-label`} className="change-range-label">
          Change: smallest to biggest
        </div>
        <div className="dual-range">
          <input
            type="range"
            min={extents.min}
            max={extents.max}
            step={(extents.max - extents.min) / 100 || 0.01}
            value={lo}
            aria-label="Minimum change"
            onChange={(e) => {
              const v = Number(e.target.value);
              setLo(v);
              onRange(Math.min(v, hi), Math.max(v, hi));
            }}
            onKeyDown={(e) => {
              if (e.key === "Home") {
                e.preventDefault();
                setLo(extents.min);
                onRange(extents.min, Math.max(extents.min, hi));
              }
              if (e.key === "End") {
                e.preventDefault();
                setLo(extents.max);
                onRange(Math.min(extents.max, hi), Math.max(extents.max, hi));
              }
            }}
          />
          <input
            type="range"
            min={extents.min}
            max={extents.max}
            step={(extents.max - extents.min) / 100 || 0.01}
            value={hi}
            aria-label="Maximum change"
            onChange={(e) => {
              const v = Number(e.target.value);
              setHi(v);
              onRange(Math.min(lo, v), Math.max(lo, v));
            }}
            onKeyDown={(e) => {
              if (e.key === "Home") {
                e.preventDefault();
                setHi(extents.min);
                onRange(Math.min(lo, extents.min), Math.max(lo, extents.min));
              }
              if (e.key === "End") {
                e.preventDefault();
                setHi(extents.max);
                onRange(Math.min(lo, extents.max), extents.max);
              }
            }}
          />
        </div>
        <div className="row wrap" style={{ gap: "0.5rem", alignItems: "center" }}>
          <span className="mono">
            [{Math.min(lo, hi).toFixed(2)}, {Math.max(lo, hi).toFixed(2)}]
          </span>
          <label>
            Biggest N
            <input
              type="number"
              min={1}
              max={Math.max(1, frames.length)}
              value={topN}
              aria-label="Show only the biggest N changes"
              onChange={(e) => setTopN(Number(e.target.value))}
              style={{ width: "3.5rem" }}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              const top = biggestN(frames, topN);
              if (!top.length) return;
              const mags = top.map((f) => scoreMagnitude(f)!);
              const nlo = Math.min(...mags);
              const nhi = Math.max(...mags);
              setLo(nlo);
              setHi(nhi);
              onRange(nlo, nhi);
            }}
          >
            Show only biggest N
          </button>
          <button
            type="button"
            onClick={() => {
              setLo(extents.min);
              setHi(extents.max);
              onRange(extents.min, extents.max);
            }}
          >
            Reset range
          </button>
        </div>
      </div>

      <div
        className="change-hist"
        role="img"
        aria-label={`Change score histogram, showing ${kept.length} of ${frames.length} frames`}
        data-testid="change-histogram"
      >
        {orderFrames(frames, "time").map((f) => {
          const m = scoreMagnitude(f);
          const h = m == null ? 2 : Math.max(4, (m / maxBar) * 48);
          const active = kept.some((k) => k.epoch_id === f.epoch_id);
          const title = [
            f.epoch_id,
            `MJD ${f.mjd.toFixed(3)}`,
            f.wavelength_um != null ? `λ ${f.wavelength_um.toFixed(3)} µm` : null,
            f.detector != null ? `D${f.detector}` : null,
            m == null
              ? "not computed"
              : `score ${f.score!.toFixed(2)} ± ${f.score_err ?? "n/a"} ${unit}`,
            f.wavelength_mismatched ? "wavelength-mismatched" : null,
            whyFiltered(f),
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <button
              key={f.epoch_id}
              type="button"
              className={`hist-bar ${active ? "kept" : "dim"} ${f.status === "not_computed" ? "nc" : ""}`}
              style={{ height: `${h}px` }}
              title={title}
              aria-label={title}
              data-epoch-id={f.epoch_id}
              onMouseEnter={() => setHover(f)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onJumpToEpochId(f.epoch_id)}
            />
          );
        })}
      </div>
      <p className="mono" aria-live="polite" data-testid="change-count">
        showing {kept.length} of {frames.length} frames
      </p>
      <div ref={announceRef} className="sr-only" aria-live="polite" />

      {hover && (
        <p className="hint mono" data-testid="hist-hover">
          {whyFiltered(hover)}
          {hover.score != null && (
            <>
              {" "}
              · raw {hover.score.toFixed(2)}
              {hover.score_err != null
                ? ` ± ${hover.score_err.toFixed(2)}`
                : " (no uncertainty available)"}
            </>
          )}
        </p>
      )}

      {scores?.motion && (
        <div className="motion-summary" data-testid="motion-summary">
          {scores.motion.status === "too_few_points" ? (
            <p className="hint">{String(scores.motion.message ?? "too few points to estimate motion")}</p>
          ) : (
            <p className="hint">
              Trail displacement:{" "}
              {scores.motion.total_displacement_arcsec != null
                ? `${Number(scores.motion.total_displacement_arcsec).toFixed(2)}″ ± ${
                    scores.motion.total_displacement_arcsec_err != null
                      ? Number(scores.motion.total_displacement_arcsec_err).toFixed(2)
                      : "n/a"
                  }″`
                : "not computed"}
              {scores.motion.pm_arcsec_yr != null && (
                <>
                  {" "}
                  · apparent motion {Number(scores.motion.pm_arcsec_yr).toFixed(2)} ±{" "}
                  {scores.motion.pm_arcsec_yr_err != null
                    ? Number(scores.motion.pm_arcsec_yr_err).toFixed(2)
                    : "n/a"}{" "}
                  ″/yr
                </>
              )}
              . {String(scores.motion.uncertainty_note ?? "")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
