"""Parse an eCrew 'Personal Crew Schedule Report' PDF into a Roster.

This is the *manual upload* ingestion path. The report lays each day out as a
fixed-x column. Within a column the rows always appear top-to-bottom as:

    report-time-or-duty-code
    [ standby-window-start, standby-window-end ]      (standby days)
    < per sector:  flight-no, dep-time, dep-apt, arr-apt, arr-time, [type] >
    [ duty-end-time ]

All printed times are Local Base (per the report header). We localise to the
base timezone and store UTC.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import pdfplumber

from ..models import Duty, DutyType, Roster, Sector
from ..timezones import base_local_to_utc

ZWSP = "\u200b"

_RE_TIME = re.compile(r"^([AE])?(\d{2}):(\d{2})$")
_RE_FLIGHT = re.compile(r"^\d{2,4}$")
_RE_APT = re.compile(r"^[A-Z]{3}$")
_RE_ACTYPE = re.compile(r"^\[\d{2,4}\]$")
_RE_DATE = re.compile(r"^(\d{2})/(\d{2})$")
_RE_DATE_FULL = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_RE_CREWLINE = re.compile(r"^([A-Z]{3})-([A-Z]{2,3})-(\d{2,4})$")

_CODE_MAP = {
    "D/O": DutyType.DAY_OFF, "DO": DutyType.DAY_OFF, "OFF": DutyType.DAY_OFF,
    "PSBE": DutyType.STANDBY, "ESBY": DutyType.STANDBY, "LSBY": DutyType.STANDBY,
    "ASBY": DutyType.STANDBY, "HSBY": DutyType.STANDBY, "STBY": DutyType.STANDBY,
    "FTGD": DutyType.TRAINING, "SIM": DutyType.TRAINING, "GS": DutyType.TRAINING,
}

GRID_TOP, GRID_BOTTOM = 118, 296   # vertical window holding the duty grid


def parse_pdf(path: str, debrief_minutes: int = 30) -> Roster:
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

    words = [{"t": w["text"].replace(ZWSP, "").strip(),
              "x": (w["x0"] + w["x1"]) / 2, "top": w["top"]} for w in words]
    words = [w for w in words if w["t"]]

    year = _find_year(words)
    crew_id, crew_name, base = _find_header(words)

    # Column anchors come from the date header row (top ~103).
    date_words = sorted(
        (w for w in words if _RE_DATE.match(w["t"]) and 95 <= w["top"] <= 110),
        key=lambda w: w["x"])
    if not date_words:
        raise ValueError("Could not find the date header row in the PDF.")

    centers = [w["x"] for w in date_words]
    col_dates = [_to_date(w["t"], year) for w in date_words]
    step = _median_step(centers)

    # Assign grid words to the nearest column.
    columns: list[list[dict]] = [[] for _ in centers]
    for w in words:
        if not (GRID_TOP <= w["top"] <= GRID_BOTTOM):
            continue
        idx = min(range(len(centers)), key=lambda i: abs(centers[i] - w["x"]))
        if abs(centers[idx] - w["x"]) <= step * 0.8:
            columns[idx].append(w)

    roster = Roster(crew_id=crew_id, crew_name=crew_name, base=base)
    for date, col in zip(col_dates, columns):
        duty = _parse_column(col, date, base, debrief_minutes)
        if duty:
            roster.duties.append(duty)
    return roster


def _parse_column(col: list[dict], date: dt.date, base: str,
                  debrief_minutes: int) -> Optional[Duty]:
    toks = [w["t"] for w in sorted(col, key=lambda w: w["top"])]
    if not toks:
        return None

    head = toks[0]
    rest = toks[1:]

    # Non-flying duty codes.
    code = head.upper()
    if code in _CODE_MAP:
        duty = Duty(date=date, duty_type=_CODE_MAP[code], raw_code=head)
        times = [t for t in rest if _RE_TIME.match(t)]
        if duty.duty_type == DutyType.STANDBY and len(times) >= 2:
            anchor = base_local_to_utc(_dt_on(date, times[0]), base)
            duty.standby_start = anchor
            duty.standby_end = _seq_after(date, times[1], anchor, base)
        return duty

    # Flying duty: head should be the report time.
    m = _RE_TIME.match(head)
    if not m:
        # Unknown single token (e.g. a code we don't map yet) -> OTHER.
        return Duty(date=date, duty_type=DutyType.OTHER, raw_code=head)

    duty = Duty(date=date, duty_type=DutyType.FLY)
    prev = base_local_to_utc(_dt_on(date, head), base)
    duty.report = prev

    # Walk tokens, building sectors. A flight number opens a sector; the next
    # TIME/APT/APT/TIME fill it in order. Times stay monotonically increasing so
    # that a sector crossing midnight rolls onto the next day.
    sectors: list[Sector] = []
    i = 0
    saw_delay = False
    while i < len(rest):
        t = rest[i]
        if t.lower() == "delay":
            saw_delay = True
            i += 1
            continue
        if _RE_FLIGHT.match(t):
            sec, prev, consumed = _read_sector(rest, i, date, base, prev)
            if sec:
                sectors.append(sec)
                i += consumed
                continue
        if _RE_TIME.match(t):
            # A lone time after the sectors. Skip the delay-duration value;
            # otherwise treat it as the printed duty-end time.
            if saw_delay:
                saw_delay = False
            elif sectors and duty.duty_end is None:
                duty.duty_end = _seq_after(date, t, prev, base)
            i += 1
            continue
        i += 1

    duty.sectors = sectors

    # Authoritative duty-end for the home calc: last on-chocks + debrief.
    if sectors:
        computed_end = sectors[-1].sta + dt.timedelta(minutes=debrief_minutes)
        if duty.duty_end is None or duty.duty_end < sectors[-1].sta:
            duty.duty_end = computed_end

    return duty if sectors else Duty(date=date, duty_type=DutyType.OTHER,
                                     raw_code=head, report=duty.report)


def _read_sector(toks: list[str], start: int, date: dt.date, base: str,
                 prev: dt.datetime):
    """Read flight-no, dep-time, dep-apt, arr-apt, arr-time from toks[start:]."""
    flight_no = toks[start]
    dep_time = arr_time = None
    dep_apt = arr_apt = None
    actype = None
    j = start + 1
    while j < len(toks):
        t = toks[j]
        if _RE_FLIGHT.match(t):           # next sector begins
            break
        if _RE_TIME.match(t):
            if dep_time is None:
                dep_time = t
            elif arr_time is None:
                arr_time = t
            else:
                break                      # this time belongs to duty-end
        elif _RE_APT.match(t):
            if dep_apt is None:
                dep_apt = t
            elif arr_apt is None:
                arr_apt = t
        elif _RE_ACTYPE.match(t):
            actype = t.strip("[]")
        elif t.lower() == "delay":
            break
        j += 1
        if dep_time and arr_time and dep_apt and arr_apt:
            # allow trailing actype to be consumed
            if j < len(toks) and _RE_ACTYPE.match(toks[j]):
                actype = toks[j].strip("[]")
                j += 1
            break

    if not (dep_time and arr_time and dep_apt and arr_apt):
        return None, prev, 1

    std = _seq_after(date, dep_time, prev, base)
    sta = _seq_after(date, arr_time, std, base)
    actual = bool(_RE_TIME.match(dep_time).group(1) or
                  _RE_TIME.match(arr_time).group(1))
    sec = Sector(flight_no=flight_no, dep=dep_apt, arr=arr_apt, std=std, sta=sta,
                 aircraft_type=actype, is_actual_times=actual)
    return sec, sta, (j - start)


# --- small datetime helpers --------------------------------------------------

def _dt_on(date: dt.date, time_token: str) -> dt.datetime:
    m = _RE_TIME.match(time_token)
    return dt.datetime(date.year, date.month, date.day, int(m.group(2)), int(m.group(3)))


def _seq_after(date: dt.date, time_token: str, not_before: dt.datetime,
               base: str) -> dt.datetime:
    """UTC datetime for time_token on `date`, rolled forward past `not_before`."""
    naive = _dt_on(date, time_token)
    utc = base_local_to_utc(naive, base)
    while not_before is not None and utc < not_before:
        naive += dt.timedelta(days=1)
        utc = base_local_to_utc(naive, base)
    return utc


def _to_date(ddmm: str, year: int) -> dt.date:
    m = _RE_DATE.match(ddmm)
    return dt.date(year, int(m.group(2)), int(m.group(1)))


def _median_step(xs: list[float]) -> float:
    diffs = sorted(b - a for a, b in zip(xs, xs[1:])) or [26.0]
    return diffs[len(diffs) // 2]


def _find_year(words: list[dict]) -> int:
    for w in sorted(words, key=lambda w: w["top"]):
        m = _RE_DATE_FULL.match(w["t"])
        if m:
            return int(m.group(3))
    return dt.date.today().year


def _find_header(words: list[dict]):
    """Crew line looks like:  861234  WYTHE  STEVEN  LGW-CP-319 (one text row)."""
    crew_id, crew_name, base = "", "", ""
    id_word = next((w for w in words
                    if w["top"] < 100 and re.fullmatch(r"\d{5,7}", w["t"])), None)
    if not id_word:
        return crew_id, crew_name, base
    crew_id = id_word["t"]
    row = [w for w in words if abs(w["top"] - id_word["top"]) <= 3
           and w["x"] > id_word["x"]]
    row.sort(key=lambda w: w["x"])
    for w in row:
        m = _RE_CREWLINE.match(w["t"])
        if m:
            base = m.group(1)
            break
    names = [w["t"] for w in row
             if re.fullmatch(r"[A-Z][A-Za-z'\-]+", w["t"]) and not _RE_CREWLINE.match(w["t"])]
    crew_name = " ".join(names[:3])
    return crew_id, crew_name, base
