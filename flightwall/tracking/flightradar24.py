"""Flightradar24 provider (official FR24 API at fr24api.flightradar24.com).

IMPORTANT: this uses the **Flightradar24 API**, which is a separate, credit-
billed product from the Flightradar24.com consumer subscription. A *Contributor*
plan (what you get for hosting an ADS-B receiver) gives premium app features but
does NOT include API tokens - you create those on the FR24 API portal and pick a
plan (Explorer is the hobby tier; there's a free sandbox for testing).

FR24's strength here is the **live position** (great for the route-map marker and
for detecting that you're airborne). It is position-centric, so unless the live
record carries an ``eta`` we keep the scheduled arrival and let the marker move
along the great circle. For a predicted ETA + actual on/off times by flight
number, AeroDataBox remains the more direct fit; the two can be combined.

Endpoint: GET /api/live/flight-positions/full?flights=<IATA flight, e.g. U28301>
Auth:     Authorization: Bearer <token>,  Accept-Version: v1
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import requests

from ..models import FlightStatus, Sector
from ..timezones import _AIRPORTS
from .base import great_circle_progress

PROD = "https://fr24api.flightradar24.com/api"
SANDBOX = "https://fr24api.flightradar24.com/api/sandbox"


class FlightRadar24Tracker:
    def __init__(self, api_token: str, use_sandbox: bool = False,
                 timeout: float = 10.0):
        self.api_token = api_token
        self.base = SANDBOX if use_sandbox else PROD
        self.timeout = timeout

    def get_status(self, sector: Sector, airline_iata: str,
                   airline_icao: str) -> Optional[FlightStatus]:
        if not self.api_token:
            return None
        flight = sector.flight_iata(airline_iata)           # e.g. U28301
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Accept-Version": "v1",
        }
        try:
            resp = requests.get(f"{self.base}/live/flight-positions/full",
                                params={"flights": flight}, headers=headers,
                                timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        rows = data.get("data", data if isinstance(data, list) else [])
        row = _pick(rows, sector)
        if not row:
            return None

        status = FlightStatus(source="flightradar24", status="enroute")
        status.fr24_id = row.get("fr24_id") or row.get("id")
        status.latitude = row.get("lat")
        status.longitude = row.get("lon")
        status.eta = _ts(row.get("eta"))                    # present on some records
        dep_c = _coords(row.get("orig_iata") or sector.dep)
        arr_c = _coords(row.get("dest_iata") or sector.arr)
        if status.latitude is not None and dep_c and arr_c:
            status.progress_pct = great_circle_progress(
                status.latitude, status.longitude, dep_c, arr_c)
        if status.eta is None:
            status.eta = sector.sta                         # fall back to schedule
        return status


def _pick(rows, sector: Sector):
    for r in rows:
        o = r.get("orig_iata"); d = r.get("dest_iata")
        if (o == sector.dep and d == sector.arr) or not (o and d):
            return r
    return rows[0] if rows else None


def _coords(iata: str):
    info = _AIRPORTS.get((iata or "").upper())
    if info and info.get("lat") is not None:
        return (info["lat"], info["lon"])
    return None


def _ts(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value, dt.timezone.utc)
        txt = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(txt)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None
