"""Parse an iCal feed (AIMS eCrew export, surfaced via Google Calendar) -> Roster.

Format learned from a real AIMS eCrew event:

    SUMMARY:     8301 LGW-MXP
    DTSTART/END: 05:40 - 08:55          (report time -> arrival; NOT the STD)
    LOCATION:    (0555Z-0755Z) LGW      (block time in UTC, + departure station)
    DESCRIPTION: Reporting time : 0540
                 8301  - LGW  (0655) - MXP  (0855)
                 * All times in Local Base (LGW)

The DESCRIPTION is authoritative for sector times (Local Base), so we parse it
rather than trusting DTSTART (which is padded to the reporting time on the first
sector). LOCATION's Zulu times are kept as a cross-check / fallback. Each VEVENT
is one sector; sectors are grouped into duties by time gap, and the duty's
report comes from the 'Reporting time' line.

Non-flying events (standby / day off / training) are classified by keyword; the
exact wording AIMS uses for those is the one remaining unknown, so the keyword
lists below are easy to extend.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from ..models import Duty, DutyType, Roster, Sector
from ..timezones import base_local_to_utc

_RE_FLIGHT_LINE = re.compile(
    r"(\d{2,4})\s*-\s*([A-Z]{3})\s*\((\d{3,4})\)\s*-\s*([A-Z]{3})\s*\((\d{3,4})\)")
_RE_REPORT = re.compile(r"report(?:ing)?\s*time\s*:?\s*(\d{3,4})", re.I)
_RE_BASE = re.compile(r"local base\s*\(([A-Z]{3})\)", re.I)
_RE_TITLE = re.compile(r"^\s*(\d{2,4})\s+([A-Z]{3})\s*[-/>\u2192]\s*([A-Z]{3})")
_RE_LOC_Z = re.compile(r"\((\d{3,4})Z\s*-\s*(\d{3,4})Z\)\s*([A-Z]{3})?", re.I)
_RE_ROUTE = re.compile(r"\b([A-Z]{3})\s*[-/>\u2192]+\s*([A-Z]{3})\b")

_KW_STANDBY = ("standby", "stand by", "sby", "esby", "psbe", "lsby", "asby",
               "hsby", "reserve", "airport standby", "home standby")
_KW_OFF = ("day off", "day-off", "d/o", "rest day", "off duty", "annual leave",
           "leave")
_KW_TRAINING = ("training", "sim", "ground school", "recurrent", "ftgd", "ojt",
                "ground duty")


def parse_ical(ics_text, base_iata: str = "", duty_gap_hours: float = 5.0,
               report_lead_min: int = 60, debrief_minutes: int = 30,
               debug: bool = False) -> Roster:
    from icalendar import Calendar
    cal = Calendar.from_ical(ics_text)

    sector_items: list[tuple[Sector, Optional[dt.datetime]]] = []
    other_duties: list[Duty] = []
    discovered_base = base_iata
    raw = []

    for comp in cal.walk("VEVENT"):
        summary = str(comp.get("summary", "")).strip()
        desc = str(comp.get("description", "")).strip()
        location = str(comp.get("location", "")).strip()
        start = _to_utc(comp.get("dtstart"))
        end = _to_utc(comp.get("dtend")) or start
        raw.append({"summary": summary, "description": desc, "location": location,
                    "start": start, "end": end})

        bm = _RE_BASE.search(desc)
        if bm and not discovered_base:
            discovered_base = bm.group(1).upper()
        base = (bm.group(1).upper() if bm else discovered_base) or base_iata

        kind, payload = parse_event(summary, desc, location, start, end, base)
        if kind == "flight":
            sectors, report = payload
            for s in sectors:
                sector_items.append((s, report))
        elif kind == "standby":
            s_start, s_end, label = payload
            other_duties.append(Duty(date=(s_start or start).date(),
                                     duty_type=DutyType.STANDBY, raw_code=label,
                                     standby_start=s_start, standby_end=s_end))
        elif kind in ("off", "training"):
            date, label = payload
            typ = DutyType.DAY_OFF if kind == "off" else DutyType.TRAINING
            other_duties.append(Duty(date=date, duty_type=typ, raw_code=label))

    roster = Roster(base=discovered_base or base_iata)
    roster.duties.extend(_group(sector_items, duty_gap_hours, report_lead_min,
                                debrief_minutes))
    roster.duties.extend(other_duties)
    if debug:
        roster.__dict__["raw_events"] = raw
    return roster


def parse_event(summary, description, location, start, end, base):
    """Pure field parser for one VEVENT. Returns (kind, payload).

    kind is one of: 'flight' -> ([Sector...], report_dt|None)
                    'standby' -> (start, end, label)
                    'off'/'training' -> (date, label)
                    'skip' -> None
    """
    text = " ".join([summary, location, description])
    low = text.lower()

    flight_lines = _RE_FLIGHT_LINE.findall(description)
    title = _RE_TITLE.match(summary)

    if flight_lines or title:
        anchor = (start or end or dt.datetime.now(dt.timezone.utc))
        # Date in base-local terms so the local HHMM attach to the right day.
        local_date = base_local_to_utc(
            dt.datetime(anchor.year, anchor.month, anchor.day), base
        ).date() if False else anchor.astimezone(_base_tz(base)).date()

        rep_m = _RE_REPORT.search(description)
        report = _mk(local_date, rep_m.group(1), base) if rep_m else None

        sectors: list[Sector] = []
        prev = report
        if flight_lines:
            for no, dep, dep_t, arr, arr_t in flight_lines:
                std = _seq(local_date, dep_t, prev, base)
                sta = _seq(local_date, arr_t, std, base)
                sectors.append(Sector(flight_no=no, dep=dep, arr=arr, std=std, sta=sta))
                prev = sta
        else:
            # Fallback: route from title, times from LOCATION Zulu or DTSTART/END.
            no, dep, arr = title.group(1), title.group(2), title.group(3)
            zz = _RE_LOC_Z.search(location)
            if zz:
                std = _mk_z(local_date, zz.group(1))
                sta = _mk_z(local_date, zz.group(2))
                if sta < std:
                    sta += dt.timedelta(days=1)
            else:
                std, sta = start, end
            sectors.append(Sector(flight_no=no, dep=dep, arr=arr, std=std, sta=sta))
        return "flight", (sectors, report)

    if any(k in low for k in _KW_STANDBY):
        return "standby", (start, end, summary or "STBY")
    if any(k in low for k in _KW_OFF):
        return "off", ((start or end).date(), summary or "D/O")
    if any(k in low for k in _KW_TRAINING):
        return "training", ((start or end).date(), summary or "TRAINING")
    # Last-ditch: a bare route in the summary.
    if _RE_ROUTE.search(summary):
        r = _RE_ROUTE.search(summary)
        return "flight", ([Sector(flight_no="----", dep=r.group(1), arr=r.group(2),
                                  std=start, sta=end)], None)
    return "skip", None


def _group(items, gap_hours, report_lead, debrief):
    items = sorted(items, key=lambda it: it[0].std)
    duties: list[Duty] = []
    cur: list[tuple] = []
    gap = dt.timedelta(hours=gap_hours)

    def close(group):
        secs = [it[0] for it in group]
        reports = [it[1] for it in group if it[1]]
        rep = min(reports) if reports else None
        estimated = rep is None
        if estimated:
            rep = secs[0].std - dt.timedelta(minutes=report_lead)
        return Duty(date=secs[0].std.astimezone(dt.timezone.utc).date(),
                    duty_type=DutyType.FLY, report=rep, report_estimated=estimated,
                    duty_end=secs[-1].sta + dt.timedelta(minutes=debrief),
                    sectors=secs)

    for it in items:
        if cur and it[0].std - cur[-1][0].sta > gap:
            duties.append(close(cur))
            cur = []
        cur.append(it)
    if cur:
        duties.append(close(cur))
    return duties


# --- time helpers ------------------------------------------------------------

def _base_tz(base):
    from ..timezones import tz_for_airport
    return tz_for_airport(base)


def _pad(t: str) -> tuple[int, int]:
    t = t.zfill(4)
    return int(t[:2]), int(t[2:])


def _mk(date, hhmm, base) -> dt.datetime:
    h, m = _pad(hhmm)
    return base_local_to_utc(dt.datetime(date.year, date.month, date.day, h, m), base)


def _mk_z(date, hhmm) -> dt.datetime:
    h, m = _pad(hhmm)
    return dt.datetime(date.year, date.month, date.day, h, m, tzinfo=dt.timezone.utc)


def _seq(date, hhmm, not_before, base) -> dt.datetime:
    h, m = _pad(hhmm)
    naive = dt.datetime(date.year, date.month, date.day, h, m)
    utc = base_local_to_utc(naive, base)
    while not_before is not None and utc < not_before:
        naive += dt.timedelta(days=1)
        utc = base_local_to_utc(naive, base)
    return utc


def _to_utc(prop) -> Optional[dt.datetime]:
    if prop is None:
        return None
    value = getattr(prop, "dt", prop)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=dt.timezone.utc)
    return None
