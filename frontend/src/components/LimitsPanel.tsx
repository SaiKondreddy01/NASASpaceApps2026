export function LimitsPanel() {
  return (
    <section className="panel" aria-label="Detection limits">
      <h2>What SkyFlip cannot (yet) detect</h2>
      <ul>
        <li>Objects too faint against zodiacal background / SPHEREx depth.</li>
        <li>Motion much smaller than ~1 native pixel (6.15″) between visits.</li>
        <li>Sources in crowded fields where blending dominates.</li>
        <li>Pixels dominated by FLAGS (TRANSIENT, HALO, DICHROIC, NONFUNC, …).</li>
        <li>Brightness changes from LVF wavelength mismatch mistaken as motion.</li>
      </ul>
      <p className="hint">
        SPHEREx Level-2 IMAGE is MJy/sr and does not have ZODI subtracted. We never claim Planet X
        discoveries — only candidates with uncertainties when available.
      </p>
    </section>
  );
}
