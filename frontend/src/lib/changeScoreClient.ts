import type { ChangeMetric, ChangeReference, ChangeScoresResponse } from "../types";
import { loadDemoChangeScores } from "./demoData";

const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type CacheKey = string;
const cache = new Map<CacheKey, ChangeScoresResponse>();

function keyOf(p: {
  ra: number;
  dec: number;
  radius: number;
  metric: ChangeMetric;
  reference: ChangeReference;
  target?: string;
}): CacheKey {
  return [
    p.target ?? "",
    p.ra.toFixed(6),
    p.dec.toFixed(6),
    p.radius,
    p.metric,
    p.reference,
  ].join("|");
}

async function fetchJson(url: string, timeoutMs = 4000): Promise<unknown> {
  const ctrl = new AbortController();
  const t = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  } finally {
    window.clearTimeout(t);
  }
}

/** Prefer demo cache for known targets (offline-safe), then API. */
export async function loadChangeScores(p: {
  ra: number;
  dec: number;
  radius: number;
  metric: ChangeMetric;
  reference: ChangeReference;
  target?: string;
}): Promise<ChangeScoresResponse> {
  const k = keyOf(p);
  const hit = cache.get(k);
  if (hit) return hit;

  if (p.target) {
    const demo = await loadDemoChangeScores(p.target, p);
    if (demo) {
      cache.set(k, demo);
      return demo;
    }
  }

  const q = new URLSearchParams({
    ra: String(p.ra),
    dec: String(p.dec),
    radius: String(p.radius),
    metric: p.metric,
    reference: p.reference,
  });
  if (p.target) q.set("target", p.target);

  try {
    const data = (await fetchJson(
      `${API}/api/change-scores?${q}`,
      5000,
    )) as ChangeScoresResponse;
    if (data?.frames) {
      cache.set(k, data);
      return data;
    }
  } catch {
    /* fall through */
  }

  throw new Error("change scores unavailable");
}

export function clearChangeScoreCache(): void {
  cache.clear();
}
