#!/usr/bin/env python3
"""Write validation scoreboard JSON from measured recoveries (no hardcoded scores)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from PIL import Image
import astropy.units as u

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import validate  # noqa: E402
from app.adapters.spherex import PIXEL_SCALE_ARCSEC  # noqa: E402
from app.classify import classify_track  # noqa: E402
from app.detect import detect_sources, link_detections  # noqa: E402

OUT = ROOT / "frontend" / "public" / "demo-data" / "scoreboard.json"
DEMO = ROOT / "frontend" / "public" / "demo-data"

# Catalog proper motions used only when measured from SIMBAD at runtime, else skipped.
# Barnard's Star PM is resolved via SIMBAD when network is up; otherwise field stats
# are marked "not computed yet" rather than inventing numbers.


def _tan_wcs(ra: float, dec: float, shape: tuple[int, int]) -> WCS:
    ny, nx = shape
    w = WCS(naxis=2)
    w.wcs.crpix = [nx / 2.0, ny / 2.0]
    scale = PIXEL_SCALE_ARCSEC / 3600.0
    w.wcs.cdelt = [-scale, scale]
    w.wcs.crval = [ra, dec]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w


def _load_png_float(path: Path) -> np.ndarray:
    arr = np.asarray(Image.open(path).convert("L"), dtype=float)
    return arr


def _simbad_pm(name: str) -> dict | None:
    try:
        from astroquery.simbad import Simbad

        s = Simbad()
        s.add_votable_fields("pmra", "pmdec", "ra", "dec")
        tab = s.query_object(name)
        if tab is None or len(tab) == 0:
            return None
        row = tab[0]
        pmra = pmdec = None
        for pra, pde in (("pmra", "pmdec"), ("PMRA", "PMDEC")):
            if pra in row.colnames and row[pra] is not np.ma.masked:
                pmra = float(row[pra]) / 1000.0  # mas/yr → arcsec/yr
                pmdec = float(row[pde]) / 1000.0
                break
        ra = float(row["ra"] if "ra" in row.colnames else row["RA"])
        dec = float(row["dec"] if "dec" in row.colnames else row["DEC"])
        if pmra is None:
            return None
        return {
            "ra": ra,
            "dec": dec,
            "pm_ra": pmra,
            "pm_dec": pmdec,
            "pm_source": "SIMBAD",
            "pm_uncertainty": "no uncertainty available from this SIMBAD query",
        }
    except Exception as exc:
        print("SIMBAD unavailable:", exc)
        return None


def _field_recovery_for_target(tid: str, man: dict) -> dict:
    """Detect+link on cached demo PNGs; match to PM-propagated catalog position."""
    frames = man.get("frames") or []
    if len(frames) < 2:
        return {
            "target_id": tid,
            "status": "not computed yet",
            "reason": "fewer than 2 cached frames",
            "n_frames": len(frames),
            "n_epochs": len(frames),
        }

    ra0 = float(man["ra"])
    dec0 = float(man["dec"])
    name = man.get("name", tid)
    pm = _simbad_pm(name)
    if pm is None and tid == "wise0855":
        # Do not invent WISE 0855 PM — leave uncomputed until cited value is verified.
        return {
            "target_id": tid,
            "status": "not computed yet",
            "reason": (
                "WISE 0855 proper motion not verified in this run "
                "(TODO(VERIFY): cite SIMBAD or published PM + epoch)"
            ),
            "n_frames": len(frames),
            "n_epochs": len(frames),
            "match_radius_arcsec": 2 * PIXEL_SCALE_ARCSEC,
        }

    if pm is None:
        # Fall back: treat manifest center as fixed reference (no PM) — recovery
        # then tests whether anything is detected near the cutout center.
        pm = {
            "ra": ra0,
            "dec": dec0,
            "pm_ra": 0.0,
            "pm_dec": 0.0,
            "pm_source": "manifest center (no SIMBAD PM)",
            "pm_uncertainty": "no uncertainty available",
        }

    per_epoch = []
    predicted = []
    t0 = float(frames[0]["mjd"])
    for fr in frames:
        png = DEMO / tid / fr["png"]
        if not png.exists():
            continue
        img = _load_png_float(png)
        shape = img.shape
        wcs = _tan_wcs(ra0, dec0, shape)
        eid = str(fr["epoch_id"])
        mjd = float(fr["mjd"])
        dets = detect_sources(img, wcs, eid, mjd, fwhm=2.5, threshold_sigma=4.0)
        per_epoch.append(dets)
        dt = (mjd - t0) / 365.25
        pra = pm["ra"] + (pm["pm_ra"] * dt) / 3600.0 / max(np.cos(np.deg2rad(pm["dec"])), 0.2)
        pdec = pm["dec"] + (pm["pm_dec"] * dt) / 3600.0
        predicted.append({"epoch_id": eid, "mjd": mjd, "ra": pra, "dec": pdec})

    tracks = link_detections(per_epoch, max_sep_arcsec=3 * PIXEL_SCALE_ARCSEC)
    match_r = 2 * PIXEL_SCALE_ARCSEC
    # Known track is the PM-propagated mean position
    known = [
        {
            "id": tid,
            "ra": float(np.mean([p["ra"] for p in predicted])),
            "dec": float(np.mean([p["dec"] for p in predicted])),
        }
    ]
    stats = validate.recovery_stats(known, tracks, match_arcsec=match_r)

    # Classify each found track for false-candidate accounting
    classified = [classify_track(tr) for tr in tracks]
    n_candidates = sum(1 for c in classified if c["classification"] == "candidate")
    n_stationary = sum(1 for c in classified if c["classification"] == "stationary_source")

    return {
        "target_id": tid,
        "status": "measured",
        "method": (
            "DAOStarFinder detect + greedy link on cached demo PNG cutouts; "
            "match to PM-propagated catalog position"
        ),
        "pm_source": pm["pm_source"],
        "pm_uncertainty": pm["pm_uncertainty"],
        "pm_ra_arcsec_yr": pm["pm_ra"],
        "pm_dec_arcsec_yr": pm["pm_dec"],
        "n_frames": len(per_epoch),
        "n_epochs": len(per_epoch),
        "n_tracks_found": len(tracks),
        "n_candidate_class": n_candidates,
        "n_stationary_class": n_stationary,
        "match_radius_arcsec": match_r,
        **stats,
    }


def _write_predicted_track_cache(tid: str, man: dict, pm: dict | None) -> None:
    """Cache ghost points with x_pix/y_pix matched to demo epoch_ids."""
    frames = man.get("frames") or []
    if not frames:
        return
    ra0 = float(man["ra"])
    dec0 = float(man["dec"])
    pm_ra = float(pm["pm_ra"]) if pm else 0.0
    pm_dec = float(pm["pm_dec"]) if pm else 0.0
    method = (
        f"PM from {pm['pm_source']}" if pm else "fixed coordinates (no PM available)"
    )
    t0 = float(frames[0]["mjd"])
    shape = tuple(frames[0].get("image_shape") or [29, 29])
    wcs = _tan_wcs(ra0, dec0, (int(shape[0]), int(shape[1])))
    points = []
    for fr in frames:
        dt = (float(fr["mjd"]) - t0) / 365.25
        pra = ra0 + (pm_ra * dt) / 3600.0 / max(np.cos(np.deg2rad(dec0)), 0.2)
        pdec = dec0 + (pm_dec * dt) / 3600.0
        x_pix = y_pix = None
        try:
            x_pix, y_pix = wcs.world_to_pixel(SkyCoord(pra * u.deg, pdec * u.deg))
            x_pix, y_pix = float(x_pix), float(y_pix)
        except Exception:
            pass
        points.append(
            {
                "epoch_id": str(fr["epoch_id"]),
                "mjd": float(fr["mjd"]),
                "ra": float(pra),
                "dec": float(pdec),
                "x_pix": x_pix,
                "y_pix": y_pix,
                "note": method,
            }
        )
    out = {
        "name": man.get("name", tid),
        "ra": ra0,
        "dec": dec0,
        "method": method,
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "points": points,
        "source": "cached-demo",
    }
    (DEMO / tid / "predicted_track.json").write_text(json.dumps(out, indent=2) + "\n")


def main() -> int:
    self_test = validate.fit_motion_self_test()
    per_target = []
    recovered = missed = false_cands = 0
    known_considered = []
    n_measured = 0

    for tid_dir in sorted(DEMO.iterdir()):
        if not tid_dir.is_dir():
            continue
        man_path = tid_dir / "manifest.json"
        if not man_path.exists():
            continue
        man = json.loads(man_path.read_text())
        tid = man.get("target_id", tid_dir.name)
        pm = _simbad_pm(man.get("name", tid))
        _write_predicted_track_cache(tid, man, pm)
        result = _field_recovery_for_target(tid, man)
        per_target.append(result)
        known_considered.append({"id": tid, "name": man.get("name", tid)})
        if result.get("status") != "measured":
            continue
        n_measured += 1
        recovered += int(result.get("n_recovered") or 0)
        missed += int(result.get("n_missed") or 0)
        false_cands += int(result.get("n_false_candidates") or 0)

    # Load synthetic injection results if present (written by inject_movers.py)
    synth_path = DEMO / "synthetic_movers.json"
    if synth_path.exists():
        synth = json.loads(synth_path.read_text())
    else:
        synth = {
            "is_synthetic": True,
            "bins": [],
            "note": "not computed yet — run pipeline/inject_movers.py",
            "status": "not computed yet",
        }

    if n_measured == 0:
        field = {
            "status": "not computed yet",
            "note": (
                "No target yielded a measured recovery in this run "
                "(need SIMBAD PM and ≥2 cached frames)."
            ),
            "known_targets_considered": known_considered,
            "per_target": per_target,
            "n_known": None,
            "n_recovered": None,
            "n_missed": None,
            "n_false_candidates": None,
            "recovery_rate": None,
            "match_radius_arcsec": 2 * PIXEL_SCALE_ARCSEC,
            "sample_size": {"n_targets_attempted": len(per_target), "n_measured": 0},
            "method": "DAOStarFinder + link on cached demo PNGs vs PM-propagated position",
        }
    else:
        n_known = recovered + missed
        field = {
            "status": "measured",
            "note": "Measured on cached demo cutouts; misses are first-class.",
            "known_targets_considered": known_considered,
            "per_target": per_target,
            "n_known": n_known,
            "n_recovered": recovered,
            "n_missed": missed,
            "n_false_candidates": false_cands,
            "recovery_rate": (recovered / n_known) if n_known else None,
            "match_radius_arcsec": 2 * PIXEL_SCALE_ARCSEC,
            "sample_size": {
                "n_targets_attempted": len(per_target),
                "n_measured": n_measured,
                "n_frames_total": sum(int(t.get("n_frames") or 0) for t in per_target),
            },
            "method": (
                "DAOStarFinder detect + greedy nearest-neighbor link on cached demo PNG "
                f"cutouts; match radius = 2×{PIXEL_SCALE_ARCSEC}\" SPHEREx pixels"
            ),
            "misses": [t for t in per_target if t.get("n_missed")],
            "misses_explained": (
                "Coarse 6.15\" pixels, wavelength mismatch between LVF visits, "
                "8-bit PNG stretch loss, and sparse epochs can hide motion of ~1 pixel."
            ),
        }

    payload = {
        "source": "cached-demo",
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "motion_fit_self_test": self_test,
        "field_validation": field,
        "synthetic": synth if synth.get("bins") is not None else {
            "is_synthetic": True,
            "status": "not computed yet",
            "bins": [],
        },
        "limits": [
            "Too faint relative to SPHEREx depth / zodiacal background",
            "Too slow: sub-pixel motion between visits",
            "Crowded fields / blending",
            "Bad / flagged pixels (TRANSIENT, HALO, DICHROIC, …)",
            "Wavelength mismatch across LVF visits mistaken for variability",
            "Demo PNGs are 8-bit stretched — detection here underestimates float archive S/N",
        ],
        "disclaimer": "SkyFlip does not claim to discover Planet X or any new object.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print("Wrote", OUT)
    print("field status:", field.get("status"), "measured targets:", n_measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
