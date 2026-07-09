"""Optional live commute time via the Google Maps Routes API.

Computes driving time from base (car park) to home, with traffic, departing at
the moment debrief + walk-to-car finishes. Falls back to the manual slider if
no key/coordinates are set or the call fails.

Enable by setting use_maps_commute, google_maps_api_key, and the home/base
coordinates in config. The Routes API is a paid Google Cloud product (it has a
monthly free credit); for a fully free build, leave it off and use the slider.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import requests

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def drive_minutes(api_key: str, origin: tuple, dest: tuple,
                  depart_at: Optional[dt.datetime] = None,
                  timeout: float = 10.0) -> Optional[int]:
    if not api_key or not origin or not dest:
        return None
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0],
                                           "longitude": origin[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest[0],
                                                "longitude": dest[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    if depart_at:
        if depart_at <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1):
            depart_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        body["departureTime"] = depart_at.astimezone(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration",
    }
    try:
        resp = requests.post(ROUTES_URL, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        routes = resp.json().get("routes", [])
        if not routes:
            return None
        secs = int(str(routes[0]["duration"]).rstrip("s"))
        return round(secs / 60)
    except Exception:
        return None


def airport_drive_minutes(api_key: str, from_iata: str, to_iata: str,
                          depart_at=None, timeout: float = 10.0):
    """Driving minutes between two airports (e.g. LHR -> LGW), via address search.

    Used for personal flights that land away from base. Returns int or None.
    """
    if not api_key or not from_iata or not to_iata:
        return None
    body = {
        "origin": {"address": f"{from_iata} Airport"},
        "destination": {"address": f"{to_iata} Airport"},
        "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
    }
    if depart_at:
        now = dt.datetime.now(dt.timezone.utc)
        if depart_at <= now + dt.timedelta(minutes=1):
            depart_at = now + dt.timedelta(minutes=2)
        body["departureTime"] = depart_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key,
               "X-Goog-FieldMask": "routes.duration"}
    try:
        r = requests.post(ROUTES_URL, json=body, headers=headers, timeout=timeout)
        r.raise_for_status()
        secs = int(r.json()["routes"][0]["duration"].rstrip("s"))
        return max(1, round(secs / 60))
    except Exception:
        return None
