import { TEST_TARGETS } from "../types";

const BLURBS: Record<string, string> = {
  wise0855: "Fast-moving Y dwarf — the blink hop is the demo hook.",
  barnards_star: "Highest proper-motion star; ghost track should nearly match.",
  epsilon_indi_b: "Brown-dwarf companion system near a bright star.",
  rw_aurigae: "Variable star — brightness changes, position mostly fixed.",
  r_draconis: "Another variable to contrast with true movers.",
};

export function SkyTour({ onPick }: { onPick: (id: string) => void }) {
  return (
    <section className="panel" aria-label="Sky tour">
      <h2>Sky tour</h2>
      <ul>
        {TEST_TARGETS.map((t) => (
          <li key={t.id}>
            <button type="button" onClick={() => onPick(t.id)}>
              {t.name}
            </button>
            — {BLURBS[t.id] ?? "Curated starting field."}
          </li>
        ))}
      </ul>
    </section>
  );
}
