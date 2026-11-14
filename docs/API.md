# SkyFlip API (contract)

See `backend/app/models.py` for the source of truth. Phase 0 implements:

| Method | Path | Status |
| --- | --- | --- |
| GET | `/api/health` | Phase 0 |
| GET | `/api/resolve?name=` | Phase 0 |
| GET | `/api/epochs?ra=&dec=&fov=` | Phase 0 |
| GET | `/api/cutouts?...` | Phase 1 |
| GET | `/api/diff?...` | Phase 1 |
| GET | `/api/movers?...` | Phase 2 |
| GET | `/api/predicted-track?...` | Phase 2 |
| GET | `/api/spectrum?...` | Phase 3 |
| GET | `/api/scoreboard` | Phase 2 |

All responses include `source`: `live` or `cached-demo`.
