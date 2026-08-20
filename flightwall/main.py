"""Flight Wall daemon.

Each tick it recomputes the current state and renders it. While you're airborne
it polls the live tracker (at most every poll_seconds) and merges actual times /
ETA into the active sector so the wall and the home estimate track reality.

Run on the Pi:
    python -m flightwall.main              # renders to configured output + web UI
    python -m flightwall.main --no-web     # headless

The web control panel runs in a background thread on port 8080 by default.
"""
from __future__ import annotations

import argparse
import datetime as dt
import threading
import time

from .config import Config, build_renderer, build_tracker, load_roster
from .maps import drive_minutes
from .render.presenter import present
from .state_engine import DutyState, compute_view
from .tracking.base import update_active_sector


def _start_web(port: int):
    from .web.app import create_app
    app = create_app()
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False,
                               use_reloader=False),
        daemon=True).start()


def run(enable_web: bool = True, port: int = 8080, tick_seconds: int = 30):
    cfg = Config.load()
    renderer = build_renderer(cfg)
    tracker = build_tracker(cfg)
    try:
        from . import geo
        threading.Thread(target=geo.prefetch, daemon=True).start()
    except Exception:
        pass
    if enable_web:
        _start_web(port)
        print(f"[flightwall] control panel on http://0.0.0.0:{port}")

    last_poll = 0.0
    last_ical = 0.0
    maps_commute = None
    from . import __version__
    print(f"[flightwall] v{__version__} started · output={cfg.renderer} · tracker={cfg.tracker}")
    while True:
        cfg = Config.load()                      # pick up web edits live
        if cfg.ical_url and cfg.ical_refresh_minutes and \
           (time.time() - last_ical >= cfg.ical_refresh_minutes * 60):
            try:
                from .config import refresh_from_ical
                n = refresh_from_ical(cfg)
                if n is not None:
                    print(f"[flightwall] iCal auto-refresh: {n} duties")
            except Exception as e:
                print(f"[flightwall] iCal refresh error: {e}")
            last_ical = time.time()
        roster = load_roster()
        now = dt.datetime.now(dt.timezone.utc)

        # Provisional view to learn the state cheaply.
        vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                          walk_minutes=cfg.walk_minutes,
                          commute_minutes=cfg.commute_minutes)

        # Poll live tracking only while airborne, and not too often.
        if vm.state == DutyState.IN_FLIGHT and cfg.tracker != "none":
            if time.time() - last_poll >= cfg.poll_seconds:
                try:
                    update_active_sector(roster, tracker, cfg.airline_iata,
                                         cfg.airline_icao, now)
                except Exception as e:
                    print(f"[flightwall] tracker error: {e}")
                last_poll = time.time()

        # Optional live commute time, refreshed near end of duty.
        live_commute = None
        if cfg.use_maps_commute and cfg.google_maps_api_key and cfg.home_lat:
            if vm.home and vm.home.commute_start:
                if maps_commute is None or vm.state in (DutyState.IN_FLIGHT,
                                                        DutyState.TURNAROUND):
                    maps_commute = drive_minutes(
                        cfg.google_maps_api_key,
                        (cfg.base_lat, cfg.base_lng), (cfg.home_lat, cfg.home_lng),
                        depart_at=vm.home.commute_start)
            live_commute = maps_commute

        vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                          walk_minutes=cfg.walk_minutes,
                          commute_minutes=cfg.commute_minutes,
                          live_commute_minutes=live_commute)
        from .config import transfer_minutes_for
        _tr = transfer_minutes_for(cfg, vm)
        if _tr:
            vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                              walk_minutes=cfg.walk_minutes,
                              commute_minutes=cfg.commute_minutes,
                              live_commute_minutes=live_commute, transfer_minutes=_tr)
        screen = present(vm, tz_mode=cfg.tz_mode, flight_prefix=cfg.display_prefix, iata=cfg.airline_iata, now=now)

        try:
            renderer.show(screen)
        except Exception as e:
            print(f"[flightwall] render error: {e}")

        time.sleep(tick_seconds)


def main():
    ap = argparse.ArgumentParser(description="Flight Wall daemon")
    ap.add_argument("--no-web", action="store_true", help="disable the web panel")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--tick", type=int, default=30, help="render interval seconds")
    ap.add_argument("--set-password", action="store_true",
                    help="set (or clear) the web panel login, then exit")
    args = ap.parse_args()
    if args.set_password:
        import getpass
        from .auth import hash_password
        cfg = Config.load()
        user = input(f"Username [{cfg.auth_user or 'pilot'}]: ").strip() or (cfg.auth_user or "pilot")
        pw = getpass.getpass("Password (blank to disable login): ")
        if pw and pw != getpass.getpass("Confirm password: "):
            print("Passwords did not match."); return
        cfg.auth_user = user
        cfg.auth_password_hash = hash_password(pw) if pw else ""
        cfg.save()
        print(f"Login {'enabled for user ' + user if pw else 'disabled'}.")
        return
    try:
        run(enable_web=not args.no_web, port=args.port, tick_seconds=args.tick)
    except KeyboardInterrupt:
        print("\n[flightwall] stopped")


if __name__ == "__main__":
    main()
