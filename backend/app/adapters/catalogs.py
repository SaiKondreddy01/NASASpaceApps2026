"""Catalog adapters (SIMBAD/Sesame, Gaia, JPL). Phase 0: name resolve + pings."""

from __future__ import annotations

from typing import Any, Optional

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.coordinates.name_resolve import NameResolveError
from astropy.time import Time


class CatalogAdapterError(RuntimeError):
    pass


# Verified literature fallback for WISE 0855 when SIMBAD PM query fails.
# Luhman 2014, ApJ 786 L18 / arXiv:1404.6501 Table 1:
#   μα cos δ = −8.06 ± 0.09 ″/yr, μδ = +0.70 ± 0.07 ″/yr
# Challenge coordinates (08h55m10.831s, −7d14m42.53s) match the WISE designation
# epoch (~2010); SPHEREx visits are ~2025 so ~15 yr of motion ≈ 120″ ≈ 20 SPHEREx pixels.
WISE0855_LUHMAN2014 = {
    "pm_ra_cosdec_arcsec_yr": -8.06,
    "pm_dec_arcsec_yr": 0.70,
    "pm_ra_err": 0.09,
    "pm_dec_err": 0.07,
    "ref_epoch": Time(2010.5, format="decimalyear"),
    "citation": "Luhman 2014, ApJ 786 L18 (arXiv:1404.6501) Table 1",
}

# Gaia DR3 4472832130942575872 — values widely published (ESA Gaia / Wikipedia Gaia DR3 table).
# Formal σ not inlined here: see Gaia Archive for the source; UI notes "see Gaia Archive".
BARNARDS_GAIA_DR3 = {
    "pm_ra_cosdec_arcsec_yr": -0.801551,  # −801.551 mas/yr
    "pm_dec_arcsec_yr": 10.362394,  # +10362.394 mas/yr
    "pm_ra_err": None,
    "pm_dec_err": None,
    "ref_epoch": Time(2016.0, format="decimalyear"),
    "citation": (
        "Gaia DR3 source 4472832130942575872 "
        "(pmra=−801.551 mas/yr, pmdec=+10362.394 mas/yr; epoch J2016.0)"
    ),
}


def resolve_name(name: str) -> dict[str, Any]:
    """
    Resolve an object name to ICRS RA/Dec.

    Uses Astropy ``SkyCoord.from_name`` (CDS Sesame → SIMBAD/NED/VizieR).
    Preferred over raw astroquery.Simbad TAP here because the SIMBAD
    capabilities endpoint currently 404s for some astroquery versions.
    """
    try:
        coord = SkyCoord.from_name(name)
    except NameResolveError as exc:
        raise CatalogAdapterError(f"No match for {name!r}: {exc}") from exc
    except Exception as exc:
        raise CatalogAdapterError(f"Name resolve failed for {name!r}: {exc}") from exc

    return {
        "name": name,
        "ra": float(coord.ra.deg),
        "dec": float(coord.dec.deg),
        "catalog": "Sesame/SIMBAD",
        "source": "live",
        "uncertainty_arcsec": None,
        "uncertainty_note": "Sesame/SIMBAD coordinates; no separate uncertainty provided by resolver",
    }


def get_proper_motion(name: str, ra: float, dec: float) -> dict[str, Any]:
    """
    Return pm (arcsec/yr), reference epoch, and citation.
    Tries SIMBAD via astroquery; for WISE 0855 falls back to Luhman 2014 (cited).
    """
    pm_ra = pm_dec = None
    pm_ra_err = pm_dec_err = None
    citation = "none"
    ref_epoch = Time(2000.0, format="decimalyear")
    try:
        from astroquery.simbad import Simbad

        s = Simbad()
        s.add_votable_fields("pmra", "pmdec", "pmra_err", "pmdec_err")
        tab = s.query_object(name)
        if tab is not None and len(tab) > 0:
            row = tab[0]
            for pra, pde, era, ede in (
                ("pmra", "pmdec", "pmra_err", "pmdec_err"),
                ("PMRA", "PMDEC", "PMRA_ERR", "PMDEC_ERR"),
            ):
                if pra in row.colnames and row[pra] is not np.ma.masked:
                    # SIMBAD pmra is usually mas/yr
                    pm_ra = float(row[pra]) / 1000.0
                    pm_dec = float(row[pde]) / 1000.0
                    if era in row.colnames and row[era] is not np.ma.masked:
                        pm_ra_err = float(row[era]) / 1000.0
                        pm_dec_err = float(row[ede]) / 1000.0
                    citation = "SIMBAD proper motion (mas/yr → arcsec/yr)"
                    break
    except Exception:
        pass

    if pm_ra is None and ("0855" in name or "WISE" in name.upper()):
        w = WISE0855_LUHMAN2014
        pm_ra = w["pm_ra_cosdec_arcsec_yr"]
        pm_dec = w["pm_dec_arcsec_yr"]
        pm_ra_err = w["pm_ra_err"]
        pm_dec_err = w["pm_dec_err"]
        ref_epoch = w["ref_epoch"]
        citation = w["citation"]

    if pm_ra is None and "barnard" in name.lower():
        w = BARNARDS_GAIA_DR3
        pm_ra = w["pm_ra_cosdec_arcsec_yr"]
        pm_dec = w["pm_dec_arcsec_yr"]
        pm_ra_err = w["pm_ra_err"]
        pm_dec_err = w["pm_dec_err"]
        ref_epoch = w["ref_epoch"]
        citation = w["citation"]

    if pm_ra is None:
        return {
            "ra": ra,
            "dec": dec,
            "pm_ra_cosdec_arcsec_yr": 0.0,
            "pm_dec_arcsec_yr": 0.0,
            "pm_ra_err": None,
            "pm_dec_err": None,
            "ref_epoch": ref_epoch,
            "citation": "no proper motion available",
            "uncertainty_note": "no uncertainty available",
        }

    return {
        "ra": ra,
        "dec": dec,
        "pm_ra_cosdec_arcsec_yr": float(pm_ra),
        "pm_dec_arcsec_yr": float(pm_dec),
        "pm_ra_err": pm_ra_err,
        "pm_dec_err": pm_dec_err,
        "ref_epoch": ref_epoch,
        "citation": citation,
        "uncertainty_note": (
            f"σ_μα={pm_ra_err}\"/yr, σ_μδ={pm_dec_err}\"/yr"
            if pm_ra_err is not None
            else "no uncertainty available"
        ),
    }


def propagate_position(
    ra: float,
    dec: float,
    pm: dict[str, Any],
    obstime: Time,
) -> tuple[float, float]:
    """Propagate RA/Dec to obstime with SkyCoord.apply_space_motion."""
    ref = pm.get("ref_epoch") or Time(2000.0, format="decimalyear")
    coord = SkyCoord(
        ra=ra * u.deg,
        dec=dec * u.deg,
        pm_ra_cosdec=(pm.get("pm_ra_cosdec_arcsec_yr") or 0.0) * u.arcsec / u.yr,
        pm_dec=(pm.get("pm_dec_arcsec_yr") or 0.0) * u.arcsec / u.yr,
        obstime=ref,
    )
    try:
        moved = coord.apply_space_motion(new_obstime=obstime)
    except Exception:
        # Fallback linear approx
        dt = (obstime - ref).to(u.yr).value
        pra = ra + (pm.get("pm_ra_cosdec_arcsec_yr") or 0.0) * dt / 3600.0 / max(
            np.cos(np.deg2rad(dec)), 0.2
        )
        pdec = dec + (pm.get("pm_dec_arcsec_yr") or 0.0) * dt / 3600.0
        return float(pra), float(pdec)
    return float(moved.ra.deg), float(moved.dec.deg)


def ping_simbad() -> dict[str, Any]:
    try:
        resolve_name("Sirius")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def ping_jpl() -> dict[str, Any]:
    """Phase 0: connectivity probe only (Horizons)."""
    import requests

    try:
        r = requests.get(
            "https://ssd.jpl.nasa.gov/api/horizons.api",
            params={"format": "json", "COMMAND": "'1'", "OBJ_DATA": "'YES'", "MAKE_EPHEM": "'NO'"},
            timeout=30,
        )
        return {"ok": r.status_code == 200, "status_code": r.status_code}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}
