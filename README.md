# SkyFlip

**The blink comparator that found Pluto, rebuilt for everyone, with proof built in that it works.**

Backend Built By Aarav Bhandula
Frontend Built By Harrison Chang

Public web tool for NASA Space Apps Challenge 2026 — **Planet X and SPHEREx**. Enter sky coordinates, blink SPHEREx visits, spot movers, hear a spectrum sonification, and check a validation scoreboard.

> **We do not claim to discover Planet X or any new object.** Detections are **candidates**.

## One-command local run

```bash
export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"
make install          # Python 3.12 venv + npm deps
make precache         # real IRSA cutouts → frontend/public/demo-data/
make backend          # terminal A → :8000
make frontend         # terminal B → :5173
```

Open http://127.0.0.1:5173 — try **WISE 0855**. Offline: cached demo data loads automatically when live IRSA fails (banner shown).

Docker backend: `docker compose up --build backend`.

## Architecture

```
frontend (Vite/React)  --API-->  backend (FastAPI)
                                      │
                                      ├─ adapters/spherex.py  (ALL SPHEREx/IRSA I/O)
                                      ├─ adapters/catalogs.py (Sesame/SIMBAD, JPL ping)
                                      ├─ imaging / detect / classify / spectra / validate
                                      └─ on-disk cache + demo-data fallback
```

## Official test targets

Barnard's Star · Epsilon Indi B · WISE 0855 (RA 08h55m10.831s, Dec −7d14m42.53s) · RW Aurigae · R Draconis

## Docs

- [`docs/DATA_NOTES.md`](docs/DATA_NOTES.md) — verified IRSA access
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — scoreboard methodology
- [`docs/SCIENCE_LIMITS.md`](docs/SCIENCE_LIMITS.md) — limits & citations
- [`docs/PRIVACY_AND_DATA.md`](docs/PRIVACY_AND_DATA.md) — community observation privacy
- [`.env.example`](.env.example) — secrets via environment only (never commit `.env`)
- [`DEMO.md`](DEMO.md) — 60–90 s demo script
- [`ATTRIBUTION.md`](ATTRIBUTION.md) — NASA/JPL/IPAC credits

## Community observations

Users can file structured **unverified** reports (frames + sky highlights + ≤300 words) via **Report an observation**.

- Storage: **SQLite + local disk** behind `StorageBackend` (Supabase later as a config swap).
- Admin: token-only (`SKYFLIP_ADMIN_TOKEN`); CLI `python pipeline/obs_admin.py list|export|aggregate`.
- Privacy: [`docs/PRIVACY_AND_DATA.md`](docs/PRIVACY_AND_DATA.md). Secrets: [`.env.example`](.env.example).

## Honest limits

Coarse 6.15″ pixels; LVF wavelength varies across the detector; Level-2 IMAGE is MJy/sr without ZODI subtraction; brightness—not motion—is the hard part for distant planets.

## License

MIT
