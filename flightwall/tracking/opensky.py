"""OpenSky Network provider (free, no key for low-rate anonymous use).

Position-only and matched by callsign, which is the well-known gotcha: many
airlines (easyJet included) fly alphanumeric callsigns that do NOT equal the
marketed flight number, so matches can be missed. Use this as a free secondary
source for live position/progress; prefer AeroDataBox for ETA and actual times.

OpenSky is rate-limited for anonymous users; supplying account credentials
raises the limits.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import requests

from ..models import FlightStatus, Sector
from ..timezones import _AIRPORTS  # offline coords if available
from .base import great_circle_progress

STATES_URL = "https://opensky-network.org/api/states/all"


class OpenSkyTracker:
    def __init__(self, username: str = "", password: str = "", timeout: float = 12.0):
        self.auth = (username, password) if username else None
        self.timeout = timeout

    def get_status(self, sector: Sector, airline_iata: str,
                   airline_icao: str) -> Optional[FlightStatus]:
        wanted = f"{airline_icao}{sector.flight_no}".upper()
        try:
            resp = requests.get(STATES_URL, auth=self.auth, timeout=self.timeout)
            resp.raise_for_status()
            states = resp.json().get("states") or []
        except Exception:
            return None

        match = None
        for st in states:
            callsign = (st[1] or "").strip().upper()
            if callsign == wanted or callsign.startswith(airline_icao.upper()) \
                    and sector.flight_no in callsign:
                match = st
                break
        if not match:
            return None

        lon, lat = match[5], match[6]
        status = FlightStatus(source="opensky", status="enroute",
                              latitude=lat, longitude=lon)
        dep_c, arr_c = _coords(sector.dep), _coords(sector.arr)
        if lat is not None and dep_c and arr_c:
            status.progress_pct = great_circle_progress(lat, lon, dep_c, arr_c)
            remaining = (sector.sta - dt.datetime.now(dt.timezone.utc))
            if status.progress_pct < 100 and remaining.total_seconds() > 0:
                status.eta = sector.sta   # OpenSky gives no ETA; keep schedule
        return status


def _coords(iata: str):
    info = _AIRPORTS.get((iata or "").upper())
    if info and info.get("lat") is not None:
        return (info["lat"], info["lon"])
    return None
