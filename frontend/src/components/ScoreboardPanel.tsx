import { useEffect, useState } from "react";
import { api } from "../lib/api";

function numOrPending(v: unknown): string {
  if (v === null || v === undefined) return "not computed yet";
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return "not computed yet";
}

export function ScoreboardPanel() {
  const [data, setData] = useState<{
    results: Record<string, unknown>;
    explanation: string;
    source: string;
  } | null>(null);
  const [err, setErr] = useState("");
  const [cachedBanner, setCachedBanner] = useState(false);

  useEffect(() => {
    api
      .scoreboard()
      .then(setData)
      .catch(async () => {
        try {
          const r = await fetch("/demo-data/scoreboard.json");
          if (!r.ok) throw new Error("scoreboard unavailable");
          const results = await r.json();
          setCachedBanner(true);
          setData({
            results,
            explanation:
              "Using cached demo scoreboard.json (API unreachable). Candidates only — not a discovery claim.",
            source: "cached-demo",
          });
        } catch (e) {
          setErr(String(e));
        }
      });
  }, []);

  const field = (data?.results?.field_validation ?? {}) as Record<string, unknown>;
  const selfTest = (data?.results?.motion_fit_self_test ?? {}) as Record<string, unknown>;
  const synth = (data?.results?.synthetic ?? {}) as Record<string, unknown>;
  const sample = (field.sample_size ?? {}) as Record<string, unknown>;
  const status = String(field.status ?? "");

  return (
    <section className="panel" aria-label="Validation scoreboard">
      <h2>Validation scoreboard</h2>
      {err && <p className="error">{err}</p>}
      {cachedBanner && (
        <p className="badge" role="status">
          using cached demo data
        </p>
      )}
      {!data ? (
        <p>Loading…</p>
      ) : (
        <>
          <p>{data.explanation}</p>
          <p className="hint">
            Data source: {data.source}
            {field.method ? ` · Method: ${String(field.method)}` : ""}
          </p>
          <p className="hint">
            Sample size:{" "}
            {sample.n_measured != null
              ? `${sample.n_measured} measured / ${sample.n_targets_attempted ?? "?"} attempted` +
                (sample.n_frames_total != null ? ` · ${sample.n_frames_total} frames` : "")
              : "not computed yet"}
            {field.match_radius_arcsec != null
              ? ` · match radius ${String(field.match_radius_arcsec)}″`
              : ""}
          </p>
          {status === "not computed yet" ? (
            <p className="hint" role="status">
              Field recovery: not computed yet — {String(field.note ?? "")}
            </p>
          ) : (
            <div className="score-grid">
              <div>
                <div className="num">{numOrPending(field.n_recovered)}</div>
                <div>recovered</div>
              </div>
              <div>
                <div className="num">{numOrPending(field.n_missed)}</div>
                <div>missed</div>
              </div>
              <div>
                <div className="num">{numOrPending(field.n_false_candidates)}</div>
                <div>false candidates</div>
              </div>
              <div>
                <div className="num">
                  {field.recovery_rate != null && typeof field.recovery_rate === "number"
                    ? `${(field.recovery_rate * 100).toFixed(0)}%`
                    : "not computed yet"}
                </div>
                <div>recovery rate</div>
              </div>
            </div>
          )}
          <p className="hint">{String(field.misses_explained ?? "")}</p>
          {Array.isArray(field.misses) && field.misses.length > 0 && (
            <details>
              <summary>Misses detail</summary>
              <pre className="hint">{JSON.stringify(field.misses, null, 2)}</pre>
            </details>
          )}
          {Array.isArray(field.per_target) && (
            <details>
              <summary>Per-target measurements</summary>
              <pre className="hint">{JSON.stringify(field.per_target, null, 2)}</pre>
            </details>
          )}
          <h3>Synthetic injection</h3>
          <p className="badge synth" role="status">
            SIMULATED / TEST DATA
          </p>
          <p className="hint">
            {String(synth.method ?? synth.note ?? "not computed yet")}
            {synth.sample_size
              ? ` · sample ${JSON.stringify(synth.sample_size)}`
              : ""}
            {synth.recovery_rate != null && typeof synth.recovery_rate === "number"
              ? ` · recovery ${(synth.recovery_rate * 100).toFixed(0)}%`
              : ""}
          </p>
          {Array.isArray(synth.bins) && synth.bins.length > 0 ? (
            <ul className="hint">
              {(synth.bins as Record<string, unknown>[]).map((b, i) => (
                <li key={i}>
                  {String(b.brightness)} · speed {String(b.speed_arcsec_yr ?? "—")}″/yr ·{" "}
                  {b.recovered ? "recovered" : "missed"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Synthetic bins: not computed yet</p>
          )}
          <h3>Motion-fit self-test</h3>
          <p>
            Synthetic track recovered: {selfTest.ok ? "yes" : "no"} (truth μ≈
            {String(selfTest.truth_pm_ra)}/{String(selfTest.truth_pm_dec)} ″/yr; fit{" "}
            {typeof selfTest.fit_pm_ra === "number"
              ? selfTest.fit_pm_ra.toFixed(1)
              : "—"}
            /
            {typeof selfTest.fit_pm_dec === "number"
              ? selfTest.fit_pm_dec.toFixed(1)
              : "—"}{" "}
            ±
            {selfTest.fit_pm_ra_err != null
              ? Number(selfTest.fit_pm_ra_err).toFixed(1)
              : "no uncertainty available"}
            ). <span className="badge synth">is_synthetic</span>
          </p>
        </>
      )}
    </section>
  );
}
