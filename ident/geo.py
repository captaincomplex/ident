"""Coastline for the map styles (downloaded once on the Pi, then cached offline).

The Pi fetches Natural Earth 1:50m land polygons (falling back to 1:110m), keeps
them lightly simplified, and stores each landmass with its bounding box so the
renderer can cull off-screen shapes cheaply — that keeps a detailed dataset fast
enough to redraw on a Pi Zero. No geo libraries are needed at runtime.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request

_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
SOURCES = [_BASE + "ne_50m_land.geojson", _BASE + "ne_110m_land.geojson"]
SIMPLIFY_TOL = 0.03            # ~3 km; small = more detailed shorelines

_MEM = None
_LOCK = threading.Lock()


def _cache_path() -> str:
    from .config import DATA_DIR
    return os.path.join(DATA_DIR, "coastline.json")


def _simplify(coords, tol=SIMPLIFY_TOL):
    if len(coords) < 4:
        return coords
    out = [coords[0]]
    for p in coords[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    out.append(coords[-1])
    return out


def _ring(coords):
    pl = [[round(x, 3), round(y, 3)] for x, y in _simplify(coords)]
    if len(pl) < 3:
        return None
    xs = [p[0] for p in pl]; ys = [p[1] for p in pl]
    return {"b": [min(xs), min(ys), max(xs), max(ys)], "r": pl}


def _build():
    data = None; last = None
    for url in SOURCES:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.load(r)
            break
        except Exception as e:
            last = e
    if data is None:
        raise last or RuntimeError("no coastline source reachable")
    land = []
    for feat in data.get("features", []):
        g = feat.get("geometry") or {}
        t = g.get("type"); cs = g.get("coordinates")
        polys = [cs] if t == "Polygon" else cs if t == "MultiPolygon" else []
        for poly in polys:
            if poly and poly[0]:
                ring = _ring(poly[0])
                if ring:
                    land.append(ring)
    p = _cache_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"land": land}, open(p, "w"), separators=(",", ":"))
    return land


def get_land():
    """Cached landmasses [{'b':[minlon,minlat,maxlon,maxlat],'r':[[lon,lat],..]}].

    Never downloads; returns [] until prefetch() has populated the cache.
    """
    global _MEM
    if _MEM is not None:
        return _MEM
    p = _cache_path()
    if os.path.exists(p):
        try:
            _MEM = json.load(open(p)).get("land", [])
            return _MEM
        except Exception:
            pass
    return []


def prefetch():
    """Ensure the coastline cache exists; download once if missing (Pi side)."""
    global _MEM
    with _LOCK:
        if _MEM:
            return
        p = _cache_path()
        if os.path.exists(p):
            try:
                _MEM = json.load(open(p)).get("land", [])
                return
            except Exception:
                pass
        try:
            _MEM = _build()
            print(f"[ident] coastline cached: {len(_MEM)} landmasses (50m)")
        except Exception as e:
            print(f"[ident] coastline download failed ({e}); map runs without land")
