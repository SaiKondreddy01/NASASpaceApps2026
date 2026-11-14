"""Alignment, stacking, and differencing of SPHEREx cutouts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_interp


@dataclass
class Frame:
    image: np.ndarray
    wcs: WCS
    variance: Optional[np.ndarray] = None
    flags: Optional[np.ndarray] = None
    mjd: float = 0.0
    label: str = ""


def percentile_clip(data: np.ndarray, lo: float = 1.0, hi: float = 99.0) -> tuple[float, float]:
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return 0.0, 1.0
    return float(np.percentile(finite, lo)), float(np.percentile(finite, hi))


def stretch(
    data: np.ndarray,
    mode: str = "asinh",
    lo: float = 1.0,
    hi: float = 99.0,
) -> np.ndarray:
    """Return display-scaled array in [0, 1]."""
    vmin, vmax = percentile_clip(data, lo, hi)
    x = np.nan_to_num(data, nan=vmin)
    x = np.clip(x, vmin, vmax)
    if vmax <= vmin:
        return np.zeros_like(x)
    if mode == "linear":
        y = (x - vmin) / (vmax - vmin)
    elif mode == "log":
        y = np.log1p(x - vmin) / np.log1p(vmax - vmin)
    else:  # asinh default
        y = np.arcsinh((x - vmin) / ((vmax - vmin) / 3.0))
        y = y / (np.arcsinh(3.0) + 1e-9)
    return np.clip(y, 0.0, 1.0)


def reproject_to_wcs(
    image: np.ndarray,
    wcs_in: WCS,
    wcs_out: WCS,
    shape_out: tuple[int, int],
) -> np.ndarray:
    out, _ = reproject_interp((image, wcs_in), wcs_out, shape_out=shape_out)
    return np.asarray(out, dtype=float)


def stack_mean(frames: Iterable[np.ndarray]) -> np.ndarray:
    arr = np.stack([np.asarray(f, dtype=float) for f in frames], axis=0)
    return np.nanmean(arr, axis=0)


def difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.asarray(a, dtype=float) - np.asarray(b, dtype=float)


def align_frames(frames: list[Frame], reference: Frame | None = None) -> list[np.ndarray]:
    """Reproject all frames onto the reference WCS/grid."""
    if not frames:
        return []
    ref = reference or frames[0]
    shape = ref.image.shape
    aligned = []
    for fr in frames:
        if fr is ref:
            aligned.append(np.asarray(fr.image, dtype=float))
        else:
            aligned.append(reproject_to_wcs(fr.image, fr.wcs, ref.wcs, shape))
    return aligned
