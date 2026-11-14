"""Triage tracks as known / candidate / stationary_source / likely_artifact."""

from __future__ import annotations

from typing import Any

import numpy as np

from .detect import Track

# Motion significance: |pm| / sigma_pm. Flat arcsec/yr cuts mislabel centroid noise.
SIGNIFICANCE_THRESHOLD = 3.0


def classify_track(
    track: Track,
    *,
    crossmatch: dict[str, Any] | None = None,
    near_edge: bool = False,
    flagged_fraction: float = 0.0,
    significance_threshold: float = SIGNIFICANCE_THRESHOLD,
) -> dict[str, Any]:
    reasons: list[str] = []
    crossmatch = crossmatch or {}

    if len(track.detections) < 2:
        reasons.append("single-epoch detection")
        return {"classification": "likely_artifact", "reasons": reasons, "crossmatch": crossmatch}

    if near_edge:
        reasons.append("near detector / cutout edge")
    if flagged_fraction > 0.3:
        reasons.append("high fraction of flagged pixels near source")

    # Known if cross-matched within ~2 SPHEREx pixels (~12")
    if crossmatch.get("name"):
        reasons.append(
            f"cross-matched to {crossmatch['name']} ({crossmatch.get('catalog', 'catalog')})"
        )
        return {"classification": "known", "reasons": reasons, "crossmatch": crossmatch}

    if near_edge or flagged_fraction > 0.3:
        return {"classification": "likely_artifact", "reasons": reasons, "crossmatch": crossmatch}

    pm_ra = float(track.pm_ra_arcsec_yr or 0.0)
    pm_dec = float(track.pm_dec_arcsec_yr or 0.0)
    pm = float(np.hypot(pm_ra, pm_dec))
    era = track.pm_ra_err
    ede = track.pm_dec_err

    if era is None or ede is None or era <= 0 or ede <= 0:
        reasons.append(
            "proper-motion uncertainty unavailable — cannot assess significance; "
            "not labeling as candidate"
        )
        return {
            "classification": "stationary_source",
            "reasons": reasons,
            "crossmatch": crossmatch,
            "pm_arcsec_yr": pm,
            "significance": None,
        }

    # Propagate: sigma_|pm| ≈ sqrt( (pm_ra*era)^2 + (pm_dec*ede)^2 ) / |pm|
    # For total pm uncertainty use quadrature of component errors (conservative).
    sigma_pm = float(np.hypot(era, ede))
    significance = pm / sigma_pm if sigma_pm > 0 else 0.0
    reasons.append(
        f"|μ|={pm:.2f}\"/yr, σ_μ≈{sigma_pm:.2f}\"/yr, significance={significance:.2f} "
        f"(threshold {significance_threshold})"
    )

    if significance < significance_threshold:
        reasons.append("motion not significant vs centroid noise — stationary_source")
        return {
            "classification": "stationary_source",
            "reasons": reasons,
            "crossmatch": crossmatch,
            "pm_arcsec_yr": pm,
            "significance": significance,
        }

    reasons.append("significant fitted motion without catalog match — candidate")
    return {
        "classification": "candidate",
        "reasons": reasons,
        "crossmatch": crossmatch,
        "pm_arcsec_yr": pm,
        "significance": significance,
    }
