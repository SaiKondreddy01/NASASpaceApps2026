# Science limits and citations

## Pixel scale

- SPHEREx Spectral Image native scale: **6.15 arcsec/pixel** (Explanatory Supplement; live SIA `s_pixel_scale`).
- Older instrument page value 6.2″ is ~consistent; SkyFlip uses 6.15″.

## Level-2 IMAGE

- Units: MJy/sr.
- Zodiacal light is **not** subtracted from IMAGE (see ZODI extension).

## LVF / wavelength

- Wavelength varies across each detector. Blinking mismatched wavelengths can mimic variability.
- Prefer same detector / nearby λ when comparing epochs.

## Absorption band markers (spectrum panel)

Approximate published IR band regions used **for annotation only** (not object classification):

| Feature | Approx. µm | Notes |
| --- | --- | --- |
| H₂O | 2.7–3.5 | Broad ice/gas features in near-IR |
| CO₂ | 4.1–4.4 | Common CO₂ ice/gas region |
| CO | 4.5–4.8 | CO fundamental region |

These are standard laboratory/astronomical IR band locations for educational overlays. SkyFlip does **not** infer chemistry or object type from a cutout spectrum.

## Planet X meter

- Parallax semi-amplitude ≈ 206265″ / d(AU).
- Six-month max shift up to ~2× that (geometry-dependent).
- Reflected light ∝ R² A / d⁴ — illustrative.
- SPHEREx point-source depth: cite Explanatory Supplement / mission docs before quoting a magnitude limit (`TODO(VERIFY)` exact QR depth number for UI comparison).

## Proper motion for WISE 0855

**Verified citation (not invented):** Luhman (2014), ApJ 786 L18 / [arXiv:1404.6501](https://arxiv.org/abs/1404.6501) Table 1:

| Quantity | Value |
| --- | --- |
| μ_α cos δ | −8.06 ± 0.09 ″/yr |
| μ_δ | +0.70 ± 0.07 ″/yr |
| π | 0.454 ± 0.045 ″ |

Challenge coordinates `08h55m10.831s, −7d14m42.53s` match the WISE designation epoch (~2010). SPHEREx DR1/QR3 visits are ~2025, so ~15 yr of motion ≈ **120″ ≈ 20 SPHEREx pixels** at 6.15″/pix. A 0.05° (180″) fixed-sky cutout centered on the 2010 position can place the object near/off the edge; SkyFlip defaults to **fixed_sky** with **FOV ≥ 0.2°** so the hop is visible, plus a **track_target** mode that recenters each epoch on the PM-propagated position via `SkyCoord.apply_space_motion`.

SkyFlip uses the Luhman 2014 values when SIMBAD PM is unavailable, always showing the citation and uncertainties.

## Proper motion for Barnard's Star

**Verified citation:** Gaia DR3 source `4472832130942575872` — μ_α* = −801.551 mas/yr, μ_δ = +10362.394 mas/yr, epoch J2016.0 (ESA Gaia / Gaia Archive; also tabulated on Wikipedia from DR3). Formal component uncertainties: see Gaia Archive (not inlined here → UI says see Gaia Archive when σ absent).

## Detector defaults for demo targets

Band ranges from SPHEREx Data Products / Explanatory Supplement (`docs/DATA_NOTES.md`):

| Detector | λ (µm) | Default for |
| --- | --- | --- |
| D1 | 0.75–1.09 | Barnard's Star, RW Aur, R Dra |
| D5 | 3.83–4.41 | WISE 0855, Epsilon Indi B (cold / red) |
| D6 | 4.42–5.00 | alternate for cold brown dwarfs |

WISE 0855 peaks near Spitzer [4.5]; it is **likely invisible** on D1. Prefer D5/D6 and state honestly if still undetected.

## Change score (Change Slider)

**Language:** A high score means “this frame differs from the reference at this position,” **not** “a new object” or a discovery. UI and API treat hits as **candidates only**.

### Aperture

- Default radius ≈ **1.5 SPHEREx pixels** (~9.2″ at 6.15″/pix) — within the stated 1–2 pixel guidance.
- Local annulus background: inner/outer ≈ 2.5 / 4.0 pixels (median residual).
- Bad FLAGS bits (transient, overflow, ghost, halo, …) and non-finite pixels are masked; informational bits `SOURCE` / `FULLSAMPLE` are kept. The API reports `n_masked` / `masked_fraction`.

### Reference (selectable)

| Mode | Definition |
| --- | --- |
| `median_others` (default) | Nan-median of **wavelength-matched** peer frames on the common WCS grid (±0.15 µm default). If no peers within tolerance, falls back to all other epochs and sets `wavelength_mismatched=True`. |
| `first_epoch` | Frame 0 image. |
| `previous_epoch` | Prior frame in time order (self for epoch 0). |

LVF wavelength variation across a detector can mimic variability; **prefer λ-matched peers**. Mismatched scores are flagged, never silently treated as pure temporal change.

### Brightness change (S/N)

\[
\mathrm{SNR} = \frac{\sum_{\mathrm{ap}} (I - R - B_{\mathrm{ann}})}{\sqrt{\sum_{\mathrm{ap}} 2\,\sigma^2}}
\]

- \(I\): frame IMAGE; \(R\): reference; \(B_{\mathrm{ann}}\): median residual in the annulus.
- \(\sigma^2\): VARIANCE extension. Factor 2 approximates variance of (frame − median stack) when per-peer variances are not co-added. If VARIANCE is missing, annulus scatter is used and the note says so — **never invent a number**.
- Score uncertainty reported as ≈ 1 (Gaussian S/N scale) when variance-based; UI always shows uncertainty or “no uncertainty available”.
- If the aperture is empty / all masked / non-positive σ → `status=not_computed`, `score=null`.

### Position shift

- Flux-weighted centroid in the aperture vs reference centroid.
- Reported in **pixels** and **arcsec** (`× 6.15″`), with centroid σ propagated.
- Metric `position_shift` displays arcsec offset; `combined` uses \(\mathrm{hypot}(|\mathrm{SNR}_{\mathrm{bright}}|, |\mathrm{shift}/\sigma_{\mathrm{shift}}|)\).

### Apparent motion from trail

- Needs **≥ 3** frames with centroids; otherwise: “too few points to estimate motion”.
- Total displacement and rate (″ and ″/yr) from first→last epoch using **real MJDs**, with endpoint centroid uncertainties.

## Community observation reports

- A user report is an **unverified community observation**, not a detection and not a discovery.
- Reported “up/left” directions depend on **display orientation**; always store north/east from WCS and prefer sky-based position angle for science use.
- LVF **wavelength mismatch** between frames can look like brightness change — reports should note detector/λ; do not treat λ-mismatched blinks as pure motion.
