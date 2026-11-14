"""API schema smoke tests (TestClient, mocked IRSA where needed)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_schema():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "services" in body
    assert "demo_cache_available" in body
    assert body["pixel_scale_arcsec"] == 6.15
    assert body["source"] in ("live", "cached-demo")


def test_change_scores_cached_demo():
    # WISE 0855 catalog position — must work offline from demo cache / float bins
    r = client.get(
        "/api/change-scores",
        params={
            "ra": 133.79512917,
            "dec": -7.24514722,
            "radius": 1.5,
            "metric": "brightness_snr",
            "reference": "median_others",
            "target": "wise0855",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "cached-demo"
    assert body["banner"] and "cached" in body["banner"].lower()
    assert body["metric"] == "brightness_snr"
    assert len(body["frames"]) >= 2
    for fr in body["frames"]:
        assert fr["status"] in ("ok", "not_computed")
        if fr["status"] == "not_computed":
            assert fr["score"] is None
        else:
            assert fr["score"] is not None
            assert fr["score_err"] is not None or "no uncertainty" in (
                fr.get("status_reason") or ""
            )
        assert "epoch_id" in fr
        assert "mjd" in fr


def test_change_scores_no_500_without_target():
    # Unknown field with no demo nearby — expect 200 from nearest demo or 503 JSON
    r = client.get(
        "/api/change-scores",
        params={"ra": 0.0, "dec": 0.0, "radius": 1.5},
    )
    assert r.status_code in (200, 503)
    body = r.json()
    assert "detail" in body or "frames" in body
    if r.status_code == 503:
        assert body.get("ok") is False
        assert body.get("endpoint") == "/api/change-scores"
