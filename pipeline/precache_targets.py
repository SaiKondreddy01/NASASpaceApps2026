#!/usr/bin/env python3
"""Pre-cache cutouts + manifests for the five official test targets into frontend/public/demo-data/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from astropy.time import Time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import catalogs  # noqa: E402
from app.adapters.spherex import PIXEL_SCALE_ARCSEC, SpherexAdapter  # noqa: E402
from app.imaging import stretch  # noqa: E402

OUT = ROOT / "frontend" / "public" / "demo-data"
FOV = 0.2  # ~117 px at 6.15″ — larger so fixed-sky hops are visible
MAX_FRAMES = 6
# Default: fixed_sky so movers hop against static stars
TARGETING_MODE = "fixed_sky"
DEFAULT_DETECTOR_BY_TARGET = {
    "wise0855": "SPHEREx-D5",
    "epsilon_indi_b": "SPHEREx-D5",
    "barnards_star": "SPHEREx-D1",
    "rw_aurigae": "SPHEREx-D1",
    "r_draconis": "SPHEREx-D1",
}

TARGETS = [
    {"id": "wise0855", "name": "WISE 0855", "ra": 133.79512917, "dec": -7.24514722},
    {"id": "barnards_star", "name": "Barnard's Star"},
    {"id": "epsilon_indi_b", "name": "Epsilon Indi B"},
    {"id": "rw_aurigae", "name": "RW Aurigae"},
    {"id": "r_draconis", "name": "R Draconis"},
]


def resolve(t):
    if "ra" in t:
        return t["ra"], t["dec"]
    r = catalogs.resolve_name(t["name"])
    return r["ra"], r["dec"]


def save_png(arr, path: Path):
    scaled = stretch(arr, "asinh")
    img = Image.fromarray((scaled * 255).astype(np.uint8), mode="L")
    img.save(path)


def main() -> int:
    adapter = SpherexAdapter(cache_dir=ROOT / "backend" / ".cache", include_deep=True)
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    visibility_report = []

    for t in TARGETS:
        print("===", t["name"])
        try:
            ra, dec = resolve(t)
        except Exception as exc:
            print("  resolve failed:", exc)
            continue

        band = DEFAULT_DETECTOR_BY_TARGET.get(t["id"], "SPHEREx-D1")
        pm = catalogs.get_proper_motion(t["name"], ra, dec)
        print("  PM:", pm["citation"], pm["pm_ra_cosdec_arcsec_yr"], pm["pm_dec_arcsec_yr"])

        dest = OUT / t["id"]
        dest.mkdir(parents=True, exist_ok=True)
        try:
            obs = adapter.find_observations(
                ra, dec, fov_deg=FOV, bandpasses=(band,), prefer="sia"
            )
        except Exception as exc:
            print("  discovery failed:", exc)
            continue
        print("  collections:", sorted({o.collection for o in obs}), "n=", len(obs))

        by_day = {}
        for o in sorted(obs, key=lambda x: x.mjd):
            by_day.setdefault(int(o.mjd), o)
        chosen = list(by_day.values())
        if len(chosen) > MAX_FRAMES:
            idxs = np.linspace(0, len(chosen) - 1, MAX_FRAMES).astype(int)
            chosen = [chosen[i] for i in idxs]

        frames = []
        pixel_shifts = []
        for i, o in enumerate(chosen):
            cra, cdec = ra, dec
            if TARGETING_MODE == "track_target":
                cra, cdec = catalogs.propagate_position(
                    ra, dec, pm, Time(o.mjd, format="mjd")
                )
            # Predicted shift vs first epoch (for visibility report)
            pra, pdec = catalogs.propagate_position(ra, dec, pm, Time(o.mjd, format="mjd"))
            if i == 0:
                pra0, pdec0 = pra, pdec
            dra = (pra - pra0) * np.cos(np.deg2rad(dec)) * 3600.0
            ddec = (pdec - pdec0) * 3600.0
            shift_pix = float(np.hypot(dra, ddec) / PIXEL_SCALE_ARCSEC)
            pixel_shifts.append(shift_pix)

            try:
                cut = adapter.fetch_cutout(
                    o,
                    subtract_zodi=True,
                    center_ra=cra,
                    center_dec=cdec,
                    size_deg=FOV,
                )
            except Exception as exc:
                print("  cutout fail", o.obs_id, exc)
                continue

            png_name = f"frame_{i:02d}_{o.mjd:.5f}.png"
            save_png(cut.image, dest / png_name)
            frames.append(
                {
                    "epoch_id": f"{o.obs_id}|{o.bandpass}|{o.mjd}",
                    "obs_id": o.obs_id,
                    "mjd": o.mjd,
                    "time_iso": o.time_iso,
                    "bandpass": o.bandpass,
                    "detector": o.detector,
                    "collection": o.collection,
                    "png": png_name,
                    "central_wavelength_um": cut.central_wavelength_um,
                    "flag_summary": cut.flag_summary,
                    "image_shape": list(cut.image.shape),
                    "cutout_center_ra": cra,
                    "cutout_center_dec": cdec,
                    "predicted_ra": pra,
                    "predicted_dec": pdec,
                    "predicted_shift_pix_from_epoch0": shift_pix,
                }
            )
            print("  wrote", png_name, "shape", cut.image.shape, "λ", cut.central_wavelength_um)

        total_shift = pixel_shifts[-1] if pixel_shifts else 0.0
        # Honest visibility: we cannot claim detection without measuring peak at predicted pixel
        vis = {
            "target_id": t["id"],
            "bandpass": band,
            "targeting_mode": TARGETING_MODE,
            "fov_deg": FOV,
            "n_frames": len(frames),
            "pm_citation": pm["citation"],
            "pm_ra_cosdec_arcsec_yr": pm["pm_ra_cosdec_arcsec_yr"],
            "pm_dec_arcsec_yr": pm["pm_dec_arcsec_yr"],
            "pm_uncertainty": pm["uncertainty_note"],
            "predicted_shift_pix_epoch0_to_last": total_shift,
            "visibility_note": (
                "Predicted geometric shift only. Whether the source is actually "
                "detectable in this detector is reported after inspecting cutouts; "
                "cold Y dwarfs may be invisible shortward of ~3 µm."
            ),
        }
        visibility_report.append(vis)

        man = {
            "target_id": t["id"],
            "name": t["name"],
            "ra": ra,
            "dec": dec,
            "fov_deg": FOV,
            "bandpass": band,
            "targeting_mode": TARGETING_MODE,
            "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
            "proper_motion": {
                "pm_ra_cosdec_arcsec_yr": pm["pm_ra_cosdec_arcsec_yr"],
                "pm_dec_arcsec_yr": pm["pm_dec_arcsec_yr"],
                "citation": pm["citation"],
                "uncertainty_note": pm["uncertainty_note"],
            },
            "frames": frames,
            "source": "cached-demo",
            "is_synthetic": False,
            "credit": "NASA/JPL-Caltech/IPAC — SPHEREx at IRSA",
            "visibility": vis,
        }
        (dest / "manifest.json").write_text(json.dumps(man, indent=2, default=str))
        summary.append(
            {
                "id": t["id"],
                "name": t["name"],
                "n_frames": len(frames),
                "ra": ra,
                "dec": dec,
                "fov_deg": FOV,
                "bandpass": band,
            }
        )

    (OUT / "index.json").write_text(json.dumps({"targets": summary}, indent=2) + "\n")
    (OUT / "visibility_report.json").write_text(
        json.dumps(visibility_report, indent=2, default=str) + "\n"
    )
    print("Done", summary)
    return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
