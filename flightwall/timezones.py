"""Timezone helpers.

The roster prints everything in *Local Base* time. We localise to the base
timezone and convert to UTC for storage. For display the user can choose:

    * "utc"     - Zulu
    * "base"    - the crew member's home base local time
    * "station" - the local time at the relevant airport for that sector

IATA -> timezone comes from the offline ``airportsdata`` dataset, so no network
is required on the Pi for the conversion itself.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

try:
    import airportsdata
    _AIRPORTS = airportsdata.load("IATA")  # keyed by IATA code
except Exception:                          # pragma: no cover - dataset optional
    _AIRPORTS = {}

# A few manual fall-backs in case the dataset is unavailable.
_FALLBACK_TZ = {
    "LGW": "Europe/London", "LTN": "Europe/London", "STN": "Europe/London",
    "SKG": "Europe/Athens", "MUC": "Europe/Berlin", "CFU": "Europe/Athens",
    "NAP": "Europe/Rome", "LJU": "Europe/Ljubljana", "CPH": "Europe/Copenhagen",
    "MXP": "Europe/Rome", "BER": "Europe/Berlin", "DBV": "Europe/Zagreb",
    "JER": "Europe/Jersey", "SVQ": "Europe/Madrid", "NBE": "Africa/Tunis",
}


@lru_cache(maxsize=512)
def tz_for_airport(iata: str) -> ZoneInfo:
    iata = (iata or "").upper()
    info = _AIRPORTS.get(iata)
    if info and info.get("tz"):
        try:
            return ZoneInfo(info["tz"])
        except Exception:
            pass
    if iata in _FALLBACK_TZ:
        return ZoneInfo(_FALLBACK_TZ[iata])
    return ZoneInfo("UTC")


def base_local_to_utc(naive_local: dt.datetime, base_iata: str) -> dt.datetime:
    """Interpret a naive datetime as local-base time and return UTC."""
    tz = tz_for_airport(base_iata)
    return naive_local.replace(tzinfo=tz).astimezone(dt.timezone.utc)


def for_display(when: dt.datetime, mode: str, base_iata: str,
                station_iata: str | None = None) -> dt.datetime:
    """Convert a UTC datetime into the requested display zone."""
    if when is None:
        return None
    mode = (mode or "base").lower()
    if mode == "utc":
        return when.astimezone(dt.timezone.utc)
    if mode == "station" and station_iata:
        return when.astimezone(tz_for_airport(station_iata))
    return when.astimezone(tz_for_airport(base_iata))


def hhmm(when: dt.datetime, mode: str, base_iata: str,
         station_iata: str | None = None) -> str:
    if when is None:
        return "--:--"
    local = for_display(when, mode, base_iata, station_iata)
    return local.strftime("%H:%M")


def tz_suffix(mode: str) -> str:
    return {"utc": "Z", "station": "L", "base": ""}.get((mode or "base").lower(), "")
