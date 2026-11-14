import { useState, type FormEvent } from "react";
import { api } from "../lib/api";

interface Props {
  onGoto: (ra: number, dec: number, name?: string) => void;
}

export function parseCoord(text: string): { ra: number; dec: number } | null {
  const t = text.trim();
  // degrees pair
  const m = t.match(/^([+-]?\d+(?:\.\d+)?)\s*[,\s]\s*([+-]?\d+(?:\.\d+)?)$/);
  if (m) return { ra: Number(m[1]), dec: Number(m[2]) };
  // Colon-separated: 08:55:10.831 -07:14:42.53 (challenge WISE 0855 style)
  const colon = t.match(
    /^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)\s+([+-]?\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$/,
  );
  if (colon) {
    const ra = 15 * (Number(colon[1]) + Number(colon[2]) / 60 + Number(colon[3]) / 3600);
    const sign = colon[4].startsWith("-") ? -1 : 1;
    const dec =
      sign * (Math.abs(Number(colon[4])) + Number(colon[5]) / 60 + Number(colon[6]) / 3600);
    return { ra, dec };
  }
  // sexagesimal RA Dec (hms dms)
  const sex = t.match(
    /^(\d+)[h\s]+(\d+)[m\s]+(\d+(?:\.\d+)?)[s]?\s+([+-]?\d+)[d°\s]+(\d+)[m'\s]+(\d+(?:\.\d+)?)/i,
  );
  if (sex) {
    const ra = 15 * (Number(sex[1]) + Number(sex[2]) / 60 + Number(sex[3]) / 3600);
    const sign = sex[4].startsWith("-") ? -1 : 1;
    const dec =
      sign * (Math.abs(Number(sex[4])) + Number(sex[5]) / 60 + Number(sex[6]) / 3600);
    return { ra, dec };
  }
  return null;
}

export function SearchBar({ onGoto }: Props) {
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    const parsed = parseCoord(q);
    if (parsed) {
      onGoto(parsed.ra, parsed.dec);
      return;
    }
    setBusy(true);
    try {
      const r = await api.resolve(q);
      onGoto(r.ra, r.dec, r.name);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Resolve failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="search" onSubmit={submit} aria-label="Sky search">
      <label htmlFor="sky-q">Coordinates or name</label>
      <div className="row">
        <input
          id="sky-q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="RA, Dec or object name"
          aria-describedby="sky-help"
        />
        <button type="submit" disabled={busy}>
          {busy ? "…" : "Go"}
        </button>
      </div>
      <p id="sky-help" className="hint">
        Degrees (133.8, -7.25), colons (08:55:10.831 -07:14:42.53), sexagesimal
        (08h55m10.8s -7d14m42.5s), or a name via Sesame/SIMBAD.
      </p>
      {err && <p className="error" role="alert">{err}</p>}
    </form>
  );
}
