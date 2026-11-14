#!/usr/bin/env python3
"""Precompute change_scores.json for each demo target (offline Change Slider)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.cache import DEMO_DATA, write_json  # noqa: E402
from app.change_scores import (  # noqa: E402
    load_demo_frame_inputs,
    net_motion,
    score_frames,
)

TARGETS = [
    "wise0855",
    "barnards_star",
    "epsilon_indi_b",
    "rw_aurigae",
    "r_draconis",
]
METRICS = ("brightness_snr", "position_shift", "combined")
REFERENCES = ("median_others", "first_epoch", "previous_epoch")
RADIUS = 1.5


def main() -> None:
    for tid in TARGETS:
        demo_dir = DEMO_DATA / tid
        man_path = demo_dir / "manifest.json"
        if not man_path.exists():
            print(f"skip {tid}: no manifest")
            continue
        import json

        man = json.loads(man_path.read_text(encoding="utf-8"))
        ra = float(man["ra"])
        dec = float(man["dec"])
        frames, ax, ay = load_demo_frame_inputs(
            demo_dir, ra=ra, dec=dec, target_ra=ra, target_dec=dec
        )
        by_key: dict = {}
        default_payload = None
        for metric in METRICS:
            for reference in REFERENCES:
                scores = score_frames(
                    frames,
                    metric=metric,  # type: ignore[arg-type]
                    reference=reference,  # type: ignore[arg-type]
                    aperture_pix=RADIUS,
                )
                payload = {
                    "ra": ra,
                    "dec": dec,
                    "radius_pix": RADIUS,
                    "metric": metric,
                    "reference": reference,
                    "aperture_x_pix": ax,
                    "aperture_y_pix": ay,
                    "frames": [s.to_dict() for s in scores],
                    "motion": net_motion(scores),
                    "is_synthetic": False,
                    "source": "cached-demo",
                    "note": (
                        "Precomputed from demo float bins; VARIANCE not packed — "
                        "brightness S/N uses annulus scatter when needed. "
                        "Candidates only — not a discovery."
                    ),
                }
                by_key[f"{metric}|{reference}|{RADIUS}"] = payload
                if metric == "brightness_snr" and reference == "median_others":
                    default_payload = payload
        out = {
            "target_id": tid,
            "ra": ra,
            "dec": dec,
            "default": default_payload,
            "by_key": by_key,
        }
        out_path = demo_dir / "change_scores.json"
        write_json(out_path, out)
        n = len(default_payload["frames"]) if default_payload else 0
        print(f"wrote {out_path} ({n} frames)")


if __name__ == "__main__":
    main()
