"""SkyFlip FastAPI application."""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from PIL import Image
from astropy.wcs import WCS

from .adapters import catalogs, spherex
from .adapters.spherex import PIXEL_SCALE_ARCSEC
from .cache import DEMO_DATA, demo_data_available, read_json, write_json, cache_root
from .classify import classify_track
from .detect import detect_sources, link_detections
from .imaging import Frame, align_frames, difference, stretch, stack_mean
from .models import (
    Classification,
    CutoutFrameMeta,
    CutoutsResponse,
    DataSource,
    DiffResponse,
    EpochInfo,
    EpochsResponse,
    HealthResponse,
    HealthServiceStatus,
    MoverCandidate,
    MoversResponse,
    MoverTrackPoint,
    PredictedTrackPoint,
    PredictedTrackResponse,
    ResolveResponse,
    ScoreboardResponse,
    ChangeScoreFrame,
    ChangeScoresResponse,
    SpectrumPoint,
    SpectrumResponse,
)
from . import change_scores, spectra, validate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skyflip")

ROOT = Path(__file__).resolve().parents[2]
SCOREBOARD_PATH = ROOT / "frontend" / "public" / "demo-data" / "scoreboard.json"
VOTES_DB = cache_root() / "votes.sqlite3"

app = FastAPI(
    title="SkyFlip API",
    version="0.2.0",
    description="Blink comparator for NASA SPHEREx. Candidates only — we do not claim Planet X discoveries.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Discover via SIA: spherex_dr1, spherex_dr1_deep, spherex_qr3, spherex_qr3_deep
adapter = spherex.SpherexAdapter(include_deep=True)

TEST_TARGETS = {
    "wise0855": {
        "id": "wise0855",
        "name": "WISE 0855",
        "ra": 133.79512917,
        "dec": -7.24514722,
        "resolve": False,
    },
    "barnards_star": {"id": "barnards_star", "name": "Barnard's Star", "resolve": True},
    "epsilon_indi_b": {"id": "epsilon_indi_b", "name": "Epsilon Indi B", "resolve": True},
    "rw_aurigae": {"id": "rw_aurigae", "name": "RW Aurigae", "resolve": True},
    "r_draconis": {"id": "r_draconis", "name": "R Draconis", "resolve": True},
}


def _array_to_png_bytes(data: np.ndarray, mode: str = "asinh") -> bytes:
    scaled = stretch(data, mode=mode)
    img8 = (scaled * 255).astype(np.uint8)
    im = Image.fromarray(img8, mode="L")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _demo_manifest(target_id: str) -> Optional[dict[str, Any]]:
    path = DEMO_DATA / target_id / "manifest.json"
    if path.exists():
        return read_json(path)
    return None


def _wcs_dict(wcs) -> dict[str, Any]:
    try:
        return dict(wcs.to_header())
    except Exception:
        return {}


def _service_unavailable(endpoint: str, detail: str, *, source: str = "error") -> JSONResponse:
    """CORS-safe 503 JSON — never let offline archive failures white-screen the UI."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": detail,
            "source": source,
            "endpoint": endpoint,
            "ok": False,
        },
    )


def _tan_wcs(ra: float, dec: float, shape: tuple[int, int], pixel_scale_arcsec: float = PIXEL_SCALE_ARCSEC) -> WCS:
    ny, nx = shape
    w = WCS(naxis=2)
    w.wcs.crpix = [nx / 2.0, ny / 2.0]
    scale = pixel_scale_arcsec / 3600.0
    w.wcs.cdelt = [-scale, scale]
    w.wcs.crval = [ra, dec]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w


def _cached_predicted_track(name: str) -> Optional[dict[str, Any]]:
    needle = name.lower()
    for tid, meta in TEST_TARGETS.items():
        if tid in needle or meta["name"].lower() in needle or needle in meta["name"].lower():
            path = DEMO_DATA / tid / "predicted_track.json"
            if path.exists():
                return read_json(path)
    return None


@app.get("/api/health", response_model=HealthResponse)
def health(deep: bool = Query(False, description="If true, ping IRSA/SIMBAD/JPL (slow)")) -> HealthResponse:
    # Fast default so the UI never blocks on external archives.
    if not deep:
        return HealthResponse(
            status="ok",
            source=DataSource.live,
            services={
                "irsa": HealthServiceStatus(ok=True, detail="skipped (pass deep=1 to probe)"),
                "simbad": HealthServiceStatus(ok=True, detail="skipped (pass deep=1 to probe)"),
                "jpl": HealthServiceStatus(ok=True, detail="skipped (pass deep=1 to probe)"),
            },
            demo_cache_available=demo_data_available(),
            pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
        )
    irsa = adapter.ping_irsa()
    simbad = catalogs.ping_simbad()
    jpl = catalogs.ping_jpl()
    services = {
        "irsa": HealthServiceStatus(ok=bool(irsa.get("ok")), detail=str(irsa)[:300]),
        "simbad": HealthServiceStatus(ok=bool(simbad.get("ok")), detail=str(simbad)[:300]),
        "jpl": HealthServiceStatus(ok=bool(jpl.get("ok")), detail=str(jpl)[:300]),
    }
    oks = [s.ok for s in services.values()]
    status = "ok" if all(oks) else ("degraded" if any(oks) else "down")
    return HealthResponse(
        status=status,
        source=DataSource.live,
        services=services,
        demo_cache_available=demo_data_available(),
        pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
    )


@app.get("/api/targets")
def targets() -> dict[str, Any]:
    return {"targets": list(TEST_TARGETS.values()), "source": "live"}


@app.get("/api/resolve", response_model=ResolveResponse)
def resolve(name: str = Query(..., min_length=1)) -> ResolveResponse:
    try:
        data = catalogs.resolve_name(name)
    except catalogs.CatalogAdapterError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resolve error: {exc}") from exc
    return ResolveResponse(**data)


@app.get("/api/epochs", response_model=EpochsResponse)
def epochs(
    ra: float = Query(...),
    dec: float = Query(...),
    fov: float = Query(0.15, gt=0, le=2.0),
    bandpass: Optional[str] = None,
    target: Optional[str] = None,
) -> EpochsResponse:
    bands = (bandpass,) if bandpass else ("SPHEREx-D1",)
    try:
        obs = adapter.find_observations(
            ra, dec, fov_deg=fov, bandpasses=bands, prefer="sia"
        )
        source = DataSource.live
    except Exception as exc:
        logger.warning("live epochs failed: %s", exc)
        obs = []
        source = DataSource.cached_demo

    if not obs and target:
        man = _demo_manifest(target)
        if man:
            epochs_out = [
                EpochInfo(
                    epoch_id=f["epoch_id"],
                    obs_id=f.get("obs_id", f["epoch_id"]),
                    mjd=f["mjd"],
                    time_iso=f.get("time_iso", ""),
                    bandpass=f.get("bandpass", "SPHEREx-D1"),
                    detector=f.get("detector", 1),
                    collection=f.get("collection", ""),
                    central_wavelength_um=f.get("central_wavelength_um"),
                    flag_summary=f.get("flag_summary", {}),
                )
                for f in man.get("frames", [])
            ]
            return EpochsResponse(
                ra=ra, dec=dec, fov_deg=fov, epochs=epochs_out, source=DataSource.cached_demo
            )

    epochs_out = [
        EpochInfo(
            epoch_id=f"{o.obs_id}|{o.bandpass}|{o.mjd}",
            obs_id=o.obs_id,
            mjd=o.mjd,
            time_iso=o.time_iso,
            bandpass=o.bandpass,
            detector=o.detector,
            collection=o.collection,
            cutout_url=o.cutout_url,
            s_pixel_scale_arcsec=o.s_pixel_scale_arcsec,
        )
        for o in obs
    ]
    return EpochsResponse(ra=ra, dec=dec, fov_deg=fov, epochs=epochs_out, source=source)


def _select_blink_epochs(
    obs_list: list,
    max_frames: int = 8,
    *,
    wavelength_tol_um: Optional[float] = None,
    ref_wavelength_um: Optional[float] = None,
) -> list:
    """Pick well-spaced epochs for blinking (prefer distinct nights)."""
    if not obs_list:
        return []
    obs_list = sorted(obs_list, key=lambda o: o.mjd)
    by_day: dict[int, Any] = {}
    for o in obs_list:
        day = int(o.mjd)
        by_day.setdefault(day, o)
    days = sorted(by_day)
    chosen = [by_day[d] for d in days]
    if len(chosen) > max_frames:
        idxs = np.linspace(0, len(chosen) - 1, max_frames).astype(int)
        chosen = [chosen[i] for i in idxs]
    return chosen


DEFAULT_DETECTOR_BY_TARGET = {
    # Verified band ranges in docs/DATA_NOTES.md (Explanatory Supplement / Data Products).
    # Cold brown dwarfs peak mid-IR → prefer D5/D6; bright stars OK on D1.
    "wise0855": "SPHEREx-D5",
    "epsilon_indi_b": "SPHEREx-D5",
    "barnards_star": "SPHEREx-D1",
    "rw_aurigae": "SPHEREx-D1",
    "r_draconis": "SPHEREx-D1",
}


@app.get("/api/cutouts", response_model=CutoutsResponse)
def cutouts(
    ra: float,
    dec: float,
    fov: float = Query(0.2, gt=0, le=1.0),
    stack: Literal["none", "detector", "all_detectors", "date"] = "none",
    bandpass: Optional[str] = None,
    detector: Optional[int] = Query(None, ge=1, le=6),
    stretch_mode: str = "asinh",
    max_frames: int = Query(6, ge=2, le=12),
    target: Optional[str] = None,
    target_name: Optional[str] = None,
    targeting_mode: Literal["fixed_sky", "track_target"] = "fixed_sky",
    wavelength_tol_um: Optional[float] = Query(
        None, description="Keep frames within ±X µm of the first frame's λ"
    ),
    median_subtract: bool = False,
) -> CutoutsResponse:
    frames_meta: list[CutoutFrameMeta] = []
    source = DataSource.live
    note_bits: list[str] = []

    if bandpass is None:
        if detector is not None:
            bandpass = f"SPHEREx-D{detector}"
        elif target and target in DEFAULT_DETECTOR_BY_TARGET:
            bandpass = DEFAULT_DETECTOR_BY_TARGET[target]
        else:
            bandpass = "SPHEREx-D1"

    # Fixed-sky: one center for all epochs (movers hop). Track-target: each cutout
    # centered on PM-propagated position (target stays near crosshair).
    pm = None
    name_for_pm = target_name or (TEST_TARGETS.get(target or "", {}) or {}).get("name") or ""
    if targeting_mode == "track_target" or name_for_pm:
        try:
            pm = catalogs.get_proper_motion(name_for_pm or "target", ra, dec)
            note_bits.append(f"PM: {pm['citation']} ({pm['uncertainty_note']})")
        except Exception as exc:
            logger.info("PM lookup skipped: %s", exc)

    try:
        bandpasses: tuple[str, ...]
        if stack == "all_detectors":
            bandpasses = tuple(f"SPHEREx-D{i}" for i in range(1, 7))
        else:
            bandpasses = (bandpass,)

        obs = adapter.find_observations(
            ra, dec, fov_deg=fov, bandpasses=bandpasses, prefer="sia"
        )
        chosen = _select_blink_epochs(obs, max_frames=max_frames)
        cut_objs = []
        for o in chosen:
            cra, cdec = ra, dec
            if targeting_mode == "track_target" and pm is not None:
                cra, cdec = catalogs.propagate_position(
                    ra, dec, pm, Time(o.mjd, format="mjd")
                )
            cut = adapter.fetch_cutout(
                o, subtract_zodi=True, center_ra=cra, center_dec=cdec, size_deg=fov
            )
            cut = adapter.parse_cutout_fits(
                cut.fits_path, o, subtract_zodi=True, target_ra=cra, target_dec=cdec
            )
            cut_objs.append(cut)

        # Wavelength match filter (after we know central λ)
        if wavelength_tol_um is not None and cut_objs:
            ref_l = cut_objs[0].central_wavelength_um
            if ref_l is not None:
                kept = [
                    c
                    for c in cut_objs
                    if c.central_wavelength_um is None
                    or abs(c.central_wavelength_um - ref_l) <= wavelength_tol_um
                ]
                if len(kept) >= 2:
                    cut_objs = kept
                    note_bits.append(
                        f"wavelength match ±{wavelength_tol_um} µm around {ref_l:.3f} µm"
                    )
                else:
                    note_bits.append(
                        f"wavelength match ±{wavelength_tol_um} µm left <2 frames; kept all"
                    )

        note_bits.append(f"targeting_mode={targeting_mode}")

        if stack in ("detector", "all_detectors") and cut_objs:
            aligned = align_frames(
                [Frame(c.image, c.wcs, c.variance, c.flags, c.observation.mjd) for c in cut_objs]
            )
            stacked = stack_mean(aligned)
            png_name = _store_png(stacked, f"stack_{ra:.5f}_{dec:.5f}", stretch_mode)
            frames_meta.append(
                CutoutFrameMeta(
                    epoch_id="stack",
                    obs_id="stack",
                    mjd=float(np.mean([c.observation.mjd for c in cut_objs])),
                    time_iso="stacked",
                    bandpass=bandpass if stack == "detector" else "SPHEREx-D1..D6",
                    detector=cut_objs[0].observation.detector,
                    image_url=f"/api/png/{png_name}",
                    central_wavelength_um=cut_objs[0].central_wavelength_um,
                    flag_summary={},
                    wcs=_wcs_dict(cut_objs[0].wcs),
                )
            )
            note_bits.append(f"stack={stack} (mean of aligned frames)")
        else:
            if cut_objs:
                ref = Frame(cut_objs[0].image, cut_objs[0].wcs)
                aligned = align_frames(
                    [Frame(c.image, c.wcs, mjd=c.observation.mjd) for c in cut_objs], ref
                )
            else:
                aligned = []
            if median_subtract and len(aligned) >= 3:
                med = np.nanmedian(np.stack(aligned, axis=0), axis=0)
                aligned = [a - med for a in aligned]
                note_bits.append("median-subtraction mode (static sky removed)")
            for c, img in zip(cut_objs, aligned):
                eid = f"{c.observation.obs_id}|{c.observation.bandpass}|{c.observation.mjd}"
                png_name = _store_png(img, eid.replace("|", "_"), stretch_mode)
                frames_meta.append(
                    CutoutFrameMeta(
                        epoch_id=eid,
                        obs_id=c.observation.obs_id,
                        mjd=c.observation.mjd,
                        time_iso=c.observation.time_iso,
                        bandpass=c.observation.bandpass,
                        detector=c.observation.detector,
                        image_url=f"/api/png/{png_name}",
                        central_wavelength_um=c.central_wavelength_um,
                        flag_summary=c.flag_summary,
                        wcs=_wcs_dict(c.wcs),
                        bunit=str(c.header_meta.get("BUNIT") or "MJy/sr"),
                    )
                )
    except Exception as exc:
        logger.warning("live cutouts failed: %s", exc)
        source = DataSource.cached_demo
        frames_meta = []
        note_bits.append(f"live failed: {exc}")

    if not frames_meta and target:
        man = _demo_manifest(target)
        if man:
            source = DataSource.cached_demo
            demo_frames = list(man.get("frames", []))
            if wavelength_tol_um is not None and demo_frames:
                ref_l = demo_frames[0].get("central_wavelength_um")
                if ref_l is not None:
                    filt = [
                        f
                        for f in demo_frames
                        if f.get("central_wavelength_um") is None
                        or abs(float(f["central_wavelength_um"]) - float(ref_l))
                        <= wavelength_tol_um
                    ]
                    if len(filt) >= 2:
                        demo_frames = filt
            for f in demo_frames:
                frames_meta.append(
                    CutoutFrameMeta(
                        epoch_id=f["epoch_id"],
                        obs_id=f.get("obs_id", ""),
                        mjd=f["mjd"],
                        time_iso=f.get("time_iso", ""),
                        bandpass=f.get("bandpass", bandpass),
                        detector=f.get("detector", 1),
                        image_url=f"/demo-data/{target}/{f['png']}",
                        central_wavelength_um=f.get("central_wavelength_um"),
                        flag_summary=f.get("flag_summary", {}),
                        wcs=f.get("wcs", {}),
                    )
                )
            note_bits.append("cached-demo frames")
            if median_subtract:
                note_bits.append(
                    "median-subtract requested but not applied to pre-stretched demo PNGs"
                )

    if not frames_meta:
        raise HTTPException(
            status_code=503,
            detail="No live cutouts and no cached demo data for this field.",
        )

    return CutoutsResponse(
        ra=ra,
        dec=dec,
        fov_deg=fov,
        stack=stack,
        frames=frames_meta,
        source=source,
        pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
        note="; ".join(note_bits) if note_bits else None,
    )


def _store_png(data: np.ndarray, key: str, mode: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)[:80]
    name = f"{safe}_{mode}.png"
    path = cache_root() / "png" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_array_to_png_bytes(data, mode=mode))
    return name


@app.get("/api/png/{name}")
def get_png(name: str):
    path = cache_root() / "png" / name
    if not path.exists():
        raise HTTPException(404, "PNG not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/diff", response_model=DiffResponse)
def diff_images(
    ra: float,
    dec: float,
    fov: float = 0.15,
    a: str = Query(..., description="epoch_id A"),
    b: str = Query(..., description="epoch_id B"),
    bandpass: str = "SPHEREx-D1",
):
    try:
        obs = adapter.find_observations(
            ra, dec, fov_deg=fov, bandpasses=(bandpass,), prefer="sia"
        )
        by_id = {f"{o.obs_id}|{o.bandpass}|{o.mjd}": o for o in obs}

        def find(eid: str):
            if eid in by_id:
                return by_id[eid]
            for k, v in by_id.items():
                if eid in k:
                    return v
            return None

        oa, ob = find(a), find(b)
        if not oa or not ob:
            return _service_unavailable(
                "/api/diff",
                "epoch not found or archive unreachable",
                source="error",
            )

        ca = adapter.parse_cutout_fits(
            adapter.fetch_cutout(oa, subtract_zodi=True).fits_path,
            oa,
            subtract_zodi=True,
            target_ra=ra,
            target_dec=dec,
        )
        cb = adapter.parse_cutout_fits(
            adapter.fetch_cutout(ob, subtract_zodi=True).fits_path,
            ob,
            subtract_zodi=True,
            target_ra=ra,
            target_dec=dec,
        )
        aligned = align_frames([Frame(ca.image, ca.wcs), Frame(cb.image, cb.wcs)])
        diff = difference(aligned[0], aligned[1])
        name = _store_png(diff, f"diff_{a}_{b}", "asinh")
        return DiffResponse(
            ra=ra,
            dec=dec,
            fov_deg=fov,
            epoch_a=a,
            epoch_b=b,
            image_url=f"/api/png/{name}",
            source=DataSource.live,
        )
    except Exception as exc:
        logger.exception("diff failed")
        return _service_unavailable("/api/diff", f"diff failed: {exc}", source="error")


@app.get("/api/predicted-track", response_model=PredictedTrackResponse)
def predicted_track(
    ra: float,
    dec: float,
    name: str = Query(...),
    bandpass: str = "SPHEREx-D1",
    fov: float = 0.15,
):
    """Ghost marker from catalog proper motion; falls back to cached demo track offline."""
    try:
        pmra = pmdec = 0.0
        pm_note = "no proper motion available from resolver; ghost stays fixed"
        pm_err_note = "no uncertainty available"
        try:
            from astroquery.simbad import Simbad

            s = Simbad()
            s.add_votable_fields("pmra", "pmdec")
            tab = s.query_object(name)
            if tab is not None and len(tab) > 0:
                row = tab[0]
                for pra, pde in (("pmra", "pmdec"), ("PMRA", "PMDEC")):
                    if pra in row.colnames and pde in row.colnames and row[pra] is not np.ma.masked:
                        pmra = float(row[pra]) / 1000.0
                        pmdec = float(row[pde]) / 1000.0
                        pm_note = "SIMBAD proper motion (mas/yr → arcsec/yr)"
                        pm_err_note = "SIMBAD did not supply pm uncertainties in this query"
                        break
        except Exception as exc:
            logger.info("SIMBAD pm lookup failed: %s", exc)

        # TODO(VERIFY): WISE 0855 PM must be cited from SIMBAD/paper before claiming a value.
        # Do not invent a number here — offline uses cached predicted_track.json when present.
        if ("0855" in name or "WISE" in name.upper()) and pmra == 0 and pmdec == 0:
            cached = _cached_predicted_track(name)
            if cached:
                return PredictedTrackResponse(
                    name=name,
                    ra=ra,
                    dec=dec,
                    points=[PredictedTrackPoint(**p) for p in cached.get("points", [])],
                    source=DataSource.cached_demo,
                    method=cached.get("method", "cached demo predicted track"),
                    pixel_scale_arcsec=float(
                        cached.get("pixel_scale_arcsec", PIXEL_SCALE_ARCSEC)
                    ),
                )
            pm_note = (
                "WISE 0855 proper motion not resolved from SIMBAD in this session; "
                "ghost fixed at input coordinates until verified PM is cached — "
                + pm_err_note
            )

        epochs = []
        try:
            epochs = adapter.find_observations(
                ra, dec, fov_deg=fov, bandpasses=(bandpass,), prefer="sia"
            )
        except Exception as exc:
            logger.info("predicted-track epoch query failed: %s", exc)

        chosen = _select_blink_epochs(epochs, max_frames=8) if epochs else []

        # Prefer demo-frame epoch_ids so ghost matches offline blinks by epoch_id.
        demo_frames = None
        for tid, meta in TEST_TARGETS.items():
            if meta["name"].lower() in name.lower() or tid in name.lower().replace(" ", "_"):
                man = _demo_manifest(tid)
                if man:
                    demo_frames = man.get("frames", [])
                    ra = float(man.get("ra", ra))
                    dec = float(man.get("dec", dec))
                break

        if not chosen and demo_frames:
            t0 = float(demo_frames[0]["mjd"])
            shape = tuple(demo_frames[0].get("image_shape") or [29, 29])
            wcs = _tan_wcs(ra, dec, (int(shape[0]), int(shape[1])))
            points = []
            for fr in demo_frames:
                dt = (float(fr["mjd"]) - t0) / 365.25
                pra = ra + (pmra * dt) / 3600.0 / max(np.cos(np.deg2rad(dec)), 0.2)
                pdec = dec + (pmdec * dt) / 3600.0
                x_pix = y_pix = None
                try:
                    x_pix, y_pix = wcs.world_to_pixel(SkyCoord(pra * u.deg, pdec * u.deg))
                    x_pix, y_pix = float(x_pix), float(y_pix)
                except Exception:
                    pass
                points.append(
                    PredictedTrackPoint(
                        epoch_id=str(fr["epoch_id"]),
                        mjd=float(fr["mjd"]),
                        ra=float(pra),
                        dec=float(pdec),
                        x_pix=x_pix,
                        y_pix=y_pix,
                        note=f"{pm_note}; {pm_err_note}",
                    )
                )
            return PredictedTrackResponse(
                name=name,
                ra=ra,
                dec=dec,
                points=points,
                source=DataSource.cached_demo,
                method=pm_note,
                pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
            )

        if not chosen:
            cached = _cached_predicted_track(name)
            if cached:
                return PredictedTrackResponse(
                    name=name,
                    ra=ra,
                    dec=dec,
                    points=[PredictedTrackPoint(**p) for p in cached.get("points", [])],
                    source=DataSource.cached_demo,
                    method=cached.get("method", "cached demo predicted track"),
                    pixel_scale_arcsec=float(
                        cached.get("pixel_scale_arcsec", PIXEL_SCALE_ARCSEC)
                    ),
                )
            return PredictedTrackResponse(
                name=name,
                ra=ra,
                dec=dec,
                points=[
                    PredictedTrackPoint(
                        epoch_id="ref",
                        mjd=0,
                        ra=ra,
                        dec=dec,
                        x_pix=None,
                        y_pix=None,
                        note=pm_note,
                    )
                ],
                source=DataSource.live,
                method=pm_note,
                pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
            )

        t0 = chosen[0].mjd
        npix = max(29, int(round(fov * 3600.0 / PIXEL_SCALE_ARCSEC)))
        wcs = _tan_wcs(ra, dec, (npix, npix))
        points = []
        for o in chosen:
            dt = (o.mjd - t0) / 365.25
            pra = ra + (pmra * dt) / 3600.0 / max(np.cos(np.deg2rad(dec)), 0.2)
            pdec = dec + (pmdec * dt) / 3600.0
            eid = f"{o.obs_id}|{o.bandpass}|{o.mjd}"
            x_pix = y_pix = None
            try:
                x_pix, y_pix = wcs.world_to_pixel(SkyCoord(pra * u.deg, pdec * u.deg))
                x_pix, y_pix = float(x_pix), float(y_pix)
            except Exception:
                pass
            shift_arcsec = float(np.hypot(pmra * dt, pmdec * dt))
            points.append(
                PredictedTrackPoint(
                    epoch_id=eid,
                    mjd=o.mjd,
                    ra=float(pra),
                    dec=float(pdec),
                    x_pix=x_pix,
                    y_pix=y_pix,
                    note=(
                        f"predicted shift {shift_arcsec:.2f}\" ≈ "
                        f"{shift_arcsec / PIXEL_SCALE_ARCSEC:.2f} pix; {pm_note}; {pm_err_note}"
                    ),
                )
            )
        return PredictedTrackResponse(
            name=name,
            ra=ra,
            dec=dec,
            points=points,
            source=DataSource.live,
            method=pm_note,
            pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
        )
    except Exception as exc:
        logger.exception("predicted-track failed")
        cached = _cached_predicted_track(name)
        if cached:
            return PredictedTrackResponse(
                name=name,
                ra=ra,
                dec=dec,
                points=[PredictedTrackPoint(**p) for p in cached.get("points", [])],
                source=DataSource.cached_demo,
                method=cached.get("method", f"cached fallback after error: {exc}"),
                pixel_scale_arcsec=float(
                    cached.get("pixel_scale_arcsec", PIXEL_SCALE_ARCSEC)
                ),
            )
        return _service_unavailable(
            "/api/predicted-track",
            f"predicted-track failed: {exc}",
            source="error",
        )


@app.get("/api/movers", response_model=MoversResponse)
def movers(
    ra: float,
    dec: float,
    fov: float = 0.15,
    bandpass: str = "SPHEREx-D1",
):
    try:
        obs = adapter.find_observations(
            ra, dec, fov_deg=fov, bandpasses=(bandpass,), prefer="sia"
        )
        chosen = _select_blink_epochs(obs, max_frames=6)
        if not chosen:
            # Offline: empty movers with clear source, not a 500
            cached = DEMO_DATA / "movers_cache.json"
            if cached.exists():
                data = read_json(cached)
                return MoversResponse(
                    ra=ra,
                    dec=dec,
                    fov_deg=fov,
                    movers=[MoverCandidate(**m) for m in data.get("movers", [])],
                    source=DataSource.cached_demo,
                )
            return MoversResponse(
                ra=ra, dec=dec, fov_deg=fov, movers=[], source=DataSource.cached_demo
            )
        per_epoch = []
        for o in chosen:
            cut = adapter.parse_cutout_fits(
                adapter.fetch_cutout(o, subtract_zodi=True).fits_path,
                o,
                subtract_zodi=True,
                target_ra=ra,
                target_dec=dec,
            )
            eid = f"{o.obs_id}|{o.bandpass}|{o.mjd}"
            dets = detect_sources(cut.image, cut.wcs, eid, o.mjd)
            per_epoch.append(dets)
        tracks = link_detections(per_epoch)
        out = []
        for tr in tracks:
            cls = classify_track(tr)
            out.append(
                MoverCandidate(
                    id=tr.id,
                    classification=Classification(cls["classification"]),
                    reasons=cls["reasons"],
                    track=[
                        MoverTrackPoint(
                            epoch_id=d.epoch_id,
                            mjd=d.mjd,
                            ra=d.ra,
                            dec=d.dec,
                            ra_err_arcsec=d.x_err * PIXEL_SCALE_ARCSEC,
                            dec_err_arcsec=d.y_err * PIXEL_SCALE_ARCSEC,
                        )
                        for d in tr.detections
                    ],
                    pm_ra_arcsec_yr=tr.pm_ra_arcsec_yr,
                    pm_dec_arcsec_yr=tr.pm_dec_arcsec_yr,
                    pm_ra_err_arcsec_yr=tr.pm_ra_err,
                    pm_dec_err_arcsec_yr=tr.pm_dec_err,
                    crossmatch=cls.get("crossmatch", {}),
                    is_synthetic=tr.is_synthetic,
                )
            )
        return MoversResponse(ra=ra, dec=dec, fov_deg=fov, movers=out, source=DataSource.live)
    except Exception as exc:
        logger.exception("movers failed")
        return _service_unavailable("/api/movers", f"movers failed: {exc}", source="error")


@app.get("/api/spectrum", response_model=SpectrumResponse)
def spectrum(ra: float, dec: float, fov: float = 0.03):
    try:
        data = spectra.extract_spectrum_at(adapter, ra, dec, fov_deg=fov)
        return SpectrumResponse(
            ra=ra,
            dec=dec,
            points=[SpectrumPoint(**p) for p in data["points"]],
            source=DataSource.live,
            unit=data["unit"],
            method_note=data["method_note"] + " Notes: " + "; ".join(data.get("notes", [])),
            is_synthetic=False,
        )
    except Exception as exc:
        logger.exception("spectrum failed")
        # Cached spectrum fallback
        for tid in TEST_TARGETS:
            path = DEMO_DATA / tid / "spectrum.json"
            if path.exists():
                cached = read_json(path)
                return SpectrumResponse(
                    ra=float(cached.get("ra", ra)),
                    dec=float(cached.get("dec", dec)),
                    points=[SpectrumPoint(**p) for p in cached.get("points", [])],
                    source=DataSource.cached_demo,
                    unit=cached.get("unit", "MJy/sr"),
                    method_note=cached.get(
                        "method_note",
                        f"Using cached demo spectrum after live failure: {exc}",
                    ),
                    is_synthetic=bool(cached.get("is_synthetic", False)),
                )
        return _service_unavailable(
            "/api/spectrum",
            f"spectrum failed: {exc}",
            source="error",
        )


@app.get("/api/change-scores", response_model=ChangeScoresResponse)
def change_scores_endpoint(
    ra: float = Query(...),
    dec: float = Query(...),
    radius: float = Query(1.5, gt=0.1, le=10.0, description="Aperture radius in SPHEREx pixels"),
    metric: Literal["brightness_snr", "position_shift", "combined"] = "brightness_snr",
    reference: Literal["median_others", "first_epoch", "previous_epoch"] = "median_others",
    target: Optional[str] = None,
    live: bool = Query(
        False,
        description="If true, attempt IRSA cutouts (slow). Default uses demo float bins / cache only.",
    ),
) -> ChangeScoresResponse | JSONResponse:
    """
    Per-frame change scores at (ra, dec). Candidates only — not discoveries.
    Offline: serves/computes from demo-data float bins; never 500s blank.
    """
    banner: Optional[str] = None
    source = DataSource.live
    frames_in: list[change_scores.FrameInput] = []
    ax = ay = None

    # Prefer computing from demo float bins when a known target is requested
    # (works offline; also used as fallback).
    def _from_demo(tid: str) -> Optional[ChangeScoresResponse]:
        nonlocal banner, source, ax, ay
        demo_dir = DEMO_DATA / tid
        cache_path = demo_dir / "change_scores.json"
        man = _demo_manifest(tid)
        if not man:
            return None
        target_ra = float(man.get("ra", ra))
        target_dec = float(man.get("dec", dec))
        # Exact cache hit for default params at catalog position
        if (
            cache_path.exists()
            and abs(ra - target_ra) < 1e-5
            and abs(dec - target_dec) < 1e-5
            and abs(radius - 1.5) < 1e-6
        ):
            cached = read_json(cache_path)
            # Prefer matching metric/reference slice if present
            slices = cached.get("by_key") or {}
            key = f"{metric}|{reference}|{radius}"
            payload = slices.get(key) or cached.get("default")
            if payload and payload.get("frames"):
                source = DataSource.cached_demo
                banner = "using cached demo data"
                motion = payload.get("motion")
                if not motion:
                    score_objs = [
                        change_scores.FrameChangeScore(**{**f, "notes": list(f.get("notes") or [])})
                        for f in payload["frames"]
                    ]
                    motion = change_scores.net_motion(score_objs)
                return ChangeScoresResponse(
                    ra=ra,
                    dec=dec,
                    radius_pix=radius,
                    metric=metric,
                    reference=reference,
                    frames=[ChangeScoreFrame(**f) for f in payload["frames"]],
                    motion=motion,
                    source=source,
                    pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
                    aperture_x_pix=payload.get("aperture_x_pix"),
                    aperture_y_pix=payload.get("aperture_y_pix"),
                    is_synthetic=bool(payload.get("is_synthetic", False)),
                    banner=banner,
                )
        try:
            fin, ax, ay = change_scores.load_demo_frame_inputs(
                demo_dir,
                ra=ra,
                dec=dec,
                target_ra=target_ra,
                target_dec=target_dec,
                pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
            )
        except FileNotFoundError:
            return None
        scores = change_scores.score_frames(
            fin,
            metric=metric,  # type: ignore[arg-type]
            reference=reference,  # type: ignore[arg-type]
            aperture_pix=radius,
        )
        motion = change_scores.net_motion(scores)
        source = DataSource.cached_demo
        banner = "using cached demo data"
        return ChangeScoresResponse(
            ra=ra,
            dec=dec,
            radius_pix=radius,
            metric=metric,
            reference=reference,
            frames=[ChangeScoreFrame(**s.to_dict()) for s in scores],
            motion=motion,
            source=source,
            pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
            aperture_x_pix=ax,
            aperture_y_pix=ay,
            is_synthetic=False,
            banner=banner,
        )

    try:
        if target and target in TEST_TARGETS:
            resp = _from_demo(target)
            if resp is not None:
                return resp
        # Try nearest demo target by catalog RA/Dec
        for tid, meta in TEST_TARGETS.items():
            man = _demo_manifest(tid)
            if not man:
                continue
            if abs(float(man["ra"]) - ra) < 0.05 and abs(float(man["dec"]) - dec) < 0.05:
                resp = _from_demo(tid)
                if resp is not None:
                    return resp
    except Exception as exc:
        logger.warning("change-scores demo path failed: %s", exc)

    # Opt-in live IRSA path (slow; default stays offline-safe)
    if live:
        try:
            bandpass = "SPHEREx-D1"
            if target and target in DEFAULT_DETECTOR_BY_TARGET:
                bandpass = DEFAULT_DETECTOR_BY_TARGET[target]
            obs = adapter.find_observations(
                ra, dec, fov_deg=0.15, bandpasses=(bandpass,), prefer="sia"
            )
            chosen = _select_blink_epochs(obs, max_frames=8)
            cut_objs = []
            for o in chosen:
                cut = adapter.fetch_cutout(
                    o, subtract_zodi=True, center_ra=ra, center_dec=dec, size_deg=0.05
                )
                cut = adapter.parse_cutout_fits(
                    cut.fits_path, o, subtract_zodi=True, target_ra=ra, target_dec=dec
                )
                cut_objs.append(cut)
            if len(cut_objs) < 2:
                raise RuntimeError("fewer than 2 live cutouts for change scores")
            ref = Frame(cut_objs[0].image, cut_objs[0].wcs)
            aligned_imgs = align_frames(
                [
                    Frame(c.image, c.wcs, c.variance, c.flags, c.observation.mjd)
                    for c in cut_objs
                ],
                ref,
            )
            try:
                x0, y0 = cut_objs[0].wcs.world_to_pixel(SkyCoord(ra * u.deg, dec * u.deg))
                ax, ay = float(x0), float(y0)
            except Exception:
                ay, ax = (np.array(aligned_imgs[0].shape) - 1) / 2.0
            for c, img in zip(cut_objs, aligned_imgs):
                frames_in.append(
                    change_scores.FrameInput(
                        epoch_id=f"{c.observation.obs_id}|{c.observation.bandpass}|{c.observation.mjd}",
                        mjd=c.observation.mjd,
                        image=np.asarray(img, dtype=float),
                        variance=c.variance,
                        flags=c.flags,
                        wavelength_um=c.central_wavelength_um,
                        detector=c.observation.detector,
                        x_pix=float(ax),
                        y_pix=float(ay),
                    )
                )
            scores = change_scores.score_frames(
                frames_in,
                metric=metric,  # type: ignore[arg-type]
                reference=reference,  # type: ignore[arg-type]
                aperture_pix=radius,
            )
            return ChangeScoresResponse(
                ra=ra,
                dec=dec,
                radius_pix=radius,
                metric=metric,
                reference=reference,
                frames=[ChangeScoreFrame(**s.to_dict()) for s in scores],
                motion=change_scores.net_motion(scores),
                source=DataSource.live,
                pixel_scale_arcsec=PIXEL_SCALE_ARCSEC,
                aperture_x_pix=float(ax) if ax is not None else None,
                aperture_y_pix=float(ay) if ay is not None else None,
                is_synthetic=False,
                banner=None,
            )
        except Exception as exc:
            logger.warning("live change-scores failed: %s", exc)
            return _service_unavailable(
                "/api/change-scores",
                f"live change scores failed: {exc}",
                source="error",
            )

    return _service_unavailable(
        "/api/change-scores",
        "No cached change scores for this position. Pass target=<demo id> "
        "or live=1 when IRSA is reachable.",
        source="cached-demo",
    )


@app.get("/api/scoreboard", response_model=ScoreboardResponse)
def scoreboard() -> ScoreboardResponse:
    self_test = validate.fit_motion_self_test()
    payload: dict[str, Any] = {
        "motion_fit_self_test": self_test,
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
    }
    source = DataSource.live
    if SCOREBOARD_PATH.exists():
        file_data = read_json(SCOREBOARD_PATH)
        payload.update(file_data)
        source = DataSource(file_data.get("source", "cached-demo"))
    return ScoreboardResponse(
        source=source,
        results=payload,
        is_synthetic_injected=bool(payload.get("synthetic", {}).get("is_synthetic")),
        explanation=(
            "Recovery counts compare detections to known movers within 2 SPHEREx pixels. "
            "Misses are shown deliberately. Synthetic injections are labeled is_synthetic. "
            "This does not claim discovery of Planet X."
        ),
    )


# --- Discovery Mode votes (SQLite optional) ---
def _votes_conn():
    VOTES_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(VOTES_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS votes (
        candidate_id TEXT, vote TEXT, ts REAL
        )"""
    )
    conn.commit()
    return conn


@app.post("/api/votes")
def post_vote(candidate_id: str, vote: Literal["moved", "didnt", "unsure"]):
    conn = _votes_conn()
    import time

    conn.execute(
        "INSERT INTO votes(candidate_id, vote, ts) VALUES (?,?,?)",
        (candidate_id, vote, time.time()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "source": "live"}


@app.get("/api/votes/{candidate_id}")
def get_votes(candidate_id: str):
    conn = _votes_conn()
    rows = conn.execute(
        "SELECT vote, COUNT(*) FROM votes WHERE candidate_id=? GROUP BY vote",
        (candidate_id,),
    ).fetchall()
    conn.close()
    counts = {k: v for k, v in rows}
    total = sum(counts.values())
    moved = counts.get("moved", 0)
    return {
        "candidate_id": candidate_id,
        "counts": counts,
        "n_votes": total,
        "agreement_pct_moved": (100.0 * moved / total) if total else None,
        "note": "Agreement percentage among volunteers — not a discovery claim.",
        "source": "live",
    }


# --- Community observations (unverified) ---
from .observations.schema import ObservationCreate  # noqa: E402
from .observations import service as obs_service  # noqa: E402
from .observations.db import connect as obs_connect, delete_submission as obs_delete  # noqa: E402


@app.post("/api/observations")
async def post_observation(
    request: Request,
    payload: ObservationCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if idempotency_key and not payload.idempotency_key:
        payload.idempotency_key = idempotency_key
    elif idempotency_key:
        payload.idempotency_key = idempotency_key
    # Coarse client key: no plain IP stored on the report
    fwd = request.headers.get("x-forwarded-for", "")
    peer = request.client.host if request.client else "unknown"
    raw = (fwd.split(",")[0].strip() or peer)[:64]
    known = set(payload.allowed_epoch_ids) if payload.allowed_epoch_ids else None
    result = obs_service.submit_observation(
        payload,
        client_raw_key=raw,
        known_epoch_ids=known,
        git_commit=os.environ.get("SKYFLIP_GIT_COMMIT", ""),
    )
    if not result.get("ok"):
        return JSONResponse(
            status_code=int(result.get("status_code", 400)),
            content={
                "ok": False,
                "errors": result.get("errors", []),
                "detail": "validation failed",
            },
        )
    return JSONResponse(status_code=int(result.get("status_code", 201)), content=result)


@app.delete("/api/observations/{submission_id}")
def delete_observation(submission_id: str, delete_token: str = Query(...)):
    conn = obs_connect()
    ok = obs_delete(conn, submission_id, delete_token)
    conn.close()
    if not ok:
        raise HTTPException(404, "Not found or bad delete token")
    return {"ok": True, "deleted": submission_id}


@app.get("/api/observations")
def list_observations(
    admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    status: Optional[str] = None,
    target: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    if not obs_service.require_admin(admin_token):
        raise HTTPException(401, "Admin token required")
    rows = obs_service.list_submissions(
        status=status, target_id=target, limit=limit, offset=offset
    )
    return {"ok": True, "results": rows, "note": "Community observations, unverified."}


@app.get("/api/observations/aggregate")
def observations_aggregate(
    admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    cone_arcsec: float = Query(12.3, gt=0),
):
    if not obs_service.require_admin(admin_token):
        raise HTTPException(401, "Admin token required")
    groups = obs_service.aggregate_by_sky(cone_arcsec=cone_arcsec)
    return {
        "ok": True,
        "groups": groups,
        "label": "agreement among community reports, not a detection",
    }


@app.get("/api/observations/{submission_id}")
def get_observation_admin(
    submission_id: str,
    admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    if not obs_service.require_admin(admin_token):
        raise HTTPException(401, "Admin token required")
    from .observations.db import get_submission

    conn = obs_connect()
    row = get_submission(conn, submission_id)
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    # Strip delete_token from admin list? Keep for ops; never expose contact here without join
    return {"ok": True, "submission": dict(row)}
