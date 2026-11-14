import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AladinOverlay } from "./components/AladinOverlay";
import { Banner } from "./components/Banner";
import { BlinkPlayer } from "./components/BlinkPlayer";
import { CandidateList } from "./components/CandidateList";
import { ChangeSlider } from "./components/ChangeSlider";
import { ClassroomMode } from "./components/ClassroomMode";
import { DiscoveryMode } from "./components/DiscoveryMode";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LimitsPanel } from "./components/LimitsPanel";
import { MetadataPanel } from "./components/MetadataPanel";
import { PlanetXMeter } from "./components/PlanetXMeter";
import { ReportObservation } from "./components/ReportObservation";
import { ScoreboardPanel } from "./components/ScoreboardPanel";
import { SearchBar } from "./components/SearchBar";
import { ShareButton } from "./components/ShareButton";
import { SkyTour } from "./components/SkyTour";
import { SpectrumPanel } from "./components/SpectrumPanel";
import { TargetButtons } from "./components/TargetButtons";
import { api, apiUrl } from "./lib/api";
import { loadChangeScores } from "./lib/changeScoreClient";
import { trailFromScores } from "./lib/changeScoreMath";
import { loadDemoCutouts } from "./lib/demoData";
import type { FrozenReportContext } from "./lib/observationTypes";
import { flushQueue, peekQueue } from "./lib/observationQueue";
import { readUrlState, shareUrl, viewFromUrl, writeUrlState } from "./lib/urlState";
import type { ViewRect } from "./lib/zoomMath";
import type {
  ChangeMetric,
  ChangeReference,
  ChangeScoresResponse,
  ChangeSortMode,
  CutoutsResponse,
  MoverCandidate,
  PredictedTrackPoint,
  SpectrumPoint,
  TrailPoint,
} from "./types";
import { TEST_TARGETS, WISE0855 } from "./types";
import "./App.css";

type Tab = "viewer" | "scoreboard" | "discovery" | "classroom" | "planetx";

export default function App() {
  const initial = readUrlState();
  const reduced = useMemo(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
    []
  );
  const embed = Boolean(initial.embed);
  const [tab, setTab] = useState<Tab>((initial.tab as Tab) || "viewer");
  const [ra, setRa] = useState(initial.ra ?? WISE0855.ra);
  const [dec, setDec] = useState(initial.dec ?? WISE0855.dec);
  const [fov, setFov] = useState(initial.fov ?? 0.2);
  const [targetId, setTargetId] = useState(initial.target ?? "wise0855");
  const [name, setName] = useState("WISE 0855");
  const [cutouts, setCutouts] = useState<CutoutsResponse | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [ghost, setGhost] = useState<PredictedTrackPoint[]>([]);
  const [showGhost, setShowGhost] = useState(true);
  const [movers, setMovers] = useState<MoverCandidate[]>([]);
  const [spectrum, setSpectrum] = useState<SpectrumPoint[]>([]);
  const [specNote, setSpecNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [stack, setStack] = useState<"none" | "detector" | "all_detectors">("none");
  const [detector, setDetector] = useState<number>(1);
  const [targetingMode, setTargetingMode] = useState<"fixed_sky" | "track_target">("fixed_sky");
  const [waveTol, setWaveTol] = useState<number | "">("");
  const [medianSub, setMedianSub] = useState(false);
  const [diffUrl, setDiffUrl] = useState<string | null>(null);
  const [stretch, setStretch] = useState(initial.stretch || "asinh");
  const [zoomView, setZoomView] = useState<ViewRect | null>(() => viewFromUrl(initial));

  const [cMetric, setCMetric] = useState<ChangeMetric>(
    (initial.cmetric as ChangeMetric) || "brightness_snr",
  );
  const [cRef, setCRef] = useState<ChangeReference>(
    (initial.cref as ChangeReference) || "median_others",
  );
  const [cAperture, setCAperture] = useState(initial.cap ?? 1.5);
  const [cSort, setCSort] = useState<ChangeSortMode>(
    (initial.csort as ChangeSortMode) || "time",
  );
  const [cRa, setCRa] = useState(initial.cra ?? initial.ra ?? WISE0855.ra);
  const [cDec, setCDec] = useState(initial.cdec ?? initial.dec ?? WISE0855.dec);
  const [cRangeLo, setCRangeLo] = useState<number | null>(initial.cmin ?? null);
  const [cRangeHi, setCRangeHi] = useState<number | null>(initial.cmax ?? null);
  const [changeScores, setChangeScores] = useState<ChangeScoresResponse | null>(null);
  const [changeBusy, setChangeBusy] = useState(false);
  const [keptEpochIds, setKeptEpochIds] = useState<string[]>([]);
  const keptKeyRef = useRef("");
  const onKeptEpochIds = useCallback((ids: string[]) => {
    const key = ids.join("\0");
    if (key === keptKeyRef.current) return;
    keptKeyRef.current = key;
    setKeptEpochIds(ids);
  }, []);
  const [pickAperture, setPickAperture] = useState(false);
  const [jumpEpochId, setJumpEpochId] = useState<string | null>(null);
  const changeDebounce = useRef<number | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [frozenReport, setFrozenReport] = useState<FrozenReportContext | null>(null);
  const [queueBanner, setQueueBanner] = useState("");

  const canReport =
    Number.isFinite(ra) &&
    Number.isFinite(dec) &&
    Boolean(cutouts?.frames && cutouts.frames.length >= 2);

  // Do not write epoch on every playback tick — only via onEpochCommit (step/pause).
  useEffect(() => {
    writeUrlState({
      ra,
      dec,
      fov,
      stretch,
      embed,
      demo: initial.demo,
      tab,
      target: targetId,
      zx0: zoomView?.x0,
      zy0: zoomView?.y0,
      zx1: zoomView?.x1,
      zy1: zoomView?.y1,
      cmin: cRangeLo ?? undefined,
      cmax: cRangeHi ?? undefined,
      cmetric: cMetric,
      cref: cRef,
      cap: cAperture,
      csort: cSort,
      cra: cRa,
      cdec: cDec,
    });
  }, [
    ra,
    dec,
    fov,
    stretch,
    embed,
    tab,
    targetId,
    initial.demo,
    zoomView,
    cRangeLo,
    cRangeHi,
    cMetric,
    cRef,
    cAperture,
    cSort,
    cRa,
    cDec,
  ]);

  const onEpochChange = useCallback((i: number) => {
    setEpoch(i);
  }, []);

  const onEpochCommit = useCallback((i: number) => {
    setEpoch(i);
    writeUrlState({
      ra,
      dec,
      fov,
      epoch: i,
      stretch,
      embed,
      demo: initial.demo,
      tab,
      target: targetId,
      zx0: zoomView?.x0,
      zy0: zoomView?.y0,
      zx1: zoomView?.x1,
      zy1: zoomView?.y1,
    });
  }, [ra, dec, fov, stretch, embed, tab, targetId, initial.demo, zoomView]);

  const onViewCommit = useCallback((view: ViewRect | null) => {
    setZoomView(view);
  }, []);

  const refreshChangeScores = useCallback(
    (opts: { ra: number; dec: number; target?: string }) => {
      if (changeDebounce.current) window.clearTimeout(changeDebounce.current);
      changeDebounce.current = window.setTimeout(() => {
        setChangeBusy(true);
        void loadChangeScores({
          ra: opts.ra,
          dec: opts.dec,
          radius: cAperture,
          metric: cMetric,
          reference: cRef,
          target: opts.target ?? targetId,
        })
          .then((data) => setChangeScores(data))
          .catch(() => setChangeScores(null))
          .finally(() => setChangeBusy(false));
      }, 280);
    },
    [cAperture, cMetric, cRef, targetId],
  );

  const loadField = async (opts: {
    ra: number;
    dec: number;
    name?: string;
    target?: string;
  }) => {
    setBusy(true);
    setErr("");
    setRa(opts.ra);
    setDec(opts.dec);
    setCRa(opts.ra);
    setCDec(opts.dec);
    if (opts.name) setName(opts.name);
    if (opts.target) setTargetId(opts.target);
    try {
      // Live SIA cutouts first (dr1 / dr1_deep / qr3 / qr3_deep); demo is offline fallback.
      let data: CutoutsResponse | null = null;
      try {
        data = await api.cutouts({
          ra: opts.ra,
          dec: opts.dec,
          fov,
          target: opts.target,
          target_name: opts.name || name,
          stack,
          detector,
          targeting_mode: targetingMode,
          wavelength_tol_um: waveTol === "" ? undefined : Number(waveTol),
          median_subtract: medianSub,
        });
        setDiffUrl(null);
      } catch {
        data = opts.target ? await loadDemoCutouts(opts.target) : null;
        if (!data) {
          throw new Error("Live SPHEREx SIA failed and no cached demo available");
        }
      }
      setCutouts(data);
      setEpoch(0);
      refreshChangeScores({
        ra: opts.ra,
        dec: opts.dec,
        target: opts.target ?? targetId,
      });
      // Ghost track is optional; never block the blink player on it.
      void api
        .predictedTrack(opts.ra, opts.dec, opts.name || name)
        .then((g) => setGhost(g.points))
        .catch(() => setGhost([]));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadField({ ra, dec, name, target: targetId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recompute scores when metric / reference / aperture / aperture sky pos change
  useEffect(() => {
    refreshChangeScores({ ra: cRa, dec: cDec, target: targetId });
  }, [cMetric, cRef, cAperture, cRa, cDec, targetId, refreshChangeScores]);

  const blinkFrames = useMemo(() => {
    const all = cutouts?.frames ?? [];
    if (!keptEpochIds.length) return all;
    const set = new Set(keptEpochIds);
    const filtered = all.filter((f) => set.has(f.epoch_id));
    if (cSort === "change") {
      // Order by keptEpochIds (already sorted by ChangeSlider)
      const rank = new Map(keptEpochIds.map((id, i) => [id, i]));
      return [...filtered].sort(
        (a, b) => (rank.get(a.epoch_id) ?? 0) - (rank.get(b.epoch_id) ?? 0),
      );
    }
    return filtered;
  }, [cutouts, keptEpochIds, cSort]);

  const trail: TrailPoint[] = useMemo(() => {
    if (!changeScores) return [];
    const set = new Set(keptEpochIds);
    const keptScores = changeScores.frames.filter((f) => set.has(f.epoch_id));
    return trailFromScores(keptScores.length ? keptScores : changeScores.frames);
  }, [changeScores, keptEpochIds]);

  const predictedTrail: TrailPoint[] = useMemo(() => {
    // Optional compare: ghost points that have x_pix/y_pix
    return ghost
      .filter((g) => g.x_pix != null && g.y_pix != null)
      .map((g, i) => ({
        epoch_id: g.epoch_id,
        mjd: g.mjd,
        x: g.x_pix as number,
        y: g.y_pix as number,
        index: i + 1,
      }));
  }, [ghost]);

  const apertureOverlay = useMemo(() => {
    if (!changeScores?.aperture_x_pix || changeScores.aperture_y_pix == null) {
      return { x: 14, y: 14, r: cAperture };
    }
    return {
      x: changeScores.aperture_x_pix,
      y: changeScores.aperture_y_pix,
      r: cAperture,
    };
  }, [changeScores, cAperture]);

  // Jump blink to histogram-selected epoch
  useEffect(() => {
    if (!jumpEpochId || !blinkFrames.length) return;
    const i = blinkFrames.findIndex((f) => f.epoch_id === jumpEpochId);
    if (i >= 0) {
      setEpoch(i);
      onEpochCommit(i);
    }
    setJumpEpochId(null);
  }, [jumpEpochId, blinkFrames, onEpochCommit]);

  // Flush offline observation queue when API is reachable
  useEffect(() => {
    const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
    void (async () => {
      const pending = await peekQueue().catch(() => []);
      if (!pending.length) return;
      setQueueBanner(`${pending.length} observation(s) queued — retrying…`);
      const { sent } = await flushQueue(async (payload) => {
        const r = await fetch(`${API}/api/observations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        return { ok: r.ok };
      });
      if (sent > 0) setQueueBanner(`Sent ${sent} queued observation(s).`);
      else setQueueBanner(`${pending.length} observation(s) still queued (backend unreachable).`);
    })();
  }, [cutouts?.source]);

  // Demo auto-walk
  useEffect(() => {
    if (!initial.demo) return;
    let i = 0;
    const id = window.setInterval(() => {
      const t = TEST_TARGETS[i % TEST_TARGETS.length];
      i += 1;
      void (async () => {
        if (t.ra != null && t.dec != null) {
          await loadField({ ra: t.ra, dec: t.dec, name: t.name, target: t.id });
        } else {
          const r = await api.resolve(t.name);
          await loadField({ ra: r.ra, dec: r.dec, name: t.name, target: t.id });
        }
      })();
    }, 12000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.demo]);

  const exportCandidates = () => {
    const payload = {
      ra,
      dec,
      fov,
      movers,
      credit: "NASA/JPL-Caltech/IPAC — SPHEREx at IRSA. SkyFlip candidates only.",
      disclaimer: "Not a discovery claim.",
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "skyflip_candidates.json";
    a.click();
  };

  return (
    <div className={`app ${embed ? "embed" : ""}`}>
      {!embed && (
        <header className="hero">
          <div>
            <p className="brand">SkyFlip</p>
            <p className="tag">
              The blink comparator that found Pluto, rebuilt for everyone — with proof built in.
            </p>
          </div>
          <nav className="tabs" aria-label="Primary">
            {(
              [
                ["viewer", "Viewer"],
                ["scoreboard", "Scoreboard"],
                ["discovery", "Discovery"],
                ["classroom", "Classroom"],
                ["planetx", "Planet X meter"],
              ] as const
            ).map(([id, label]) => (
              <button key={id} type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </nav>
        </header>
      )}

      <Banner
        cached={cutouts?.source === "cached-demo"}
        synthetic={cutouts?.frames.some((f) => f.is_synthetic)}
      />
      {queueBanner && (
        <p className="banner-cached" role="status" data-testid="obs-queue-banner">
          {queueBanner}
        </p>
      )}

      {tab === "viewer" && (
        <main className="layout">
          <section className="primary">
            {!embed && (
              <>
                <SearchBar
                  onGoto={(r, d, n) => void loadField({ ra: r, dec: d, name: n, target: targetId })}
                />
                <TargetButtons
                  onSelect={(t) => void loadField({ ra: t.ra, dec: t.dec, name: t.name, target: t.id })}
                />
                <div className="row wrap">
                  <label>
                    FOV {fov.toFixed(3)}°
                    <input
                      type="range"
                      min={0.05}
                      max={0.4}
                      step={0.01}
                      value={fov}
                      onChange={(e) => setFov(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Detector
                    <select
                      value={detector}
                      onChange={(e) => setDetector(Number(e.target.value))}
                      aria-label="SPHEREx detector"
                    >
                      {[1, 2, 3, 4, 5, 6].map((d) => (
                        <option key={d} value={d}>
                          D{d}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Targeting
                    <select
                      value={targetingMode}
                      onChange={(e) =>
                        setTargetingMode(e.target.value as "fixed_sky" | "track_target")
                      }
                    >
                      <option value="fixed_sky">fixed sky (movers hop)</option>
                      <option value="track_target">track target (follow PM)</option>
                    </select>
                  </label>
                  <label>
                    Stack
                    <select
                      value={stack}
                      onChange={(e) =>
                        setStack(e.target.value as "none" | "detector" | "all_detectors")
                      }
                    >
                      <option value="none">none</option>
                      <option value="detector">this detector (S/N)</option>
                      <option value="all_detectors">all six detectors</option>
                    </select>
                  </label>
                  <label>
                    λ match ±µm
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      placeholder="off"
                      value={waveTol}
                      onChange={(e) =>
                        setWaveTol(e.target.value === "" ? "" : Number(e.target.value))
                      }
                      style={{ width: "4.5rem" }}
                    />
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={medianSub}
                      onChange={(e) => setMedianSub(e.target.checked)}
                    />
                    Median-subtract
                  </label>
                  <button type="button" disabled={busy} onClick={() => void loadField({ ra, dec, name, target: targetId })}>
                    {busy ? "Loading…" : "Reload"}
                  </button>
                  <label className="check">
                    <input type="checkbox" checked={showGhost} onChange={(e) => setShowGhost(e.target.checked)} />
                    Ghost track
                  </label>
                  <button
                    type="button"
                    disabled={!cutouts || cutouts.frames.length < 2}
                    onClick={() => {
                      const frames = cutouts?.frames ?? [];
                      if (frames.length < 2) return;
                      void api
                        .diff({
                          ra,
                          dec,
                          fov,
                          a: frames[0].epoch_id,
                          b: frames[frames.length - 1].epoch_id,
                          bandpass: `SPHEREx-D${detector}`,
                        })
                        .then((r) => setDiffUrl(r.image_url))
                        .catch((e) => setErr(String(e)));
                    }}
                  >
                    Diff first−last
                  </button>
                  <ShareButton state={{ ra, dec, fov, target: targetId, stretch: "asinh" }} />
                  <button
                    type="button"
                    data-testid="report-observation"
                    disabled={!canReport}
                    title={
                      canReport
                        ? "Report an unverified community observation"
                        : "Load a sky position with at least 2 frames first"
                    }
                    aria-keyshortcuts="Shift+R"
                    onClick={() => {
                      if (!cutouts || !canReport) return;
                      const snap: FrozenReportContext = {
                        targetId: targetId,
                        targetName: name,
                        ra,
                        dec,
                        raDecSource: "target_button",
                        fovDeg: fov,
                        dataSource: cutouts.source,
                        frames: cutouts.frames,
                        keptEpochIds: keptEpochIds,
                        shareUrl: shareUrl({
                          ra,
                          dec,
                          fov,
                          target: targetId,
                          stretch,
                          cmetric: cMetric,
                          cref: cRef,
                          cap: cAperture,
                          csort: cSort,
                        }),
                        display: {
                          detector,
                          stretch,
                          targeting_mode: targetingMode,
                          median_subtract: medianSub,
                          wavelength_tol_um: waveTol === "" ? null : waveTol,
                          change_slider: {
                            metric: cMetric,
                            reference: cRef,
                            aperture: cAperture,
                            sort: cSort,
                            lo: cRangeLo,
                            hi: cRangeHi,
                          },
                          show_ghost: showGhost,
                        },
                        imageWidth: 29,
                        imageHeight: 29,
                        pixelScaleArcsec: cutouts.pixel_scale_arcsec ?? 6.15,
                      };
                      // Prefer float shape when available
                      const fs = cutouts.frames.find((f) => f.float_shape)?.float_shape;
                      if (fs) {
                        snap.imageHeight = fs[0];
                        snap.imageWidth = fs[1];
                      }
                      setFrozenReport(snap);
                      setReportOpen(true);
                    }}
                  >
                    Report an observation
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void api.movers(ra, dec, fov).then((r) => setMovers(r.movers)).catch((e) => setErr(String(e)))
                    }
                  >
                    Detect movers
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void api
                        .spectrum(ra, dec)
                        .then((r) => {
                          setSpectrum(r.points);
                          setSpecNote(r.method_note);
                        })
                        .catch((e) => setErr(String(e)))
                    }
                  >
                    Load spectrum
                  </button>
                  <button type="button" onClick={exportCandidates}>
                    Export candidates JSON
                  </button>
                </div>
              </>
            )}
            {err && <p className="error" role="alert">{err}</p>}
            {cutouts?.note && <p className="hint">{cutouts.note}</p>}
            {cutouts && (
              <ErrorBoundary label="BlinkPlayer">
                <BlinkPlayer
                  frames={blinkFrames.length ? blinkFrames : cutouts.frames}
                  ghost={ghost}
                  showGhost={showGhost}
                  reducedMotion={reduced}
                  stretch={stretch === "log" || stretch === "linear" ? stretch : "asinh"}
                  initialIndex={initial.epoch ?? 0}
                  onEpochChange={onEpochChange}
                  onEpochCommit={onEpochCommit}
                  onStretchCommit={(m) => setStretch(m)}
                  fieldRa={ra}
                  fieldDec={dec}
                  initialView={zoomView}
                  onViewCommit={onViewCommit}
                  offline={cutouts.source === "cached-demo"}
                  trail={trail}
                  predictedTrail={showGhost ? predictedTrail : []}
                  aperture={apertureOverlay}
                  pickAperture={pickAperture}
                  onAperturePick={(xPix, yPix) => {
                    // Approximate sky from image pixel (TAN, CRPIX at center)
                    const w = 29;
                    const h = 29;
                    const scale = 6.15 / 3600;
                    const cosd = Math.cos((dec * Math.PI) / 180);
                    const dra = -((xPix - (w - 1) / 2) * scale) / Math.max(cosd, 1e-6);
                    const ddec = (yPix - (h - 1) / 2) * scale;
                    setCRa(ra + dra);
                    setCDec(dec + ddec);
                  }}
                  onRefetchRegion={(view) => {
                    const cx = (view.x0 + view.x1) / 2;
                    const cy = (view.y0 + view.y1) / 2;
                    // Approximate new FOV from selection size (native pix → deg)
                    const wPix = Math.abs(view.x1 - view.x0);
                    const newFov = Math.min(1, Math.max(0.02, (wPix * 6.15) / 3600));
                    setErr("");
                    // Center stays field RA/Dec for now — cutout re-center needs live API WCS.
                    // TODO(VERIFY): map selection center through frame WCS when live.
                    setFov(newFov);
                    void loadField({ ra, dec, name, target: targetId });
                    void cx;
                    void cy;
                  }}
                />
              </ErrorBoundary>
            )}
            <ChangeSlider
              scores={changeScores}
              loading={changeBusy}
              metric={cMetric}
              reference={cRef}
              aperture={cAperture}
              sortMode={cSort}
              rangeLo={cRangeLo}
              rangeHi={cRangeHi}
              onMetric={setCMetric}
              onReference={setCRef}
              onAperture={setCAperture}
              onSortMode={setCSort}
              onRange={(lo, hi) => {
                setCRangeLo(lo);
                setCRangeHi(hi);
              }}
              onKeptEpochIds={onKeptEpochIds}
              onJumpToEpochId={setJumpEpochId}
              pickMode={pickAperture}
              onPickMode={setPickAperture}
            />
            {diffUrl && (
              <div className="panel" aria-label="Epoch difference">
                <h2>Diff (first − last epoch)</h2>
                <img src={apiUrl(diffUrl)} alt="Difference of first and last blink epochs" />
                <p className="hint">Aligned difference via /api/diff. Static stars cancel; movers remain.</p>
              </div>
            )}
            {!cutouts && busy && <div className="skeleton" aria-busy="true" />}
          </section>
          <aside className="side">
            <MetadataPanel
              frame={(blinkFrames.length ? blinkFrames : cutouts?.frames)?.[epoch]}
              source={cutouts?.source}
            />
            <CandidateList movers={movers} />
            <SpectrumPanel points={spectrum} methodNote={specNote} />
            {!embed && <AladinOverlay ra={ra} dec={dec} fov={Math.max(fov, 0.2)} />}
            {!embed && <SkyTour onPick={(id) => {
              const t = TEST_TARGETS.find((x) => x.id === id);
              if (!t) return;
              if (t.ra != null && t.dec != null) void loadField({ ra: t.ra, dec: t.dec, name: t.name, target: t.id });
              else void api.resolve(t.name).then((r) => loadField({ ra: r.ra, dec: r.dec, name: t.name, target: t.id }));
            }} />}
          </aside>
        </main>
      )}

      {tab === "scoreboard" && (
        <main className="single">
          <ScoreboardPanel />
          <LimitsPanel />
        </main>
      )}
      {tab === "discovery" && (
        <main className="single">
          <DiscoveryMode />
        </main>
      )}
      {tab === "classroom" && (
        <main className="single">
          <ClassroomMode />
        </main>
      )}
      {tab === "planetx" && (
        <main className="single">
          <PlanetXMeter />
        </main>
      )}

      {!embed && (
        <footer>
          <p>
            Credits: NASA / JPL-Caltech / IPAC SPHEREx archive. MIT license. We do not claim to discover
            Planet X.
          </p>
        </footer>
      )}

      <ReportObservation
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        context={frozenReport}
        reducedMotion={reduced}
      />
    </div>
  );
}
