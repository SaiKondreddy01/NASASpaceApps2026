export type DataSource = "live" | "cached-demo";

export interface HealthResponse {
  status: string;
  source: DataSource;
  services: Record<string, { ok: boolean; detail?: string }>;
  demo_cache_available: boolean;
  pixel_scale_arcsec: number;
}

export interface ResolveResponse {
  name: string;
  ra: number;
  dec: number;
  source: DataSource;
  catalog: string;
  uncertainty_arcsec: number | null;
  uncertainty_note: string;
}

export interface CutoutFrame {
  epoch_id: string;
  obs_id: string;
  mjd: number;
  time_iso: string;
  bandpass: string;
  detector: number;
  image_url: string;
  central_wavelength_um?: number | null;
  flag_summary?: Record<string, number>;
  is_synthetic?: boolean;
  /** Optional float32 little-endian .bin from IRSA IMAGE (browser stretch). */
  float_bin?: string;
  float_shape?: [number, number];
  flags_bin?: string;
  bunit?: string;
  collection?: string;
  native_dtype?: string;
  png_unique_gray_levels?: number;
}

export interface CutoutsResponse {
  ra: number;
  dec: number;
  fov_deg: number;
  frames: CutoutFrame[];
  source: DataSource;
  pixel_scale_arcsec: number;
  note?: string | null;
  stack?: string;
}

export interface PredictedTrackPoint {
  epoch_id: string;
  mjd: number;
  ra: number;
  dec: number;
  /** Pixel coords in the matching frame (native cutout grid). */
  x_pix?: number | null;
  y_pix?: number | null;
  ra_err_arcsec?: number | null;
  dec_err_arcsec?: number | null;
  note?: string;
}

export interface SpectrumPoint {
  wavelength_um: number;
  flux: number;
  flux_err?: number | null;
  detector?: number;
  bandpass?: string;
}

export interface MoverCandidate {
  id: string;
  classification: "known" | "candidate" | "likely_artifact" | "stationary_source";
  reasons: string[];
  track: { epoch_id: string; mjd: number; ra: number; dec: number; ra_err_arcsec?: number; dec_err_arcsec?: number }[];
  pm_ra_arcsec_yr?: number | null;
  pm_dec_arcsec_yr?: number | null;
  pm_ra_err_arcsec_yr?: number | null;
  pm_dec_err_arcsec_yr?: number | null;
  is_synthetic: boolean;
}

export interface TestTarget {
  id: string;
  name: string;
  ra?: number;
  dec?: number;
  resolve?: boolean;
}

export const WISE0855 = {
  id: "wise0855",
  name: "WISE 0855",
  ra: 133.79512917,
  dec: -7.24514722,
};

export type ChangeMetric = "brightness_snr" | "position_shift" | "combined";
export type ChangeReference = "median_others" | "first_epoch" | "previous_epoch";
export type ChangeSortMode = "time" | "change";

export interface ChangeScoreFrame {
  epoch_id: string;
  mjd: number;
  wavelength_um?: number | null;
  detector?: number | null;
  score: number | null;
  score_err: number | null;
  score_unit: string;
  brightness_snr?: number | null;
  brightness_snr_err?: number | null;
  position_shift_pix?: number | null;
  position_shift_pix_err?: number | null;
  position_shift_arcsec?: number | null;
  position_shift_arcsec_err?: number | null;
  centroid_x?: number | null;
  centroid_y?: number | null;
  masked_fraction: number;
  n_aperture_pixels: number;
  n_masked: number;
  wavelength_mismatched: boolean;
  status: "ok" | "not_computed";
  status_reason?: string;
  is_synthetic?: boolean;
  notes?: string[];
}

export interface ChangeScoresResponse {
  ra: number;
  dec: number;
  radius_pix: number;
  metric: ChangeMetric;
  reference: ChangeReference;
  frames: ChangeScoreFrame[];
  motion: Record<string, unknown>;
  source: DataSource;
  pixel_scale_arcsec: number;
  aperture_x_pix?: number | null;
  aperture_y_pix?: number | null;
  is_synthetic?: boolean;
  banner?: string | null;
  metric_note?: string;
}

export interface TrailPoint {
  epoch_id: string;
  mjd: number;
  x: number;
  y: number;
  score?: number | null;
  index: number;
}

/** RA/Dec from cached demo manifests so buttons work offline without resolve. */
export const TEST_TARGETS: TestTarget[] = [
  {
    id: "barnards_star",
    name: "Barnard's Star",
    ra: 269.4520769586187,
    dec: 4.69336496657667,
    resolve: true,
  },
  {
    id: "epsilon_indi_b",
    name: "Epsilon Indi B",
    ra: 331.04414658852124,
    dec: -56.78284419511611,
    resolve: true,
  },
  WISE0855,
  {
    id: "rw_aurigae",
    name: "RW Aurigae",
    ra: 76.95652603458,
    dec: 30.40143817389,
    resolve: true,
  },
  {
    id: "r_draconis",
    name: "R Draconis",
    ra: 248.16761083295,
    dec: 66.75497941722,
    resolve: true,
  },
];
