"""Pydantic API contract for SkyFlip."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    live = "live"
    cached_demo = "cached-demo"


class HealthServiceStatus(BaseModel):
    ok: bool
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    source: DataSource = DataSource.live
    services: dict[str, HealthServiceStatus]
    demo_cache_available: bool = False
    pixel_scale_arcsec: float = 6.15


class ResolveResponse(BaseModel):
    name: str
    ra: float
    dec: float
    source: DataSource = DataSource.live
    catalog: str = "SIMBAD"
    uncertainty_arcsec: Optional[float] = None
    uncertainty_note: str = "SIMBAD coordinates; no separate uncertainty provided by resolver"


class EpochInfo(BaseModel):
    epoch_id: str
    obs_id: str
    mjd: float
    time_iso: str
    bandpass: str
    detector: int
    collection: str = ""
    cutout_url: Optional[str] = None
    central_wavelength_um: Optional[float] = None
    bandwidth_um: Optional[float] = None
    flag_summary: dict[str, int] = Field(default_factory=dict)
    quality_notes: list[str] = Field(default_factory=list)
    s_pixel_scale_arcsec: Optional[float] = 6.15


class EpochsResponse(BaseModel):
    ra: float
    dec: float
    fov_deg: float
    epochs: list[EpochInfo]
    source: DataSource = DataSource.live
    note: str = (
        "SPHEREx LVF means wavelength varies across the detector; "
        "prefer matching detector/nearby wavelength when blinking."
    )


class CutoutFrameMeta(BaseModel):
    epoch_id: str
    obs_id: str
    mjd: float
    time_iso: str
    bandpass: str
    detector: int
    image_url: str
    stretch_hint: dict[str, float] = Field(default_factory=dict)
    central_wavelength_um: Optional[float] = None
    flag_summary: dict[str, int] = Field(default_factory=dict)
    wcs: dict[str, Any] = Field(default_factory=dict)
    bunit: str = "MJy/sr"
    is_synthetic: bool = False


class CutoutsResponse(BaseModel):
    ra: float
    dec: float
    fov_deg: float
    stack: Literal["none", "detector", "all_detectors", "date"] = "none"
    frames: list[CutoutFrameMeta]
    source: DataSource = DataSource.live
    pixel_scale_arcsec: float = 6.15
    note: Optional[str] = (
        "IMAGE is surface brightness in MJy/sr; ZODI is not subtracted in Level-2 IMAGE."
    )


class DiffResponse(BaseModel):
    ra: float
    dec: float
    fov_deg: float
    epoch_a: str
    epoch_b: str
    image_url: str
    source: DataSource = DataSource.live
    note: str = "Difference of aligned cutouts on a common grid."


class Classification(str, Enum):
    known = "known"
    candidate = "candidate"
    likely_artifact = "likely_artifact"
    stationary_source = "stationary_source"


class MoverTrackPoint(BaseModel):
    epoch_id: str
    mjd: float
    ra: float
    dec: float
    ra_err_arcsec: Optional[float] = None
    dec_err_arcsec: Optional[float] = None


class MoverCandidate(BaseModel):
    id: str
    classification: Classification
    reasons: list[str] = Field(default_factory=list)
    track: list[MoverTrackPoint] = Field(default_factory=list)
    pm_ra_arcsec_yr: Optional[float] = None
    pm_dec_arcsec_yr: Optional[float] = None
    pm_ra_err_arcsec_yr: Optional[float] = None
    pm_dec_err_arcsec_yr: Optional[float] = None
    crossmatch: dict[str, Any] = Field(default_factory=dict)
    is_synthetic: bool = False


class MoversResponse(BaseModel):
    ra: float
    dec: float
    fov_deg: float
    movers: list[MoverCandidate]
    source: DataSource = DataSource.live


class PredictedTrackPoint(BaseModel):
    epoch_id: str
    mjd: float
    ra: float
    dec: float
    x_pix: Optional[float] = None
    y_pix: Optional[float] = None
    ra_err_arcsec: Optional[float] = None
    dec_err_arcsec: Optional[float] = None
    note: str = ""


class PredictedTrackResponse(BaseModel):
    name: str
    ra: float
    dec: float
    points: list[PredictedTrackPoint]
    source: DataSource = DataSource.live
    method: str = "catalog proper motion / ephemeris"
    pixel_scale_arcsec: float = 6.15


class SpectrumPoint(BaseModel):
    wavelength_um: float
    flux: float
    flux_err: Optional[float] = None
    detector: Optional[int] = None
    bandpass: Optional[str] = None


class SpectrumResponse(BaseModel):
    ra: float
    dec: float
    points: list[SpectrumPoint]
    source: DataSource = DataSource.live
    unit: str = "MJy/sr (surface brightness; conversion to point-source flux TBD)"
    method_note: str = ""
    is_synthetic: bool = False


class ScoreboardResponse(BaseModel):
    source: DataSource = DataSource.live
    results: dict[str, Any] = Field(default_factory=dict)
    is_synthetic_injected: bool = False
    explanation: str = ""


class ChangeScoreFrame(BaseModel):
    epoch_id: str
    mjd: float
    wavelength_um: Optional[float] = None
    detector: Optional[int] = None
    score: Optional[float] = None
    score_err: Optional[float] = None
    score_unit: str = "dimensionless (S/N)"
    brightness_snr: Optional[float] = None
    brightness_snr_err: Optional[float] = None
    position_shift_pix: Optional[float] = None
    position_shift_pix_err: Optional[float] = None
    position_shift_arcsec: Optional[float] = None
    position_shift_arcsec_err: Optional[float] = None
    centroid_x: Optional[float] = None
    centroid_y: Optional[float] = None
    masked_fraction: float = 0.0
    n_aperture_pixels: int = 0
    n_masked: int = 0
    wavelength_mismatched: bool = False
    status: Literal["ok", "not_computed"] = "ok"
    status_reason: str = ""
    is_synthetic: bool = False
    notes: list[str] = Field(default_factory=list)


class ChangeScoresResponse(BaseModel):
    ra: float
    dec: float
    radius_pix: float
    metric: Literal["brightness_snr", "position_shift", "combined"]
    reference: Literal["median_others", "first_epoch", "previous_epoch"]
    frames: list[ChangeScoreFrame]
    motion: dict[str, Any] = Field(default_factory=dict)
    source: DataSource = DataSource.live
    pixel_scale_arcsec: float = 6.15
    aperture_x_pix: Optional[float] = None
    aperture_y_pix: Optional[float] = None
    is_synthetic: bool = False
    banner: Optional[str] = None
    metric_note: str = (
        "Change = difference from reference in the aperture (candidates only; "
        "not a discovery). See docs/SCIENCE_LIMITS.md."
    )
