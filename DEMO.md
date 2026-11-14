# Demo script (60–90 s)

## Pre-flight

- [ ] `frontend/public/demo-data/` has five targets + `scoreboard.json` + `visibility_report.json`
- [ ] Float `.bin` sidecars present (browser stretch) — optional but preferred
- [ ] `make backend` and `make frontend` (or prove offline: stop backend)
- [ ] Open http://127.0.0.1:5173 — audio unmuted for sonification
- [ ] Optional: DevTools → Offline to prove cached-demo banner
- [ ] Tab pre-warmed; `prefers-reduced-motion` starts paused

## Script (matches the app now)

1. **Hook (~10 s)** — SPHEREx will image about a billion objects. Nobody can blink them all by hand. SkyFlip is a public blink comparator with proof built in — candidates only, never a Planet X discovery claim.
2. **Fixed-sky mover (~25 s)** — Click **Barnard's Star** (or WISE 0855). Leave **fixed sky**. Play the blink (≤3 Hz). Toggle **Ghost track** — marker uses cited PM (Gaia DR3 / Luhman 2014) with `x_pix`/`y_pix`. Say honestly: Barnard's predicted hop on the cached span is ~1.7 px; WISE 0855 on D1 is likely invisible (prefer D5) — see `visibility_report.json`.
2b. **Change slider (~10 s)** — Stay on **WISE 0855**. Open the **Change slider**. Drag the right handle toward the biggest changes (or **Show only biggest N**). Watch the centroid **trail** form on the image (numbered dots, net-motion arrow). Say: this is “differs from reference at this position,” **not** a discovery. Reset restores all frames.
2c. **Report an observation (~15–20 s)** — Click **Report an observation**. Select a few frames → drag a **blue highlight** → flip one frame’s toggle to **custom** and nudge the box → short description + direction → consent → Submit. Show the receipt ID. Say: **community observation, unverified**. Admin: `SKYFLIP_ADMIN_TOKEN=… python pipeline/obs_admin.py list`.
3. **Scoreboard (~15 s)** — Open **Scoreboard**. Show measured recovered/missed/false with method + sample size. Synthetic bins labeled **SIMULATED**. Point at misses.
4. **Spectrum + sonify (~15 s)** — **Load spectrum**. State the **point count** on screen (not “102 bands” unless it is). **Play sonification** — wavelength→pitch, flux→volume; text equivalent below.
5. **Discovery + Planet X (~15 s)** — **Discovery Mode** (keys 1/2/3). **Planet X meter** — motion vs brightness. Close: what we cannot do yet (cold BDs on D1, IRSA timeouts, float archive stretch still maturing).

## Offline proof

Stop the API. Click all five targets (coords from manifests). Scoreboard falls back to `scoreboard.json`. Ghost/movers/spectrum use cached JSON when present. Aladin shows offline badge.

## Manual QA

- [ ] No white screen switching Barnard's → WISE 0855 mid-blink
- [ ] `?demo=1` auto-walks five targets
- [ ] `?embed=1` · URL restores `epoch` + `stretch`
- [ ] Colon coords: `08:55:10.831 -07:14:42.53`
- [ ] Keyboard-only · mobile width · colorblind-safe yellow ghost on dark sky
