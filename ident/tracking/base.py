"""Live flight tracking provider interface.

Providers translate a roster sector into a ``FlightStatus`` (actual off/on
times, ETA, position, progress). Two implementations are included:

    * AeroDataBox  - query by flight number, returns ETA + actual times (best fit)
    * OpenSky      - free ADS-B positions by callsign (best-effort, position only)

Tracking is only polled while the state engine says you are airborne, so even a
free / low-quota provider is comfortably enough for a personal roster.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional, Protocol

from ..models import FlightStatus, Roster, Sector


class FlightTracker(Protocol):
    def get_status(self, sector: Sector, airline_iata: str,
                   airline_icao: str) -> Optional[FlightStatus]:
        ...


class NullTracker:
    """Used when no provider is configured; the wall falls back to schedule."""
    def get_status(self, sector, airline_iata, airline_icao):
        return None


def update_active_sector(roster: Roster, tracker: FlightTracker,
                         airline_iata: str, airline_icao: str,
                         now: dt.datetime) -> Optional[Sector]:
    """Find the sector that should be airborne now and refresh its live data."""
    for duty in roster.duties:
        for s in duty.sectors:
            window_start = (s.live.off_block if s.live and s.live.off_block else s.std)
            window_end = s.sta + dt.timedelta(hours=2)   # generous tail for delays
            if window_start - dt.timedelta(minutes=20) <= now <= window_end:
                status = tracker.get_status(s, airline_iata, airline_icao)
                if status:
                    status.fetched_at = now
                    s.live = status
                    return s
    return None


def great_circle_progress(lat: float, lon: float, dep: tuple, arr: tuple) -> float:
    """Rough 0..100 progress from current position between dep and arr coords."""
    import math

    def hav(a, b):
        la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
        d = (math.sin((la2 - la1) / 2) ** 2
             + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
        return 2 * math.asin(min(1.0, math.sqrt(d)))

    total = hav(dep, arr)
    if total == 0:
        return 0.0
    done = hav(dep, (lat, lon))
    return max(0.0, min(100.0, 100.0 * done / total))
