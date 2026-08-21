"""Configuration, roster persistence, and provider factories.

Settings live in a JSON file in the data directory so the web UI can update
them at runtime. The roster is cached as JSON too, so the wall survives a
reboot without a network round-trip.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from .models import Roster, roster_from_dict

def _data_dir() -> str:
    """Where config/roster/logos live.

    Honours $IDENT_DATA, else ~/.ident. If ~/.ident doesn't exist yet but an
    older ~/.flightwall does, adopt the old directory so an upgraded install
    keeps its roster, logos and settings instead of starting empty.
    """
    env = os.environ.get("IDENT_DATA")
    if env:
        return env
    new = os.path.expanduser("~/.ident")
    old = os.path.expanduser("~/.flightwall")
    if not os.path.isdir(new) and os.path.isdir(old):
        try:
            os.rename(old, new)          # same filesystem: instant, keeps everything
        except Exception:
            return old                   # couldn't move; keep using the old one
    return new


DATA_DIR = _data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
ROSTER_PATH = os.path.join(DATA_DIR, "roster.json")


@dataclass
class Config:
    # Airline / identity
    airline_iata: str = "U2"          # easyJet (from the sample roster)
    airline_icao: str = "EZY"
    display_prefix: str = "EZY"       # what the wall shows before the flight no.
    base: str = "LGW"

    # Roster source
    ical_url: str = ""
    ical_refresh_minutes: int = 30    # auto-refresh the iCal feed every N minutes (0 = off)

    # Device identity (useful when a pilot runs more than one display)
    device_name: str = "Ident"
    setup_complete: bool = False      # False on a fresh install -> show the setup wizard

    # Updates (the device pulls; nothing reaches in from outside)
    update_repo: str = "captaincomplex/ident"
    update_check_hours: int = 24      # 0 disables the check entirely

    # Web panel login (blank password = no login required)
    auth_user: str = "pilot"
    auth_password_hash: str = ""      # set via the panel or --set-password
    auth_trust_lan: bool = False      # if True, skip the login for local-network clients

    # Home-time chain (minutes)
    debrief_minutes: int = 30
    walk_minutes: int = 8             # "walk to car park" slider
    commute_minutes: int = 45         # manual slider
    use_maps_commute: bool = False    # if True, compute drive time live

    # Locations for the optional Google Maps drive-time estimate
    home_lat: float | None = None
    home_lng: float | None = None
    base_lat: float | None = None     # airport / crew car park
    base_lng: float | None = None
    google_maps_api_key: str = ""

    # Display
    tz_mode: str = "base"             # utc | base | station
    rows: int = 32
    cols: int = 64
    chain: int = 2
    brightness: int = 60
    hardware_mapping: str = "adafruit-hat"
    renderer: str = "simulator"       # simulator | matrix | vestaboard | epaper
    layout: str = "full"              # full (128x32) | compact (64x32)
    epaper_style: str = "board_solari"  # see render/epaper.py STYLE_LABELS
    epaper_width: int = 600
    epaper_height: int = 448
    epaper_saturation: float = 0.6
    epaper_panel: str = "auto"        # auto | impression_5_7 | impression_4 | impression_7_3 | impression_13_3
    epaper_palette: str = "auto"      # auto | acep7 | spectra6
    vestaboard_rw_key: str = ""       # Vestaboard Read/Write API key
    vestaboard_local_ip: str = ""     # optional: local-API IP (faster, offline)

    # Tracking
    tracker: str = "aerodatabox"      # aerodatabox | fr24 | opensky | none
    aerodatabox_key: str = ""
    fr24_api_token: str = ""          # Flightradar24 API token (separate product)
    fr24_use_sandbox: bool = False    # test against FR24's free static sandbox
    opensky_user: str = ""
    opensky_pass: str = ""
    poll_seconds: int = 180           # live-tracking poll interval while airborne

    report_lead_min: int = 60         # estimated report lead before STD (typical)
    report_lead_early_min: int = 75   # estimated report lead for early flights
    early_flight_before_hour: int = 7 # STD local-base hour below which a flight is "early"
    personal_report_min: int = 90     # report lead for manually-added personal flights
    duty_gap_hours: float = 5.0       # iCal: gap that splits duties

    def save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__annotations__}
            if "setup_complete" not in data:
                # Config written before the setup wizard existed: this is an
                # already-configured install, so don't send it through setup.
                known["setup_complete"] = True
            return cls(**known)
        cfg = cls()
        cfg.save()
        return cfg


def save_roster(roster: Roster) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ROSTER_PATH, "w") as f:
        json.dump(roster.to_dict(), f, indent=2)


def load_roster() -> Roster:
    if os.path.exists(ROSTER_PATH):
        with open(ROSTER_PATH) as f:
            return roster_from_dict(json.load(f))
    return Roster()


def refresh_from_ical(cfg: "Config" = None):
    """Fetch the configured iCal feed, parse and store it.

    Returns the number of duties stored, or None if no iCal URL is set.
    Raises on network/parse errors so callers can report them.
    """
    import requests
    from .parsers.ical_parser import parse_ical
    cfg = cfg or Config.load()
    if not cfg.ical_url:
        return None
    resp = requests.get(cfg.ical_url, timeout=20)
    resp.raise_for_status()
    roster = parse_ical(resp.content, base_iata=cfg.base,
                        duty_gap_hours=cfg.duty_gap_hours,
                        report_lead_min=cfg.report_lead_min,
                        debrief_minutes=cfg.debrief_minutes)
    if not roster.base:
        roster.base = cfg.base
    save_roster(normalize_reports(roster, cfg))
    return len(roster.duties)


_TRANSFER_CACHE: dict = {}


def transfer_minutes_for(cfg: "Config", vm) -> int:
    """Drive minutes from a personal flight's arrival airport to base (cached)."""
    duty = getattr(vm, "duty", None)
    if not (duty and getattr(duty, "personal", False) and duty.sectors):
        return 0
    arr = duty.sectors[-1].arr; base = cfg.base
    if not arr or arr == base or not cfg.google_maps_api_key:
        return 0
    key = (arr, base)
    if key not in _TRANSFER_CACHE:
        from .maps import airport_drive_minutes
        _TRANSFER_CACHE[key] = airport_drive_minutes(cfg.google_maps_api_key, arr, base) or 0
    return _TRANSFER_CACHE[key]


def normalize_reports(roster: Roster, cfg: "Config") -> Roster:
    """Fill in report time only where the calendar didn't give one.

    Calendar-provided report times are left exactly as-is. Estimated ones default
    to ``report_lead_min`` (60) before STD, or ``report_lead_early_min`` (75) for
    early flights (STD local-base hour < ``early_flight_before_hour``).
    """
    import datetime as dt
    from .models import DutyType
    from .timezones import for_display
    base = roster.base or cfg.base
    for d in roster.duties:
        if d.duty_type != DutyType.FLY or not d.sectors or d.personal:
            continue
        if d.report is not None and not d.report_estimated:
            continue                              # trust the calendar exactly
        std = d.sectors[0].std
        try:
            hour = for_display(std, "base", base).hour
        except Exception:
            hour = std.hour
        lead = cfg.report_lead_early_min if hour < cfg.early_flight_before_hour \
            else cfg.report_lead_min
        d.report = std - dt.timedelta(minutes=lead)
        d.report_estimated = True
    return roster


def add_personal_flight(cfg: "Config", flight_no: str, date_iso: str,
                        report_minutes: int | None = None) -> tuple[bool, str]:
    """Look a flight up by number+date and add it as a personal duty.

    Report defaults to ``personal_report_min`` (90) before departure.
    Returns (ok, message).
    """
    import datetime as dt
    import re
    from .models import Sector, Duty, DutyType

    raw = (flight_no or "").strip().upper().replace(" ", "")
    if not raw:
        return False, "Enter a flight number, e.g. U28243 or BA432."
    m = re.match(r"^([A-Z0-9]{2,3}?)(\d{1,4}[A-Z]?)$", raw)
    airline = m.group(1) if m else raw[:2]
    number = m.group(2) if m else raw[2:]
    try:
        the_date = dt.date.fromisoformat(date_iso)
    except Exception:
        return False, "Enter the date as YYYY-MM-DD."

    tracker = build_tracker(cfg)
    if not hasattr(tracker, "lookup_flight"):
        return False, "The current tracker can't look up flights. Switch to AeroDataBox in Advanced."
    info = tracker.lookup_flight(raw, date_iso)
    if not info:
        return False, (f"Couldn't find {raw} on {date_iso}. Check the number/date, and "
                       "that your AeroDataBox key is set in Advanced.")

    sector = Sector(flight_no=number, dep=info["dep"], arr=info["arr"],
                    std=info["std"], sta=info["sta"], aircraft_type=info.get("aircraft"))
    lead = report_minutes if report_minutes is not None else cfg.personal_report_min
    report = info["std"] - dt.timedelta(minutes=lead)
    duty = Duty(date=the_date, duty_type=DutyType.FLY, raw_code="PERSONAL",
                report=report, duty_end=info["sta"], sectors=[sector],
                personal=True, airline=airline)

    roster = load_roster()
    if not roster.base:
        roster.base = cfg.base
    roster.duties = [d for d in roster.duties
                     if not (d.personal and d.date == the_date and d.sectors
                             and d.sectors[0].flight_no == number)]
    roster.duties.append(duty)
    save_roster(roster)
    return True, (f"Added {airline}{number}  {info['dep']}\u2192{info['arr']} on {date_iso} "
                  f"(report {report.strftime('%H:%MZ')}).")


def build_tracker(cfg: Config):
    if cfg.tracker == "aerodatabox":
        from .tracking.aerodatabox import AeroDataBoxTracker
        return AeroDataBoxTracker(cfg.aerodatabox_key)
    if cfg.tracker == "fr24":
        from .tracking.flightradar24 import FlightRadar24Tracker
        return FlightRadar24Tracker(cfg.fr24_api_token, use_sandbox=cfg.fr24_use_sandbox)
    if cfg.tracker == "opensky":
        from .tracking.opensky import OpenSkyTracker
        return OpenSkyTracker(cfg.opensky_user, cfg.opensky_pass)
    from .tracking.base import NullTracker
    return NullTracker()


def build_renderer(cfg: Config):
    if cfg.renderer == "matrix":
        from .render.matrix import MatrixRenderer
        return MatrixRenderer(rows=cfg.rows, cols=cfg.cols, chain=cfg.chain,
                              brightness=cfg.brightness,
                              hardware_mapping=cfg.hardware_mapping)
    if cfg.renderer == "vestaboard":
        from .render.vestaboard import VestaboardRenderer
        return VestaboardRenderer(rw_key=cfg.vestaboard_rw_key,
                                  local_ip=cfg.vestaboard_local_ip)
    if cfg.renderer == "epaper":
        from .render.epaper import InkyRenderer, STYLE_LABELS
        def _persist(style):
            c = Config.load(); c.epaper_style = style; c.save()
        from .render.epaper import PANELS
        w, h, pal = cfg.epaper_width, cfg.epaper_height, cfg.epaper_palette
        if cfg.epaper_panel in PANELS:            # explicit panel choice wins
            w, h, pal = PANELS[cfg.epaper_panel]
            if cfg.epaper_palette != "auto":
                pal = cfg.epaper_palette
        return InkyRenderer(style=cfg.epaper_style, width=w, height=h,
                            saturation=cfg.epaper_saturation, palette=pal,
                            styles=[k for k, _ in STYLE_LABELS], on_style_change=_persist)
    from .render.simulator import ConsoleSimulator
    return ConsoleSimulator()
