import type { MoverCandidate } from "../types";

export function CandidateList({
  movers,
  onSelect,
}: {
  movers: MoverCandidate[];
  onSelect?: (m: MoverCandidate) => void;
}) {
  return (
    <section className="panel" aria-label="Mover candidates">
      <h2>Candidates</h2>
      <p className="hint">Labeled known / candidate / likely_artifact — not discoveries.</p>
      <ul className="cand-list">
        {movers.length === 0 && <li>No movers loaded yet.</li>}
        {movers.map((m) => (
          <li key={m.id}>
            <button type="button" onClick={() => onSelect?.(m)}>
              <strong>{m.id}</strong> · {m.classification}
              {m.is_synthetic && <span className="badge synth">SIMULATED</span>}
            </button>
            <div className="hint">
              μ_α={m.pm_ra_arcsec_yr?.toFixed(1) ?? "n/a"}±{m.pm_ra_err_arcsec_yr?.toFixed(1) ?? "no σ"} ″/yr;{" "}
              μ_δ={m.pm_dec_arcsec_yr?.toFixed(1) ?? "n/a"}±{m.pm_dec_err_arcsec_yr?.toFixed(1) ?? "no σ"} ″/yr
            </div>
            <div className="hint">{m.reasons.join("; ")}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
