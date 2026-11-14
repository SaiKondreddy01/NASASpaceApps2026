"""
Per-frame change scores at a sky position (candidates only — not discoveries).

Metric (documented in docs/SCIENCE_LIMITS.md):
  brightness_snr = (Σ(frame − reference − annulus_bg) in aperture)
                   / sqrt(Σ variance_eff in aperture)
  position_shift = centroid(frame) − centroid(reference) in the aperture,
                   in pixels and arcsec, with uncertainty from centroid noise.
  combined = hypot(brightness_snr, position_shift_snr) when both available.

Wavelength-matched peers only for the median reference; mismatched frames are
flagged wavelength_mismatched=True and may still receive a score vs a global
fallback reference with an explicit warning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

import numpy as np

from .adapters.spherex import FLAG_BITS, PIXEL_SCALE_ARCSEC

ReferenceKind = Literal["median_others", "first_epoch", "previous_epoch"]
MetricKind = Literal["brightness_snr", "position_shift", "combined"]

DEFAULT_APERTURE_PIX = 1.5  # ~1–2 SPHEREx pixels (6.15″ each)
DEFAULT_ANNULUS = (2.5, 4.0)  # inner, outer radius in pixels
DEFAULT_WAVELENGTH_TOL_UM = 0.15

# Mask contamination / bad pixels; keep SOURCE and FULLSAMPLE (informational).
_BAD_FLAG_NAMES = (
    "TRANSIENT",
    "OVERFLOW",
    "SUR_ERROR",
    "NONFUNC",
    "DICHROIC",
    "MISSING_DATA",
    "HOT",
    "COLD",
    "PHANMISS",
    "NONLINEAR",
    "PERSIST",
    "OUTLIER",
    "GHOST",
    "GHOST_FPA",
    "GHOST_EXT",
    "STREAK",
    "BLOOM",
    "SNOWBALL",
    "HALO",
    "SATELLITE_HALO",
)
BAD_FLAG_MASK = 0
for _name in _BAD_FLAG_NAMES:
    BAD_FLAG_MASK |= 1 << FLAG_BITS[_name]


@dataclass
class FrameInput:
    epoch_id: str
    mjd: float
    image: np.ndarray
    variance: Optional[np.ndarray] = None
    flags: Optional[np.ndarray] = None
    wavelength_um: Optional[float] = None
    detector: Optional[int] = None
    x_pix: float = 0.0  # aperture center in this frame's pixel grid
    y_pix: float = 0.0


@dataclass
class FrameChangeScore:
    epoch_id: str
    mjd: float
    wavelength_um: Optional[float]
    detector: Optional[int]
    score: Optional[float]
    score_err: Optional[float]
    score_unit: str
    brightness_snr: Optional[float]
    brightness_snr_err: Optional[float]
    position_shift_pix: Optional[float]
    position_shift_pix_err: Optional[float]
    position_shift_arcsec: Optional[float]
    position_shift_arcsec_err: Optional[float]
    centroid_x: Optional[float]
    centroid_y: Optional[float]
    masked_fraction: float
    n_aperture_pixels: int
    n_masked: int
    wavelength_mismatched: bool
    status: Literal["ok", "not_computed"]
    status_reason: str = ""
    is_synthetic: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _circular_mask(shape: tuple[int, int], x0: float, y0: float, r: float) -> np.ndarray:
    yy, xx = np.indices(shape)
    return (xx - x0) ** 2 + (yy - y0) ** 2 <= r**2


def _annulus_mask(
    shape: tuple[int, int], x0: float, y0: float, r_in: float, r_out: float
) -> np.ndarray:
    yy, xx = np.indices(shape)
    rr2 = (xx - x0) ** 2 + (yy - y0) ** 2
    return (rr2 >= r_in**2) & (rr2 <= r_out**2)


def _valid_pixels(
    image: np.ndarray,
    mask: np.ndarray,
    flags: Optional[np.ndarray],
) -> np.ndarray:
    """Boolean mask of usable pixels inside `mask` (finite, not bad-flagged).

    SOURCE / FULLSAMPLE bits are informational and are NOT treated as bad.
    """
    ok = mask & np.isfinite(image)
    if flags is not None:
        fl = np.asarray(flags).astype(np.uint64)
        ok = ok & ((fl & BAD_FLAG_MASK) == 0)
    return ok


def _annulus_background(
    image: np.ndarray,
    flags: Optional[np.ndarray],
    x0: float,
    y0: float,
    r_in: float,
    r_out: float,
) -> tuple[float, int]:
    am = _annulus_mask(image.shape, x0, y0, r_in, r_out)
    ok = _valid_pixels(image, am, flags)
    if not np.any(ok):
        return 0.0, 0
    return float(np.nanmedian(image[ok])), int(np.count_nonzero(ok))


def _weighted_centroid(
    image: np.ndarray,
    ok: np.ndarray,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Flux-weighted centroid and rough 1/SNR pixel uncertainty."""
    if not np.any(ok):
        return None, None, None, None
    yy, xx = np.indices(image.shape)
    w = np.clip(image[ok] - np.nanmin(image[ok]), 0, None)
    # Use absolute residual from median as weight floor
    med = float(np.nanmedian(image[ok]))
    w = np.abs(image[ok] - med) + 1e-6
    wsum = float(np.sum(w))
    if wsum <= 0:
        return None, None, None, None
    cx = float(np.sum(xx[ok] * w) / wsum)
    cy = float(np.sum(yy[ok] * w) / wsum)
    # Rough centroid uncertainty ~ FWHM/(2.35*SNR); use pixel scatter proxy
    snr = wsum / (np.std(image[ok]) * np.sqrt(np.count_nonzero(ok)) + 1e-9)
    pix_err = max(0.05, 1.5 / max(snr, 1.0))
    return cx, cy, pix_err, pix_err


def _brightness_residual(
    image: np.ndarray,
    reference: np.ndarray,
    variance: Optional[np.ndarray],
    flags: Optional[np.ndarray],
    x0: float,
    y0: float,
    aperture_pix: float,
    annulus: tuple[float, float],
) -> tuple[Optional[float], Optional[float], float, int, int, str]:
    """
    Returns (snr, snr_err, masked_fraction, n_ap, n_masked, reason).
    snr is dimensionless (signal / sigma).
    """
    ap = _circular_mask(image.shape, x0, y0, aperture_pix)
    n_ap = int(np.count_nonzero(ap))
    if n_ap == 0:
        return None, None, 1.0, 0, 0, "aperture outside image"

    ok = _valid_pixels(image, ap, flags) & np.isfinite(reference)
    if variance is not None:
        ok = ok & np.isfinite(variance) & (variance > 0)
    n_ok = int(np.count_nonzero(ok))
    n_masked = n_ap - n_ok
    masked_fraction = float(n_masked / n_ap) if n_ap else 1.0
    if n_ok == 0:
        return None, None, masked_fraction, n_ap, n_masked, "all aperture pixels masked or NaN"

    bg, n_bg = _annulus_background(image - reference, flags, x0, y0, annulus[0], annulus[1])
    resid = (image - reference)[ok] - bg
    signal = float(np.sum(resid))

    if variance is not None:
        # Variance of difference ≈ var_frame + var_ref; without per-frame ref var,
        # use 2× frame variance as a conservative stand-in when ref is a median stack.
        var_eff = np.asarray(variance, dtype=float)[ok] * 2.0
        sigma = float(np.sqrt(np.sum(var_eff)))
    else:
        # Fallback: annulus scatter (no formal VARIANCE) — flag in reason
        am = _annulus_mask(image.shape, x0, y0, annulus[0], annulus[1])
        aok = _valid_pixels(image - reference, am, flags)
        if np.count_nonzero(aok) < 3:
            return None, None, masked_fraction, n_ap, n_masked, "no variance and insufficient annulus"
        sigma = float(np.std((image - reference)[aok]) * np.sqrt(n_ok))
        if sigma <= 0:
            return None, None, masked_fraction, n_ap, n_masked, "zero scatter in annulus"

    if sigma <= 0 or not np.isfinite(sigma):
        return None, None, masked_fraction, n_ap, n_masked, "non-positive uncertainty"
    snr = signal / sigma
    # Uncertainty on the SNR estimate itself is ~1 for Gaussian noise (reporting σ_SNR≈1)
    # when variance is known; if annulus fallback, still ~1 but note no VARIANCE.
    snr_err = 1.0
    reason = ""
    if variance is None:
        reason = "uncertainty from annulus scatter (no VARIANCE extension)"
    if n_bg == 0:
        reason = (reason + "; " if reason else "") + "annulus empty — background set to 0"
    return snr, snr_err, masked_fraction, n_ap, n_masked, reason


def _wavelength_peers(
    frames: list[FrameInput],
    idx: int,
    tol_um: float,
) -> list[int]:
    """Indices of frames within tol of frame idx's wavelength (excluding idx)."""
    w0 = frames[idx].wavelength_um
    if w0 is None:
        return [i for i in range(len(frames)) if i != idx]
    peers = []
    for i, fr in enumerate(frames):
        if i == idx:
            continue
        if fr.wavelength_um is None:
            continue
        if abs(fr.wavelength_um - w0) <= tol_um:
            peers.append(i)
    return peers


def _build_reference(
    frames: list[FrameInput],
    idx: int,
    kind: ReferenceKind,
    tol_um: float,
) -> tuple[np.ndarray, bool, str]:
    """
    Returns (reference_image, wavelength_mismatched, note).
    wavelength_mismatched True if we could not form a λ-matched peer set.
    """
    shape = frames[idx].image.shape
    if kind == "first_epoch":
        return np.asarray(frames[0].image, dtype=float), False, "reference=first_epoch"
    if kind == "previous_epoch":
        if idx == 0:
            return np.asarray(frames[0].image, dtype=float), False, "reference=previous_epoch (self for epoch 0)"
        return (
            np.asarray(frames[idx - 1].image, dtype=float),
            False,
            "reference=previous_epoch",
        )

    # median_others — prefer wavelength-matched peers
    peers = _wavelength_peers(frames, idx, tol_um)
    mismatched = False
    note = "reference=median of wavelength-matched others"
    if len(peers) < 1:
        peers = [i for i in range(len(frames)) if i != idx]
        mismatched = True
        note = (
            "reference=median of all other epochs "
            "(no wavelength-matched peers within "
            f"±{tol_um} µm — score flagged wavelength_mismatched)"
        )
    if not peers:
        return np.asarray(frames[idx].image, dtype=float), True, "no other frames for reference"

    imgs = [np.asarray(frames[i].image, dtype=float) for i in peers]
    h = min(im.shape[0] for im in imgs + [np.asarray(frames[idx].image)])
    w = min(im.shape[1] for im in imgs + [np.asarray(frames[idx].image)])
    if any(im.shape != (h, w) for im in imgs) or shape != (h, w):
        mismatched = True
        note += "; cropped to common shape (frames not on identical grid)"
    stack = np.stack([im[:h, :w] for im in imgs], axis=0)
    with np.errstate(all="ignore"):
        ref = np.nanmedian(stack, axis=0)
    if not np.any(np.isfinite(ref)):
        # Degenerate peer stack — fall back to zeros so caller reports not_computed
        ref = np.zeros((h, w), dtype=float)
        mismatched = True
        note += "; reference all-NaN — substituted zeros"
    out = np.full(shape, np.nan, dtype=float)
    hh = min(shape[0], ref.shape[0])
    ww = min(shape[1], ref.shape[1])
    out[:hh, :ww] = ref[:hh, :ww]
    return out, mismatched, note


def score_frames(
    frames: list[FrameInput],
    *,
    metric: MetricKind = "brightness_snr",
    reference: ReferenceKind = "median_others",
    aperture_pix: float = DEFAULT_APERTURE_PIX,
    annulus: tuple[float, float] = DEFAULT_ANNULUS,
    wavelength_tol_um: float = DEFAULT_WAVELENGTH_TOL_UM,
    pixel_scale_arcsec: float = PIXEL_SCALE_ARCSEC,
    is_synthetic: bool = False,
) -> list[FrameChangeScore]:
    """Compute per-frame change scores. Frames must share a common pixel grid."""
    if not frames:
        return []

    # Reference centroid from first frame (for position shifts)
    ref_cx = ref_cy = None
    ref_img0, _, _ = _build_reference(frames, 0, reference, wavelength_tol_um)
    ap0 = _circular_mask(frames[0].image.shape, frames[0].x_pix, frames[0].y_pix, aperture_pix)
    ok0 = _valid_pixels(ref_img0, ap0, frames[0].flags)
    ref_cx, ref_cy, _, _ = _weighted_centroid(ref_img0, ok0)

    results: list[FrameChangeScore] = []
    for i, fr in enumerate(frames):
        ref_img, mismatched, ref_note = _build_reference(frames, i, reference, wavelength_tol_um)
        notes = [ref_note]
        b_snr, b_err, masked_frac, n_ap, n_masked, b_reason = _brightness_residual(
            np.asarray(fr.image, dtype=float),
            ref_img,
            fr.variance,
            fr.flags,
            fr.x_pix,
            fr.y_pix,
            aperture_pix,
            annulus,
        )
        if b_reason:
            notes.append(b_reason)

        # Position shift vs reference centroid
        ap = _circular_mask(fr.image.shape, fr.x_pix, fr.y_pix, aperture_pix)
        ok = _valid_pixels(np.asarray(fr.image, dtype=float), ap, fr.flags)
        cx, cy, cx_err, cy_err = _weighted_centroid(np.asarray(fr.image, dtype=float), ok)
        shift_pix = shift_pix_err = shift_as = shift_as_err = None
        if cx is not None and cy is not None and ref_cx is not None and ref_cy is not None:
            dx = cx - ref_cx
            dy = cy - ref_cy
            shift_pix = float(np.hypot(dx, dy))
            # Propagate centroid errors
            if cx_err is not None and cy_err is not None:
                shift_pix_err = float(np.hypot(cx_err, cy_err))
            else:
                shift_pix_err = None
            shift_as = shift_pix * pixel_scale_arcsec
            shift_as_err = (
                None if shift_pix_err is None else shift_pix_err * pixel_scale_arcsec
            )

        # Choose displayed score
        score = score_err = None
        unit = "dimensionless (S/N)"
        status: Literal["ok", "not_computed"] = "ok"
        status_reason = ""

        if metric == "brightness_snr":
            score, score_err = b_snr, b_err
            unit = "dimensionless (brightness S/N)"
            if score is None:
                status = "not_computed"
                status_reason = b_reason or "brightness S/N not computed"
        elif metric == "position_shift":
            score, score_err = shift_as, shift_as_err
            unit = "arcsec"
            if score is None:
                status = "not_computed"
                status_reason = "centroid not computed (masked/empty aperture)"
        else:  # combined
            unit = "dimensionless (hypot of brightness S/N and shift S/N)"
            parts = []
            if b_snr is not None:
                parts.append(abs(b_snr))
            if shift_pix is not None and shift_pix_err and shift_pix_err > 0:
                parts.append(abs(shift_pix / shift_pix_err))
            if not parts:
                status = "not_computed"
                status_reason = "neither brightness nor position S/N available"
            else:
                score = float(np.hypot(*parts)) if len(parts) > 1 else float(parts[0])
                score_err = 1.0  # approximate

        if mismatched:
            notes.append("wavelength_mismatched")

        results.append(
            FrameChangeScore(
                epoch_id=fr.epoch_id,
                mjd=fr.mjd,
                wavelength_um=fr.wavelength_um,
                detector=fr.detector,
                score=score,
                score_err=score_err,
                score_unit=unit,
                brightness_snr=b_snr,
                brightness_snr_err=b_err,
                position_shift_pix=shift_pix,
                position_shift_pix_err=shift_pix_err,
                position_shift_arcsec=shift_as,
                position_shift_arcsec_err=shift_as_err,
                centroid_x=cx,
                centroid_y=cy,
                masked_fraction=masked_frac,
                n_aperture_pixels=n_ap,
                n_masked=n_masked,
                wavelength_mismatched=mismatched,
                status=status,
                status_reason=status_reason,
                is_synthetic=is_synthetic,
                notes=notes,
            )
        )
    return results


def filter_by_score_range(
    scores: list[FrameChangeScore],
    lo: Optional[float],
    hi: Optional[float],
) -> list[FrameChangeScore]:
    """Keep frames whose score is within [lo, hi]. not_computed frames are dropped when filtering."""
    out = []
    for s in scores:
        if s.status != "ok" or s.score is None:
            continue
        if lo is not None and s.score < lo:
            continue
        if hi is not None and s.score > hi:
            continue
        out.append(s)
    return out


def load_demo_frame_inputs(
    demo_dir: Any,
    *,
    ra: float,
    dec: float,
    target_ra: float,
    target_dec: float,
    pixel_scale_arcsec: float = PIXEL_SCALE_ARCSEC,
) -> tuple[list[FrameInput], float, float]:
    """
    Load float32 IMAGE (+ optional FLAGS) bins from a demo-data target folder.
    Aperture pixel from approximate TAN offset relative to cutout center
    (demo manifests lack full WCS).
    Returns (frames, x_pix, y_pix).
    """
    from pathlib import Path

    demo_dir = Path(demo_dir)
    manifest_path = demo_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest in {demo_dir}")
    import json

    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames_meta = man.get("frames") or []
    if not frames_meta:
        raise FileNotFoundError(f"no frames in {manifest_path}")

    shape0 = tuple(frames_meta[0].get("float_shape") or [29, 29])

    loaded: list[tuple[dict, np.ndarray, Optional[np.ndarray]]] = []
    for fr in frames_meta:
        shape = tuple(fr.get("float_shape") or shape0)
        h, w = int(shape[0]), int(shape[1])
        bin_name = fr.get("float_bin")
        if not bin_name:
            continue
        bin_path = demo_dir / bin_name
        if not bin_path.exists():
            continue
        img = np.fromfile(bin_path, dtype=np.float32).reshape(h, w).astype(float)
        flags = None
        flags_name = fr.get("flags_bin")
        if flags_name:
            fp = demo_dir / flags_name
            if fp.exists():
                raw = fp.read_bytes()
                n = h * w
                if len(raw) == n * 2:
                    flags = np.frombuffer(raw, dtype=np.int16).reshape(h, w).astype(np.int32)
                elif len(raw) == n * 4:
                    flags = np.frombuffer(raw, dtype=np.int32).reshape(h, w)
                elif len(raw) == n:
                    flags = np.frombuffer(raw, dtype=np.uint8).reshape(h, w).astype(np.int32)
        loaded.append((fr, img, flags))
    if not loaded:
        raise FileNotFoundError(f"no float bins readable in {demo_dir}")

    # Common grid: majority native shape (skip odd reprojected outliers)
    from collections import Counter

    shape_counts = Counter(im.shape for _, im, _ in loaded)
    common_shape = shape_counts.most_common(1)[0][0]
    ch, cw = common_shape
    # Recompute aperture for the common grid
    scale_deg = pixel_scale_arcsec / 3600.0
    cosd = float(np.cos(np.deg2rad(target_dec)))
    dx = (ra - target_ra) * cosd / scale_deg
    dy = (dec - target_dec) / scale_deg
    x_pix = (cw - 1) / 2.0 - dx
    y_pix = (ch - 1) / 2.0 + dy

    out: list[FrameInput] = []
    for fr, img, flags in loaded:
        if img.shape != common_shape:
            # Center-crop larger frames; skip smaller
            if img.shape[0] < ch or img.shape[1] < cw:
                continue
            y0 = (img.shape[0] - ch) // 2
            x0 = (img.shape[1] - cw) // 2
            img = img[y0 : y0 + ch, x0 : x0 + cw]
            if flags is not None:
                flags = flags[y0 : y0 + ch, x0 : x0 + cw]
        # No VARIANCE sidecars in demo pack — metric falls back to annulus scatter
        out.append(
            FrameInput(
                epoch_id=str(fr["epoch_id"]),
                mjd=float(fr["mjd"]),
                image=img,
                variance=None,
                flags=flags,
                wavelength_um=fr.get("central_wavelength_um"),
                detector=fr.get("detector"),
                x_pix=float(x_pix),
                y_pix=float(y_pix),
            )
        )
    if not out:
        raise FileNotFoundError(f"no common-shape float bins in {demo_dir}")
    return out, float(x_pix), float(y_pix)


def net_motion(
    scores: list[FrameChangeScore],
    *,
    pixel_scale_arcsec: float = PIXEL_SCALE_ARCSEC,
) -> dict[str, Any]:
    """
    Total displacement and apparent motion from centroids with real epochs.
    Requires ≥3 points with centroids; otherwise returns too_few_points.
    """
    pts = [
        s
        for s in scores
        if s.centroid_x is not None and s.centroid_y is not None and np.isfinite(s.mjd)
    ]
    pts = sorted(pts, key=lambda s: s.mjd)
    if len(pts) < 3:
        return {
            "status": "too_few_points",
            "n_points": len(pts),
            "message": "too few points to estimate motion",
            "total_displacement_arcsec": None,
            "total_displacement_arcsec_err": None,
            "pm_arcsec_yr": None,
            "pm_arcsec_yr_err": None,
            "uncertainty_note": "no uncertainty available",
        }
    x0, y0 = pts[0].centroid_x, pts[0].centroid_y
    x1, y1 = pts[-1].centroid_x, pts[-1].centroid_y
    dpix = float(np.hypot(x1 - x0, y1 - y0))
    # Endpoint centroid errors if present
    e0 = pts[0].position_shift_pix_err or 0.2
    e1 = pts[-1].position_shift_pix_err or 0.2
    dpix_err = float(np.hypot(e0, e1))
    das = dpix * pixel_scale_arcsec
    das_err = dpix_err * pixel_scale_arcsec
    dt_yr = (pts[-1].mjd - pts[0].mjd) / 365.25
    if dt_yr <= 0:
        return {
            "status": "ok",
            "n_points": len(pts),
            "total_displacement_arcsec": das,
            "total_displacement_arcsec_err": das_err,
            "pm_arcsec_yr": None,
            "pm_arcsec_yr_err": None,
            "uncertainty_note": "non-positive time baseline — rate not computed",
        }
    pm = das / dt_yr
    pm_err = das_err / dt_yr
    return {
        "status": "ok",
        "n_points": len(pts),
        "total_displacement_arcsec": das,
        "total_displacement_arcsec_err": das_err,
        "pm_arcsec_yr": pm,
        "pm_arcsec_yr_err": pm_err,
        "dt_yr": dt_yr,
        "uncertainty_note": (
            f"endpoint centroid σ propagated; pixel scale {pixel_scale_arcsec}″ "
            "(SPHEREx Spectral Image)"
        ),
        "trail": [
            {
                "epoch_id": s.epoch_id,
                "mjd": s.mjd,
                "x": s.centroid_x,
                "y": s.centroid_y,
                "score": s.score,
            }
            for s in pts
        ],
    }
