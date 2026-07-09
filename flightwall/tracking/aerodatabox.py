"""AeroDataBox provider (via RapidAPI).

Recommended default: you query by flight number and get back scheduled /
estimated / actual times plus status, which is exactly what the wall needs.

Get a key at rapidapi.com (search 'AeroDataBox'). It has a small free tier;
note AeroDataBox moved to credit-based billing in 2026, so if you subscribed
previously you may need to re-subscribe.

Endpoint used:
    GET https://aerodatabox.p.rapidapi.com/flights/number/{flightIata}/{date}
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import requests

from ..models import FlightStatus, Sector

HOST = "aerodatabox.p.rapidapi.com"
BASE = f"https://{HOST}/flights/number"


class AeroDataBoxTracker:
    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout

    def get_status(self, sector: Sector, airline_iata: str,
                   airline_icao: str) -> Optional[FlightStatus]:
        if not self.api_key:
            return None
        flight = sector.flight_iata(airline_iata)
        date = sector.std.date().isoformat()
        url = f"{BASE}/{flight}/{date}"
        headers = {"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": HOST}
        try:
            resp = requests.get(url, headers=headers,
                                params={"withLocation": "true"}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        legs = data if isinstance(data, list) else data.get("flights", [data])
        leg = _pick_leg(legs, sector)
        if not leg:
            return None

        dep, arr = leg.get("departure", {}), leg.get("arrival", {})
        status = FlightStatus(source="aerodatabox", status=str(leg.get("status", "")))
        status.off_block = _ts(dep.get("actualTimeUtc") or dep.get("runwayTimeUtc"))
        status.on_block = _ts(arr.get("actualTimeUtc") or arr.get("runwayTimeUtc"))
        status.eta = _ts(arr.get("predictedTimeUtc") or arr.get("estimatedTimeUtc")
                         or arr.get("scheduledTimeUtc"))
        loc = (leg.get("location") or {})
        status.latitude = loc.get("lat")
        status.longitude = loc.get("lon")
        return status

    def lookup_flight(self, flight_iata: str, date_iso: str) -> Optional[dict]:
        """Look up a flight's route + scheduled times by IATA number and date.

        Returns {dep, arr, std, sta, aircraft} (UTC datetimes) or None.
        Used by the manual 'add a flight' feature.
        """
        if not self.api_key:
            return None
        url = f"{BASE}/{flight_iata}/{date_iso}"
        headers = {"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": HOST}
        try:
            resp = requests.get(url, headers=headers,
                                params={"withAircraftImage": "false",
                                        "withLocation": "false"}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        legs = data if isinstance(data, list) else data.get("flights", [data])
        if not legs:
            return None
        leg = legs[0]
        dep, arr = leg.get("departure", {}), leg.get("arrival", {})
        dep_ap = (dep.get("airport", {}) or {}).get("iata")
        arr_ap = (arr.get("airport", {}) or {}).get("iata")
        std = _ts(dep.get("scheduledTimeUtc") or dep.get("scheduledTime", {}).get("utc")
                  if isinstance(dep.get("scheduledTime"), dict) else dep.get("scheduledTimeUtc"))
        sta = _ts(arr.get("scheduledTimeUtc") or (arr.get("scheduledTime", {}).get("utc")
                  if isinstance(arr.get("scheduledTime"), dict) else arr.get("scheduledTimeUtc")))
        if not (dep_ap and arr_ap and std and sta):
            return None
        return {"dep": dep_ap, "arr": arr_ap, "std": std, "sta": sta,
                "aircraft": (leg.get("aircraft", {}) or {}).get("model")}


def _pick_leg(legs, sector: Sector):
    for leg in legs:
        d = (leg.get("departure", {}).get("airport", {}) or {}).get("iata")
        a = (leg.get("arrival", {}).get("airport", {}) or {}).get("iata")
        if d == sector.dep and a == sector.arr:
            return leg
    return legs[0] if legs else None


def _ts(value) -> Optional[dt.datetime]:
    if not value:
        return None
    txt = str(value).replace(" ", "T").replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(txt)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)
