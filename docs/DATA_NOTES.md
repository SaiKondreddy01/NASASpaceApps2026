# SPHEREx / IRSA data access notes (Phase 0)

**Last verified:** 2026-11-13 (local probes against IRSA + IRSA User Guide dated 2026-11-12).

**Honesty rule:** only facts below were checked against official IRSA docs, IRSA tutorial notebooks, the SPHEREx Explanatory Supplement PDF, and live TAP/SIA/cutout calls. Anything not verified is marked `TODO(VERIFY)`.

## Official challenge Resources tab

Verified from the challenge page HTML (Planet X and SPHEREx → Resources) on 2026-11-13:

| Resource | URL |
| --- | --- |
| NASA/IPAC IRSA — SPHEREx | https://irsa.ipac.caltech.edu/Missions/spherex.html |
| SPHEREx Tutorial Notebooks | https://caltech-ipac.github.io/irsa-tutorials/spherex/ |
| WiseView (WISE blink inspiration) | http://byw.tools/wiseview |
| Gaia Mission Data (use DR3) | https://archive.stsci.edu/missions-and-data/gaia |
| Backyard Worlds (Background) | http://backyardworlds.org/ |

Full statement text archived in `docs/CHALLENGE_STATEMENT.md`.

## How we find observations covering a sky position

### Preferred for freshness: IRSA TAP (`spherex.artifact` + `spherex.plane`)

Verified from IRSA notebook [Download SPHEREx Spectral Image cutouts](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/):

- Endpoint: `https://irsa.ipac.caltech.edu/TAP/sync` (also via `astroquery.ipac.irsa.Irsa.query_tap`).
- Construct cutout URLs as:

```sql
SELECT
  'https://irsa.ipac.caltech.edu/' || a.uri
    || '?center={ra},{dec}d&size={size_deg}' AS uri,
  p.time_bounds_lower,
  p.energy_bandpassname
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly)
  AND p.energy_bandpassname = '{bandpass}'
ORDER BY p.time_bounds_lower
```

- Bandpass names verified in docs/notebooks: `SPHEREx-D1` … `SPHEREx-D6` (one per detector array).
- TAP is recommended when you need data immediately after weekly ingestion; SIA can lag ~1 day ([IRSA Data Access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/), cutouts notebook).

### Also usable: SIA2

- Endpoint: `https://irsa.ipac.caltech.edu/SIA?COLLECTION=…`
- Collections verified in IRSA Data Access (2026-11-12):
  - `spherex_dr1`, `spherex_dr1_deep`
  - `spherex_qr3`, `spherex_qr3_deep`
  - `spherex_dr1_cube` (All-Sky Cube)
- **SkyFlip primary discovery** queries all four Spectral Image collections via SIA2, then builds IBE cutouts from `access_url`.
- DR1 + QR3 supersede QR2; QR2 is browsable but not searchable via SIA2.
- Returned columns used live: `access_url` (on-prem IBE FITS URL), `cloud_access` (AWS bucket/key), `obs_id`, `t_min`/`t_max` (MJD), `energy_bandpassname`, `s_pixel_scale`.

### ObsCore convenience table

- Live query worked: `spherex.obscore` via TAP, filtering with `CONTAINS(POINT('ICRS', ra, dec), s_region) = 1`.
- `access_url` here is often a **datalink** URL (`/datalink/links/spherex?ID=…`), not a direct IBE FITS path. Prefer `artifact.uri` or SIA `access_url` for cutouts.

## How we read a pixel rectangle efficiently

Verified from [IRSA IBE Cutouts](https://irsa.ipac.caltech.edu/ibe/cutouts.html) and [SPHEREx Data Access → Cutouts](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/):

1. Obtain on-prem FITS URL under `/ibe/data/spherex/…`.
2. Append cutout query string (no separate HTTP Range API required for SPHEREx MEFs — IBE returns a MEF cutout):

```text
{access_url}?center={ra},{dec}&size={size}
```

- `center` default units: degrees (J2000 RA, Dec). Explicit forms: `deg`, `pix`.
- `size` default units: degrees. Examples: `0.05`, `3arcmin`, `100pix`.
- SPHEREx cutouts are **not gzipped** (unlike many other IBE datasets).
- All MEF extensions are cut the same way; returned file is still a MEF.
- Cutout axes stay aligned with the parent exposure (spacecraft orientation), not necessarily north-up.

Example verified live (WISE 0855, detector D1, 0.05°):

```text
https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_1B/l2b-v27-2026-197/1/level2_2025W19_1B_0241_1D1_spx_l2b-v27-2026-197.fits?center=133.79512917,-7.24514722d&size=0.05
```

Downloaded successfully (~4 MB MEF) on 2026-11-13.

**Note:** Full-file HTTP Range / Astropy `Cutout2D` on remote files is mentioned by IRSA as an alternative pattern for other datasets; for SPHEREx we use the IBE cutout query string as documented.

## Spectral Image MEF layout (Level 2)

Verified from [SPHEREx Data Products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/) and intro notebook:

| HDU | EXTNAME (typical) | Contents |
| --- | --- | --- |
| 0 | PRIMARY | Metadata (`VERSION`, etc.); no image |
| 1 | IMAGE | Calibrated surface brightness, **MJy/sr**, 2040×2040 native; **zodiacal light NOT subtracted** |
| 2 | FLAGS | Per-pixel bit flags (Table 16 of Explanatory Supplement) |
| 3 | VARIANCE | Variance in **(MJy/sr)²** |
| 4 | ZODI | Modeled zodiacal background, MJy/sr (reference; not subtracted from IMAGE) |
| 5 | EPSF (DR1/QR3) or PSF (QR2) | Effective / exposure-averaged PSFs |
| 6 | WCS-WAVE | Spectral WCS lookup: control-point grid → (central wavelength, bandwidth) |

Filename pattern:

```text
level2_[ObservationID]D[Detector]_spx_l2b-v[Version]-[ProcessingDate].fits
```

Directory layout under release root (`dr1` / `qr3` / `qr2`):

```text
level2/[PlanningPeriod]/l2b-v[Version]-[ProcessingDate]/[Detector]/
```

## Six detector arrays and 102 bands

Verified from Data Products + Caltech instrument page + Explanatory Supplement:

- Two FPAs behind a dichroic; **6** H2RG arrays (detectors **1–6**), each with an LVF.
- Wavelength coverage by detector/band (Data Products wording):
  - Band 1: 0.75–1.09 µm; R≈39
  - Band 2: 1.10–1.62 µm; R≈41
  - Band 3: 1.63–2.41 µm; R≈41
  - Band 4: 2.42–3.82 µm; R≈35
  - Band 5: 3.83–4.41 µm; R≈112
  - Band 6: 4.42–5.00 µm; R≈128
- All-Sky Cube uses **102 spectral channels** = channels 1–17 × 6 detectors (cube docs). Native Spectral Images store wavelength **per pixel** via LVF + WCS-WAVE (not a fixed band cube per exposure).
- Some observations omit some detectors if quality checks fail.

### How wavelength is stored per pixel

- `WCS-WAVE` extension: FITS spectral WCS lookup table (X, Y control points → central λ and bandwidth).
- Intro / cutouts notebooks: read with `WCS(header, fobj=hdul, key="W")` then `pixel_to_world(x, y)`.
- For science analysis, IRSA also provides calibration product `spectral_wcs` with `CWAVE` / `CBAND` images; WCS-WAVE in the MEF is intended for visualization (~1 nm bilinear interpolation accuracy per Data Products note).

## Pixel scale

- Explanatory Supplement instrument table: **6.15″ × 6.15″**.
- Live SIA `s_pixel_scale` for DR1 Spectral Images covering WISE 0855: **6.150** (arcsec).
- Caltech instrument page (updated Sep 2021) lists **6.2″** — treat 6.15″ as the archive/SIA value for SkyFlip calculations; note the ~0.05″ difference if citing the older instrument page.

## Quality / contamination flags

FLAGS HDU is a bitmask. Bits verified from Explanatory Supplement Table 16 / intro notebook (bit numbering as given):

| Bit | Name | Meaning (short) |
| --- | --- | --- |
| 0 | TRANSIENT | Transient (e.g. cosmic ray) during SUR |
| 1 | OVERFLOW | Overflow / saturation threshold during SUR |
| 2 | SUR_ERROR | Onboard SUR processing error |
| 6 | NONFUNC | Permanently unusable |
| 7 | DICHROIC | Low throughput near dichroic (bands 3/4) |
| 9 | MISSING_DATA | Onboard data lost |
| 10 | HOT | Hot / noisy pixel |
| 11 | COLD | Anomalously low signal |
| 12 | FULLSAMPLE | Full sample history available (informational) |
| 14 | PHANMISS | Phantom correction missing |
| 15 | NONLINEAR | Unreliable nonlinearity correction |
| 17 | PERSIST | Persistent charge |
| 19 | OUTLIER | Detect-Outliers module |
| 21 | SOURCE | Mapped to a known source |
| 22 | GHOST | Ghost from bright source in exposure |
| 23 | GHOST_FPA | Ghost from another detector (notebook) |
| 24 | GHOST_EXT | Ghost from outside FOV |
| 25 | STREAK | Satellite / streak (notebook) |
| 26 | BLOOM | Source blooming |
| 27 | SNOWBALL | Snowball artifact |
| 28 | HALO | Transient halo — not recommended for science |
| 29 | SATELLITE_HALO | Satellite streak halo — not recommended |

Header-level quality also includes fine-astrometry flag `FINAST` and release gates such as `N_TRANSIENTS < 435,000` (Explanatory Supplement). Exact header keyword inventory per file: inspect live headers in adapter tests — do not invent names.

## Live probe: WISE 0855

Challenge-given coordinates (only hardcoded test RA/Dec allowed by prompt):

- RA `08h55m10.831s` → **133.79512917°**
- Dec `-7d14m42.53s` → **-7.24514722°**

Live TAP `spherex.obscore` (D1) returned multiple visits, including epochs near MJD **60801.5** and **60979–60982** (~178 days apart) in collection `spherex_dr1`.

Live TAP cutout URLs for D1 returned IBE paths under `/ibe/data/spherex/dr1/level2/...`. Early and late cutouts downloaded to `tmp/phase0_probe/wise0855_d1_*.fits` (real MEFs, ~3.97 MB each).

SIA `COLLECTION=spherex_qr3` at this position returned **no rows** in our probe; `spherex_dr1` returned many rows. Adapter must search **both** DR1 and QR3 (and optionally deep collections).

## SkyFlip adapter strategy (implementation contract)

1. Discover via TAP (`artifact`+`plane`) primary; fall back / augment with SIA2 collections `spherex_dr1` + `spherex_qr3`.
2. Fetch cutouts only through IBE `?center=&size=` on on-prem URLs.
3. Return IMAGE (+ optional ZODI-subtracted view), FLAGS summary, VARIANCE, WCS, and central wavelength at the target pixel from WCS-WAVE.
4. Prefer matching detector / nearby wavelength when building blink sequences (LVF caveat from discussion #1847 + IRSA spectral WCS docs).
5. Cache on disk; never invent FITS extension names or endpoints.

## Open / unverified items

- `TODO(VERIFY)`: full official challenge Resources list once Space Apps publishes it.
- `TODO(VERIFY)`: whether challenge provides a pre-built dataset for the five test targets (discussion #1847: unconfirmed).
- `TODO(VERIFY)`: SPHEREx point-source depth numbers for Planet X meter (need cited Explanatory Supplement / mission paper section).
- `TODO(VERIFY)`: ADES/MPC export format if we implement candidate export later.

## Phase 2 visibility report (computed 2026-11-14)

Re-precache against IRSA **timed out** (SIA `spherex_dr1` read timeout). Demo frames remain the prior D1 cache. Predicted hops below use cited PMs on those cached epoch spans (not assumed by eye):

See `frontend/public/demo-data/visibility_report.json` for the machine-readable table.

Honesty:
- **WISE 0855** / **Epsilon Indi B** on D1: likely **not detectable** (too cold/red). Live default detector is **D5** (3.83–4.41 µm).
- **Barnard's Star**: Gaia DR3 PM implies a measurable hop over ~1 yr; current 0.05° / 29×29 cache under-samples it — enlarge FOV after IRSA recovers.
- Challenge WISE 0855 coordinates are ~2010 epoch; ~15 yr to SPHEREx ≈ 120″ ≈ 20 px (Luhman 2014).
