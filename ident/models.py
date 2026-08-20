"""Core roster data model.

Everything time-related is stored as a timezone-aware ``datetime`` in UTC.
Display conversion to UTC / Local Base / Local Station happens at the edges
(see ``timezones.py`` and the renderer), never in this module.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class DutyType(str, Enum):
    FLY = "FLY"
    STANDBY = "STANDBY"          # PSBE / ESBY / airport or home standby
    DAY_OFF = "DAY_OFF"          # D/O
    TRAINING = "TRAINING"        # FTGD, sim, ground school
    OTHER = "OTHER"              # WFTU and anything unrecognised


class DutyState(str, Enum):
    """What the wall should currently be showing."""
    NO_ROSTER = "NO_ROSTER"
    DAY_OFF = "DAY_OFF"
    STANDBY = "STANDBY"
    BETWEEN_DUTIES = "BETWEEN_DUTIES"   # next duty is in the future
    PRE_FLIGHT = "PRE_FLIGHT"           # reported, before first off-blocks
    IN_FLIGHT = "IN_FLIGHT"             # airborne on a sector
    TURNAROUND = "TURNAROUND"           # on ground between sectors, same duty
    POST_DUTY = "POST_DUTY"             # last sector landed, heading home


@dataclass
class FlightStatus:
    """Live data for a sector, supplied by a tracking provider."""
    source: str = ""
    status: str = ""                         # scheduled/enroute/landed/...
    off_block: Optional[dt.datetime] = None  # actual pushback / takeoff (UTC)
    on_block: Optional[dt.datetime] = None   # actual landing / on-chocks (UTC)
    eta: Optional[dt.datetime] = None        # live estimated arrival (UTC)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    progress_pct: Optional[float] = None     # 0..100 along the great circle
    fr24_id: Optional[str] = None            # FR24 live flight id -> direct live link
    fetched_at: Optional[dt.datetime] = None


@dataclass
class Sector:
    flight_no: str                      # bare number as printed, e.g. "8243"
    dep: str                            # departure IATA, e.g. "LGW"
    arr: str                            # arrival IATA, e.g. "SKG"
    std: dt.datetime                    # scheduled time of departure (UTC)
    sta: dt.datetime                    # scheduled time of arrival (UTC)
    aircraft_type: Optional[str] = None  # "320"
    is_actual_times: bool = False        # roster printed actual (A-prefixed) times
    live: Optional[FlightStatus] = None

    def flight_iata(self, airline_iata: str) -> str:
        return f"{airline_iata}{self.flight_no}"

    def flight_icao(self, airline_icao: str) -> str:
        return f"{airline_icao}{self.flight_no}"

    # The best estimate of when this sector is actually on-chocks: live on-block,
    # else live ETA, else the scheduled arrival.
    def effective_arrival(self) -> dt.datetime:
        if self.live:
            if self.live.on_block:
                return self.live.on_block
            if self.live.eta:
                return self.live.eta
        return self.sta

    def effective_departure(self) -> dt.datetime:
        if self.live and self.live.off_block:
            return self.live.off_block
        return self.std


@dataclass
class Duty:
    date: dt.date                        # local-base calendar date of the duty
    duty_type: DutyType
    raw_code: str = ""                   # original roster token (FTGD, PSBE, ...)
    report: Optional[dt.datetime] = None  # report/check-in (UTC); None for D/O
    report_estimated: bool = False        # True if we guessed it (no roster value)
    duty_end: Optional[dt.datetime] = None  # off-duty time (UTC); last on-chocks + debrief
    sectors: list[Sector] = field(default_factory=list)
    standby_start: Optional[dt.datetime] = None
    standby_end: Optional[dt.datetime] = None
    personal: bool = False                # non-work flight added manually
    airline: str = ""                    # IATA code for personal flights (logo/prefix)

    @property
    def is_flying(self) -> bool:
        return self.duty_type == DutyType.FLY and bool(self.sectors)

    @property
    def base(self) -> Optional[str]:
        return self.sectors[0].dep if self.sectors else None

    def last_arrival(self) -> Optional[dt.datetime]:
        return self.sectors[-1].effective_arrival() if self.sectors else None


@dataclass
class Roster:
    crew_id: str = ""
    crew_name: str = ""
    base: str = ""                       # home base IATA, e.g. "LGW"
    duties: list[Duty] = field(default_factory=list)

    def sorted_duties(self) -> list[Duty]:
        return sorted(self.duties, key=lambda d: (d.report or _midnight(d.date)))

    def to_dict(self) -> dict:
        return {
            "crew_id": self.crew_id,
            "crew_name": self.crew_name,
            "base": self.base,
            "duties": [_duty_to_dict(d) for d in self.duties],
        }


def _midnight(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def _duty_to_dict(d: Duty) -> dict:
    out = asdict(d)
    out["date"] = d.date.isoformat()
    out["duty_type"] = d.duty_type.value
    for key in ("report", "duty_end", "standby_start", "standby_end"):
        out[key] = d.__dict__[key].isoformat() if d.__dict__[key] else None
    out["sectors"] = []
    for s in d.sectors:
        sd = {
            "flight_no": s.flight_no, "dep": s.dep, "arr": s.arr,
            "std": s.std.isoformat(), "sta": s.sta.isoformat(),
            "aircraft_type": s.aircraft_type, "is_actual_times": s.is_actual_times,
        }
        out["sectors"].append(sd)
    return out


def roster_from_dict(data: dict) -> Roster:
    r = Roster(crew_id=data.get("crew_id", ""), crew_name=data.get("crew_name", ""),
               base=data.get("base", ""))
    for dd in data.get("duties", []):
        duty = Duty(
            date=dt.date.fromisoformat(dd["date"]),
            duty_type=DutyType(dd["duty_type"]),
            raw_code=dd.get("raw_code", ""),
            report=_iso(dd.get("report")),
            report_estimated=dd.get("report_estimated", False),
            duty_end=_iso(dd.get("duty_end")),
            standby_start=_iso(dd.get("standby_start")),
            standby_end=_iso(dd.get("standby_end")),
            personal=dd.get("personal", False),
            airline=dd.get("airline", ""),
        )
        for sd in dd.get("sectors", []):
            duty.sectors.append(Sector(
                flight_no=sd["flight_no"], dep=sd["dep"], arr=sd["arr"],
                std=_iso(sd["std"]), sta=_iso(sd["sta"]),
                aircraft_type=sd.get("aircraft_type"),
                is_actual_times=sd.get("is_actual_times", False),
            ))
        r.duties.append(duty)
    return r


def _iso(value) -> Optional[dt.datetime]:
    return dt.datetime.fromisoformat(value) if value else None
