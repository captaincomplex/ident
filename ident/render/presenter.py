"""Turn a ViewModel into the concrete lines shown on the wall.

Keeps timezone formatting and wording in one place so the LED renderer, the
console simulator and the web preview are always identical.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from ..models import DutyState, DutyType
from ..state_engine import ViewModel
from ..timezones import hhmm, tz_suffix

# Accent colours per state (hex; renderers map these to LED colours).
ACCENTS = {
    DutyState.IN_FLIGHT: "#39c0ff",
    DutyState.TURNAROUND: "#ffb340",
    DutyState.PRE_FLIGHT: "#ffd000",
    DutyState.BETWEEN_DUTIES: "#7ee787",
    DutyState.POST_DUTY: "#c08cff",
    DutyState.STANDBY: "#ff7b72",
    DutyState.DAY_OFF: "#8b949e",
    DutyState.NO_ROSTER: "#8b949e",
}


@dataclass
class Screen:
    header: str = ""
    line1: str = ""
    line2: str = ""
    line3: str = ""
    accent: str = "#39c0ff"
    progress: Optional[float] = None
    arc: Optional[tuple] = None        # (dep, arr, progress) -> draw a route map
    flags: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)   # structured fields for rich renderers


def present(vm: ViewModel, *, tz_mode: str = "base", flight_prefix: str = "EZY",
           iata: str = "U2", now: Optional[dt.datetime] = None) -> Screen:
    now = now or vm.now
    base = vm.base
    suf = tz_suffix(tz_mode)
    accent = ACCENTS.get(vm.state, "#39c0ff")
    s = Screen(accent=accent)

    def t(when, station=None):
        return hhmm(when, tz_mode, base, station) + suf if when else "--:--"

    def route(sec):
        return f"{flight_prefix}{sec.flight_no} {sec.dep}\u2192{sec.arr}"

    # ---- structured, state-aware data for rich renderers (e-paper) ----
    _act = vm.active_sector or vm.next_sector
    _duty = vm.duty
    _personal = bool(_duty and getattr(_duty, "personal", False))
    _airline = (getattr(_duty, "airline", "") if _duty else "")
    _prefix = _airline if (_personal and _airline) else flight_prefix
    _iata = _airline if (_personal and _airline) else iata
    def _disp(when, station=None):
        return hhmm(when, tz_mode, base, station) + suf if when else ""
    _prog = 0.0
    if vm.state.value == "IN_FLIGHT" and vm.active_sector:
        sec = vm.active_sector
        if sec.live and sec.live.progress_pct is not None:
            _prog = max(0.0, min(1.0, sec.live.progress_pct / 100.0))
        else:
            span = (sec.sta - sec.std).total_seconds()
            _prog = max(0.0, min(1.0, (now - sec.std).total_seconds() / span)) if span > 0 else 0.0
    _data = {
        "state": vm.state.value, "in_flight": vm.state.value == "IN_FLIGHT",
        "header": "", "fid": "", "dep": "", "arr": "", "route": "",
        "dep_time": "", "arr_time": "", "land": "", "home": "",
        "report": _disp(_duty.report) if (_duty and _duty.report) else "",
        "date": _duty.date.strftime("%a %d %b").upper() if _duty else "",
        "prog": _prog, "fr24_url": "", "personal": _personal, "airline": _airline,
        "logo_code": _iata, "flight_no": "",
        "countdown_label": vm.countdown_label, "countdown": _disp(vm.countdown_to),
    }
    if _act:
        # Prefer a direct live-flight link if the FR24 tracker resolved one this poll.
        _live = getattr(_act, "live", None)
        _fr24id = getattr(_live, "fr24_id", None) if _live else None
        _url = (f"https://www.flightradar24.com/{_fr24id}" if _fr24id
                else f"https://www.flightradar24.com/data/flights/{_iata.lower()}{_act.flight_no}")
        _data.update(
            fid=f"{_prefix}{_act.flight_no}", flight_no=_act.flight_no, dep=_act.dep, arr=_act.arr,
            route=f"{_act.dep}-{_act.arr}", dep_time=_disp(_act.std),
            arr_time=_disp(_act.sta, _act.arr), land=_disp(_act.effective_arrival(), _act.arr),
            fr24_url=_url,
        )
    if vm.home and vm.home.home_eta:
        _data["home"] = _disp(vm.home.home_eta)     # no '~' marker on e-paper
    # --- duty timeline (for the 'timeline' style): fractions across report->home ---
    _segs = []; _now_frac = None
    _dt = vm.duty
    if _dt and getattr(_dt, "sectors", None):
        _t0 = _dt.report or _dt.sectors[0].std
        _t1 = (vm.home.home_eta if (vm.home and vm.home.home_eta) else _dt.sectors[-1].sta)
        _span = (_t1 - _t0).total_seconds()
        if _span > 0:
            _fr = lambda x: max(0.0, min(1.0, (x - _t0).total_seconds() / _span))
            for _sec in _dt.sectors:
                _segs.append({"label": f"{_sec.dep}-{_sec.arr}",
                              "a": _fr(_sec.effective_departure()), "b": _fr(_sec.effective_arrival())})
            _now_frac = _fr(now)
    _data["segments"] = _segs
    _data["now_frac"] = _now_frac
    def _dur(target):
        if not target: return ""
        mins = int((target - now).total_seconds() // 60); sign = "-" if mins < 0 else ""; mins = abs(mins)
        hh, mm = divmod(mins, 60); return f"{sign}{hh}h{mm:02d}" if hh else f"{sign}{mm}m"
    _data["report_t"] = _disp(_dt.report) if (_dt and _dt.report) else ""
    _data["eta_dur"] = _dur(vm.countdown_to)
    _nd = getattr(vm, "next_duty", None)
    _data["next_summary"] = _summary_next_flight(vm, flight_prefix, tz_mode, base, suf)
    _data["next_date"] = _nd.date.strftime("%a %d %b").upper() if _nd else ""
    _data["next_report"] = (_disp(_nd.report) if (_nd and _nd.report) else "")
    if _nd and _nd.sectors:
        _data["next_dests"] = "/".join(destinations(_nd, base))
        _data["next_route"] = "  ".join(f"{x.dep}\u2013{x.arr}" for x in _nd.sectors[:4])
        _data["next_sectors"] = len(_nd.sectors)
        _data["next_dep"] = _disp(_nd.sectors[0].std)
    elif _nd:
        _data["next_route"] = _nd.raw_code or ""; _data["next_dep"] = ""; _data["next_dests"] = ""; _data["next_sectors"] = 0
    else:
        _data["next_route"] = ""; _data["next_dep"] = ""; _data["next_dests"] = ""; _data["next_sectors"] = 0
    s.data = _data


    def home_line(label="HOME"):
        if not vm.home or not vm.home.home_eta:
            return ""
        star = "~" if not vm.home.is_live else ""
        return f"{label} {star}{t(vm.home.home_eta)}"

    if vm.state == DutyState.NO_ROSTER:
        s.header, s.line1 = "NO ROSTER", "Upload a roster"
        return s

    if vm.state == DutyState.DAY_OFF:
        s.header, s.line1 = "DAY OFF", "Enjoy it \u2600"
        nxt = _summary_next_flight(vm, flight_prefix, tz_mode, base, suf)
        s.line2 = nxt
        s.data["next_summary"] = nxt
        return s

    if vm.state == DutyState.STANDBY:
        s.header = "STANDBY"
        d = vm.duty
        s.line1 = d.raw_code or "STBY"
        if d and d.standby_start:
            s.line2 = f"{t(d.standby_start)} - {t(d.standby_end)}"
        return s

    if vm.state == DutyState.BETWEEN_DUTIES:
        nxt = vm.next_sector
        if vm.countdown_label == "RPT" and nxt:
            s.header = "NEXT DUTY"
            s.line1 = route(nxt)
            s.line2 = f"RPT {t(vm.duty.report)}  DEP {t(nxt.std, nxt.dep)}"
            if vm.return_sector:
                s.line3 = (f"RTN {flight_prefix}{vm.return_sector.flight_no} "
                           f"{t(vm.return_sector.sta, vm.return_sector.arr)}  "
                           + home_line())
            else:
                s.line3 = home_line()
            s.flags.append(_countdown_flag("RPT", vm.duty.report, now))
            if vm.duty.report_estimated:
                s.flags.append("RPT est")
        else:
            s.header = vm.countdown_label or "NEXT"
            s.line1 = (vm.duty.raw_code or "DUTY") if vm.duty else "DUTY"
            if vm.countdown_to:
                s.line2 = t(vm.countdown_to)
                s.flags.append(_countdown_flag(vm.countdown_label or "IN",
                                               vm.countdown_to, now))
        return s

    if vm.state == DutyState.PRE_FLIGHT:
        sec = vm.active_sector
        s.header = "REPORTED"
        s.line1 = route(sec)
        s.line2 = f"DEP {t(sec.effective_departure(), sec.dep)}"
        s.line3 = home_line()
        s.flags.append(_countdown_flag("DEP", sec.effective_departure(), now))
        return s

    if vm.state == DutyState.IN_FLIGHT:
        sec = vm.active_sector
        s.header = "IN FLIGHT"
        s.line1 = route(sec)
        eta = sec.effective_arrival()
        live = sec.live and sec.live.status
        s.line2 = f"LAND {t(eta, sec.arr)}" + (f"  {sec.live.status.upper()}" if live else "")
        if vm.return_sector:
            s.line3 = (f"RTN {flight_prefix}{vm.return_sector.flight_no} "
                       f"{t(vm.return_sector.std, vm.return_sector.dep)}  " + home_line())
        else:
            s.line3 = home_line()
        s.progress = sec.live.progress_pct if sec.live else _time_progress(sec, now)
        s.arc = (sec.dep, sec.arr, s.progress)
        s.flags.append(_countdown_flag("LAND", eta, now))
        return s

    if vm.state == DutyState.TURNAROUND:
        sec = vm.next_sector
        s.header = "TURNAROUND"
        s.line1 = route(sec)
        s.line2 = f"DEP {t(sec.effective_departure(), sec.dep)}"
        s.line3 = home_line()
        s.flags.append(_countdown_flag("DEP", sec.effective_departure(), now))
        return s

    if vm.state == DutyState.POST_DUTY:
        s.header = "HEADING HOME"
        s.line1 = home_line("HOME")
        if vm.home:
            s.line2 = (f"chx {t(vm.home.on_chocks)}  car {t(vm.home.commute_start)}")
        s.flags.append(_countdown_flag("HOME", vm.home.home_eta if vm.home else None, now))
        return s

    return s


def destinations(duty, base) -> list[str]:
    """Where a duty actually takes you: arrival airports that aren't your base.

    A four-sector day like LGW-NTE-LGW-BOD-LGW gives ["NTE", "BOD"], so the
    board can show both turnarounds rather than only the first one. Duplicates
    are collapsed (a double out-and-back to the same field shows once), and a
    duty that somehow never leaves base falls back to its arrival list.
    """
    if not duty or not duty.sectors:
        return []
    out = []
    for sec in duty.sectors:
        if sec.arr and sec.arr != base and sec.arr not in out:
            out.append(sec.arr)
    if not out:
        for sec in duty.sectors:
            if sec.arr and sec.arr not in out:
                out.append(sec.arr)
    return out


def _summary_next_flight(vm, flight_prefix, tz_mode, base, suf):
    """One-line summary of the next real duty, for the day-off board.

    e.g. "THU 25 JUN 06:10Z NTE/BOD" (flying) or "THU 25 JUN STBY 06:00Z".
    """
    nd = getattr(vm, "next_duty", None)
    if not nd:
        return ""
    date_s = nd.date.strftime("%a %d %b").upper()
    if nd.sectors:
        sec = nd.sectors[0]
        dests = "/".join(destinations(nd, base)) or sec.arr
        return f"{date_s} {hhmm(sec.std, tz_mode, base) + suf} {dests}"
    if nd.duty_type == DutyType.STANDBY and nd.standby_start:
        return f"{date_s} {nd.raw_code or 'STBY'} {hhmm(nd.standby_start, tz_mode, base) + suf}"
    if nd.report:
        return f"{date_s} {nd.raw_code or 'DUTY'} {hhmm(nd.report, tz_mode, base) + suf}"
    return f"{date_s} {nd.raw_code}".strip()


def _time_progress(sec, now) -> Optional[float]:
    dep, arr = sec.effective_departure(), sec.effective_arrival()
    span = (arr - dep).total_seconds()
    if span <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (now - dep).total_seconds() / span))


def _countdown_flag(label, target, now) -> str:
    if not target:
        return ""
    delta = target - now
    mins = int(delta.total_seconds() // 60)
    sign = "-" if mins < 0 else ""
    mins = abs(mins)
    h, m = divmod(mins, 60)
    clock = f"{h}h{m:02d}" if h else f"{m}m"
    return f"{label} in {sign}{clock}"
