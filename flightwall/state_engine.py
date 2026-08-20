"""Decide what the wall should show right now, and when you'll get home.

Home-time chain (your spec):

    on-chocks (last sector arrival)
      + 30 min debrief
      + walk-to-car-park   (slider)
      + commute            (slider, or live Google Maps drive time)
      = home

While airborne we prefer live data (actual off-blocks / ETA) over the roster's
scheduled times, so the estimate sharpens as the duty progresses.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from .models import Duty, DutyState, DutyType, Roster, Sector


@dataclass
class HomeEstimate:
    on_chocks: Optional[dt.datetime] = None
    debrief_end: Optional[dt.datetime] = None
    commute_start: Optional[dt.datetime] = None   # after walk to car park
    home_eta: Optional[dt.datetime] = None
    is_live: bool = False                          # built on live ETA vs schedule


@dataclass
class ViewModel:
    """Everything the renderer needs, timezone-agnostic (UTC datetimes)."""
    state: DutyState
    now: dt.datetime
    base: str = ""
    duty: Optional[Duty] = None
    active_sector: Optional[Sector] = None
    return_sector: Optional[Sector] = None         # other sector(s) same duty
    next_sector: Optional[Sector] = None           # for turnaround
    next_duty: Optional[Duty] = None               # soonest real duty (day-off board)
    home: Optional[HomeEstimate] = None
    countdown_to: Optional[dt.datetime] = None      # report / STD to count down to
    countdown_label: str = ""
    messages: list[str] = field(default_factory=list)


def compute_view(roster: Roster, now: dt.datetime, *, debrief_minutes: int = 30,
                 walk_minutes: int = 0, commute_minutes: int = 0,
                 live_commute_minutes: Optional[int] = None,
                 transfer_minutes: int = 0) -> ViewModel:
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    commute = live_commute_minutes if live_commute_minutes is not None else commute_minutes

    if not roster.duties:
        return ViewModel(state=DutyState.NO_ROSTER, now=now, base=roster.base)

    duty = _current_or_next_duty(roster, now)
    if duty is None:
        return ViewModel(state=DutyState.NO_ROSTER, now=now, base=roster.base)

    vm = ViewModel(state=DutyState.BETWEEN_DUTIES, now=now, base=roster.base, duty=duty)
    vm.next_duty = _next_real_duty(roster, now)

    # Non-flying duties.
    if duty.duty_type == DutyType.DAY_OFF:
        vm.state = DutyState.DAY_OFF
        vm.next_duty = _next_real_duty(roster, now)
        return vm
    if duty.duty_type == DutyType.STANDBY:
        if duty.standby_start and duty.standby_start <= now <= (duty.standby_end or now):
            vm.state = DutyState.STANDBY
        else:
            vm.state = DutyState.BETWEEN_DUTIES
            vm.countdown_to = duty.standby_start
            vm.countdown_label = "STBY"
        return vm
    if duty.duty_type in (DutyType.TRAINING, DutyType.OTHER):
        vm.state = DutyState.BETWEEN_DUTIES
        vm.countdown_to = duty.report
        vm.countdown_label = duty.raw_code or "DUTY"
        return vm

    # --- Flying duty ---------------------------------------------------------
    sectors = duty.sectors
    active = _airborne_sector(sectors, now)
    home = _home_estimate(duty, debrief_minutes, walk_minutes, commute,
                          base=roster.base, transfer_minutes=transfer_minutes)
    vm.home = home

    if duty.report and now < duty.report:
        vm.state = DutyState.BETWEEN_DUTIES
        vm.countdown_to = duty.report
        vm.countdown_label = "RPT"
        vm.next_sector = sectors[0]
        vm.return_sector = sectors[-1] if len(sectors) > 1 else None
        return vm

    if active is not None:
        vm.state = DutyState.IN_FLIGHT
        vm.active_sector = active
        others = [s for s in sectors if s is not active and s.std >= active.std]
        vm.return_sector = others[0] if others else None
        vm.countdown_to = active.effective_arrival()
        vm.countdown_label = "LAND"
        return vm

    # Reported but not airborne: either pre-first-departure or a turnaround.
    next_sec = _next_sector(sectors, now)
    if next_sec is None:
        vm.state = DutyState.POST_DUTY
        vm.countdown_to = home.home_eta if home else None
        vm.countdown_label = "HOME"
        return vm

    if next_sec is sectors[0]:
        vm.state = DutyState.PRE_FLIGHT
        vm.countdown_to = next_sec.effective_departure()
        vm.countdown_label = "DEP"
    else:
        vm.state = DutyState.TURNAROUND
        vm.countdown_to = next_sec.effective_departure()
        vm.countdown_label = "DEP"
    vm.next_sector = next_sec
    vm.active_sector = next_sec
    vm.return_sector = sectors[-1] if next_sec is not sectors[-1] else None
    return vm


# --- helpers -----------------------------------------------------------------

def _current_or_next_duty(roster: Roster, now: dt.datetime) -> Optional[Duty]:
    """The duty in progress, else the soonest upcoming, else the most recent today."""
    duties = roster.sorted_duties()
    in_progress = [d for d in duties if _duty_window(d)[0] <= now <= _duty_window(d)[1]]
    if in_progress:
        return in_progress[-1]
    upcoming = [d for d in duties if _duty_window(d)[0] > now]
    if upcoming:
        return min(upcoming, key=lambda d: _duty_window(d)[0])
    today = [d for d in duties if d.date == now.date()]
    return today[-1] if today else (duties[-1] if duties else None)


def _next_real_duty(roster: Roster, now: dt.datetime) -> Optional[Duty]:
    """Soonest upcoming duty that isn't a day off (for the day-off board)."""
    upcoming = [d for d in roster.sorted_duties()
                if d.duty_type != DutyType.DAY_OFF and _duty_window(d)[0] > now]
    return min(upcoming, key=lambda d: _duty_window(d)[0]) if upcoming else None


def _duty_window(d: Duty) -> tuple[dt.datetime, dt.datetime]:
    midnight = dt.datetime(d.date.year, d.date.month, d.date.day, tzinfo=dt.timezone.utc)
    if d.duty_type == DutyType.STANDBY and d.standby_start:
        return d.standby_start, (d.standby_end or d.standby_start)
    if d.is_flying:
        start = d.report or d.sectors[0].std
        end = d.duty_end or d.sectors[-1].sta
        return start, end
    return midnight, midnight + dt.timedelta(hours=24)


def _airborne_sector(sectors: list[Sector], now: dt.datetime) -> Optional[Sector]:
    for s in sectors:
        if s.effective_departure() <= now <= s.effective_arrival():
            return s
    return None


def _next_sector(sectors: list[Sector], now: dt.datetime) -> Optional[Sector]:
    upcoming = [s for s in sectors if s.effective_departure() > now]
    return min(upcoming, key=lambda s: s.effective_departure()) if upcoming else None


def _home_estimate(duty: Duty, debrief_minutes: int, walk_minutes: int,
                   commute_minutes: int, base: str = "", transfer_minutes: int = 0) -> HomeEstimate:
    last = duty.sectors[-1]
    on_chocks = last.effective_arrival()
    is_live = bool(last.live and (last.live.on_block or last.live.eta))
    if getattr(duty, "personal", False) and base and last.arr != base:
        # Non-work flight landing away from base: drive arr->base, then commute home.
        commute_start = on_chocks + dt.timedelta(minutes=transfer_minutes)
        debrief_end = on_chocks
        home_eta = commute_start + dt.timedelta(minutes=commute_minutes)
    else:
        debrief_end = on_chocks + dt.timedelta(minutes=debrief_minutes)
        commute_start = debrief_end + dt.timedelta(minutes=walk_minutes)
        home_eta = commute_start + dt.timedelta(minutes=commute_minutes)
    return HomeEstimate(on_chocks=on_chocks, debrief_end=debrief_end,
                        commute_start=commute_start, home_eta=home_eta,
                        is_live=is_live)
