"""Flask control panel for the wall.

Run standalone:  python -m flightwall.web.app
Or it is started in a thread by flightwall.main when web.enabled.

Features:
  * Upload a roster (eCrew PDF or .ics) via the browser
  * Pull the configured iCal feed on demand
  * Sliders: commute, walk-to-car-park, debrief
  * Timezone toggle: UTC / Local Base / Local Station
  * Optional live Google Maps drive time (base car park -> home at debrief time)
  * Live preview of exactly what the wall is showing (with a time-travel field)
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import tempfile

from flask import Flask, jsonify, render_template, request

from ..config import (Config, build_tracker, load_roster, save_roster, normalize_reports)
from ..parsers.ecrew_pdf import parse_pdf
from ..parsers.ical_parser import parse_ical
from ..render.presenter import present
from ..render.simulator import render_png
from ..state_engine import compute_view
from ..tracking.base import update_active_sector

_runtime = {"maps_commute_minutes": None}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        from ..render.epaper import STYLE_LABELS
        from .. import __version__
        return render_template("index.html", cfg=Config.load(),
                               epaper_styles=STYLE_LABELS, version=__version__)

    @app.route("/api/state")
    def api_state():
        cfg = Config.load()
        roster = load_roster()
        at = request.args.get("at")
        now = dt.datetime.fromisoformat(at).replace(tzinfo=dt.timezone.utc) if at \
            else dt.datetime.now(dt.timezone.utc)

        live_commute = _runtime["maps_commute_minutes"] if cfg.use_maps_commute else None
        vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                          walk_minutes=cfg.walk_minutes,
                          commute_minutes=cfg.commute_minutes,
                          live_commute_minutes=live_commute)
        from ..config import transfer_minutes_for
        _tr = transfer_minutes_for(cfg, vm)
        if _tr:
            vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                              walk_minutes=cfg.walk_minutes,
                              commute_minutes=cfg.commute_minutes,
                              live_commute_minutes=live_commute, transfer_minutes=_tr)
        screen = present(vm, tz_mode=cfg.tz_mode, flight_prefix=cfg.display_prefix,
                         iata=cfg.airline_iata, now=now)
        if cfg.renderer == "epaper":
            from ..render.epaper import render as render_epaper
            import io as _io
            eimg = render_epaper(screen, cfg.epaper_style, cfg.epaper_width, cfg.epaper_height)
            buf = _io.BytesIO(); eimg.save(buf, format="PNG"); png = buf.getvalue()
        else:
            png = render_png(screen, cols=cfg.cols * cfg.chain, rows=cfg.rows, layout=cfg.layout)
        payload = {
            "state": vm.state.value,
            "header": screen.header, "line1": screen.line1,
            "line2": screen.line2, "line3": screen.line3,
            "accent": screen.accent, "progress": screen.progress,
            "flags": screen.flags,
            "now": now.isoformat(),
            "crew": roster.crew_name, "base": roster.base,
            "duties": len(roster.duties),
        }
        if png:
            payload["png"] = "data:image/png;base64," + base64.b64encode(png).decode()
        return jsonify(payload)

    @app.route("/api/config", methods=["POST"])
    def api_config():
        cfg = Config.load()
        form = request.get_json(force=True, silent=True) or request.form
        for key in ("airline_iata", "airline_icao", "base", "ical_url", "tz_mode",
                    "renderer", "tracker", "aerodatabox_key", "hardware_mapping",
                    "display_prefix", "layout", "epaper_style", "vestaboard_rw_key", "vestaboard_local_ip",
                    "fr24_api_token"):
            if key in form and form[key] != "":
                setattr(cfg, key, str(form[key]))
        for key in ("debrief_minutes", "walk_minutes", "commute_minutes",
                    "brightness", "rows", "cols", "chain", "poll_seconds",
                    "epaper_width", "epaper_height"):
            if key in form and str(form[key]) != "":
                setattr(cfg, key, int(float(form[key])))
        for key in ("home_lat", "home_lng", "base_lat", "base_lng"):
            if key in form and str(form[key]) != "":
                setattr(cfg, key, float(form[key]))
        if "google_maps_api_key" in form and form["google_maps_api_key"]:
            cfg.google_maps_api_key = str(form["google_maps_api_key"])
        cfg.use_maps_commute = str(form.get("use_maps_commute", "")).lower() in (
            "1", "true", "on", "yes")
        cfg.save()
        return jsonify({"ok": True})

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        f = request.files.get("roster")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "No file"}), 400
        cfg = Config.load()
        suffix = os.path.splitext(f.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            f.save(tmp.name)
            path = tmp.name
        try:
            if suffix == ".pdf":
                roster = parse_pdf(path, debrief_minutes=cfg.debrief_minutes)
            elif suffix in (".ics", ".ical"):
                with open(path, "rb") as fh:
                    roster = parse_ical(fh.read(), base_iata=cfg.base,
                                        duty_gap_hours=cfg.duty_gap_hours,
                                        report_lead_min=cfg.report_lead_min,
                                        debrief_minutes=cfg.debrief_minutes)
            else:
                return jsonify({"ok": False, "error": "Use a .pdf or .ics file"}), 400
            if not roster.base:
                roster.base = cfg.base
            save_roster(normalize_reports(roster, cfg))
            return jsonify({"ok": True, "duties": len(roster.duties),
                            "crew": roster.crew_name})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        finally:
            os.unlink(path)

    @app.route("/api/fetch_ical", methods=["POST"])
    def api_fetch_ical():
        import requests
        cfg = Config.load()
        if not cfg.ical_url:
            return jsonify({"ok": False, "error": "No iCal URL set"}), 400
        try:
            resp = requests.get(cfg.ical_url, timeout=20)
            resp.raise_for_status()
            roster = parse_ical(resp.content, base_iata=cfg.base,
                                duty_gap_hours=cfg.duty_gap_hours,
                                report_lead_min=cfg.report_lead_min,
                                debrief_minutes=cfg.debrief_minutes)
            if not roster.base:
                roster.base = cfg.base
            save_roster(normalize_reports(roster, cfg))
            return jsonify({"ok": True, "duties": len(roster.duties)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/style_preview")
    def api_style_preview():
        import io as _io
        from ..render.epaper import render as render_epaper
        cfg = Config.load(); roster = load_roster()
        at = request.args.get("at")
        now = dt.datetime.fromisoformat(at).replace(tzinfo=dt.timezone.utc) if at \
            else dt.datetime.now(dt.timezone.utc)
        vm = compute_view(roster, now, debrief_minutes=cfg.debrief_minutes,
                          walk_minutes=cfg.walk_minutes, commute_minutes=cfg.commute_minutes)
        screen = present(vm, tz_mode=cfg.tz_mode, flight_prefix=cfg.display_prefix,
                         iata=cfg.airline_iata, now=now)
        style = request.args.get("style", cfg.epaper_style)
        img = render_epaper(screen, style, cfg.epaper_width, cfg.epaper_height)
        buf = _io.BytesIO(); img.save(buf, format="PNG")
        return ("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())

    @app.route("/api/config_raw", methods=["GET", "POST"])
    def api_config_raw():
        import dataclasses, json as _json
        if request.method == "GET":
            return jsonify(dataclasses.asdict(Config.load()))
        incoming = request.get_json(force=True, silent=True) or {}
        cfg = Config.load(); fields = {f.name: f for f in dataclasses.fields(cfg)}
        applied = []
        for k, v in incoming.items():
            if k not in fields:
                continue
            try:
                ann = fields[k].type
                if ann in (int, "int") and v != "" and v is not None: v = int(v)
                elif ann in (float, "float") and v != "" and v is not None: v = float(v)
                elif ann in (bool, "bool"): v = bool(v)
                setattr(cfg, k, v); applied.append(k)
            except Exception:
                pass
        cfg.save()
        return jsonify({"ok": True, "applied": applied})

    @app.route("/api/upload_logo", methods=["POST"])
    def api_upload_logo():
        code = (request.form.get("code") or "").strip().upper()
        f = request.files.get("logo")
        if not code or not f:
            return jsonify({"ok": False, "message": "Pick an airline code and an image file."}), 400
        import os as _os
        data_dir = _os.path.expanduser(_os.environ.get("FLIGHTWALL_DATA", "~/.flightwall"))
        logos = _os.path.join(data_dir, "logos"); _os.makedirs(logos, exist_ok=True)
        ext = (f.filename.rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else "png")
        if ext not in ("png", "jpg", "jpeg"):
            return jsonify({"ok": False, "message": "Use a PNG or JPG."}), 400
        # remove any prior logo for this code, then save
        for e in ("png", "jpg", "jpeg"):
            p = _os.path.join(logos, f"{code}.{e}")
            if _os.path.exists(p):
                _os.remove(p)
        f.save(_os.path.join(logos, f"{code}.{ext}"))
        return jsonify({"ok": True, "message": f"Saved logo for {code}."})

    @app.route("/api/add_flight", methods=["POST"])
    def api_add_flight():
        from ..config import add_personal_flight
        cfg = Config.load()
        form = request.get_json(force=True, silent=True) or request.form
        ok, msg = add_personal_flight(cfg, form.get("flight_no", ""),
                                      form.get("date", ""),
                                      report_minutes=int(form.get("report_minutes", 90)))
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/commute", methods=["POST"])
    def api_commute():
        from ..maps import drive_minutes
        cfg = Config.load()
        mins = drive_minutes(cfg.google_maps_api_key,
                             (cfg.base_lat, cfg.base_lng) if cfg.base_lat else None,
                             (cfg.home_lat, cfg.home_lng) if cfg.home_lat else None)
        if mins is None:
            return jsonify({"ok": False,
                            "error": "Set key + coordinates, or use the slider"}), 400
        _runtime["maps_commute_minutes"] = mins
        return jsonify({"ok": True, "minutes": mins})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8080, debug=False)
