export interface UrlState {
  ra?: number;
  dec?: number;
  fov?: number;
  epoch?: number;
  stretch?: string;
  embed?: boolean;
  demo?: boolean;
  tab?: string;
  target?: string;
  /** Zoom rectangle in native image pixels (common WCS grid). */
  zx0?: number;
  zy0?: number;
  zx1?: number;
  zy1?: number;
  /** Change slider */
  cmin?: number;
  cmax?: number;
  cmetric?: string;
  cref?: string;
  cap?: number;
  csort?: string;
  cra?: number;
  cdec?: number;
}

export function readUrlState(): UrlState {
  const p = new URLSearchParams(window.location.search);
  const num = (k: string) => {
    const v = p.get(k);
    return v != null && v !== "" ? Number(v) : undefined;
  };
  return {
    ra: num("ra"),
    dec: num("dec"),
    fov: num("fov"),
    epoch: num("epoch"),
    stretch: p.get("stretch") ?? undefined,
    embed: p.get("embed") === "1",
    demo: p.get("demo") === "1",
    tab: p.get("tab") ?? undefined,
    target: p.get("target") ?? undefined,
    zx0: num("zx0"),
    zy0: num("zy0"),
    zx1: num("zx1"),
    zy1: num("zy1"),
    cmin: num("cmin"),
    cmax: num("cmax"),
    cmetric: p.get("cmetric") ?? undefined,
    cref: p.get("cref") ?? undefined,
    cap: num("cap"),
    csort: p.get("csort") ?? undefined,
    cra: num("cra"),
    cdec: num("cdec"),
  };
}

export function writeUrlState(state: UrlState): void {
  const p = new URLSearchParams(window.location.search);
  const set = (k: string, v: string | number | boolean | undefined) => {
    if (v === undefined || v === false || v === "") p.delete(k);
    else p.set(k, String(v === true ? "1" : v));
  };
  set("ra", state.ra);
  set("dec", state.dec);
  set("fov", state.fov);
  set("epoch", state.epoch);
  set("stretch", state.stretch);
  set("embed", state.embed);
  set("demo", state.demo);
  set("tab", state.tab);
  set("target", state.target);
  set("zx0", state.zx0);
  set("zy0", state.zy0);
  set("zx1", state.zx1);
  set("zy1", state.zy1);
  set("cmin", state.cmin);
  set("cmax", state.cmax);
  set("cmetric", state.cmetric);
  set("cref", state.cref);
  set("cap", state.cap);
  set("csort", state.csort);
  set("cra", state.cra);
  set("cdec", state.cdec);
  const qs = p.toString();
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  window.history.replaceState({}, "", url);
}

export function shareUrl(state: UrlState): string {
  const u = new URL(window.location.href);
  const next = { ...readUrlState(), ...state };
  writeUrlState(next);
  const params: Record<string, string> = {};
  if (next.ra != null) params.ra = String(next.ra);
  if (next.dec != null) params.dec = String(next.dec);
  if (next.fov != null) params.fov = String(next.fov);
  if (next.stretch) params.stretch = next.stretch;
  if (next.target) params.target = next.target;
  if (next.zx0 != null) params.zx0 = String(next.zx0);
  if (next.zy0 != null) params.zy0 = String(next.zy0);
  if (next.zx1 != null) params.zx1 = String(next.zx1);
  if (next.zy1 != null) params.zy1 = String(next.zy1);
  if (next.cmetric) params.cmetric = next.cmetric;
  if (next.cref) params.cref = next.cref;
  if (next.cap != null) params.cap = String(next.cap);
  if (next.csort) params.csort = next.csort;
  if (next.cmin != null) params.cmin = String(next.cmin);
  if (next.cmax != null) params.cmax = String(next.cmax);
  return u.origin + u.pathname + "?" + new URLSearchParams(params).toString();
}

export function viewFromUrl(state: UrlState): {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
} | null {
  if (
    state.zx0 == null ||
    state.zy0 == null ||
    state.zx1 == null ||
    state.zy1 == null ||
    ![state.zx0, state.zy0, state.zx1, state.zy1].every(Number.isFinite)
  ) {
    return null;
  }
  return { x0: state.zx0, y0: state.zy0, x1: state.zx1, y1: state.zy1 };
}
