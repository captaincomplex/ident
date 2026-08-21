"""Flask control panel for the wall.

Run standalone:  python -m ident.web.app
Or it is started in a thread by ident.main when web.enabled.

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

from flask import (Flask, jsonify, redirect, render_template,
                   render_template_string, request, session, url_for)

from ..config import (Config, build_tracker, load_roster, save_roster, normalize_reports)
from ..parsers.ecrew_pdf import parse_pdf
from ..parsers.ical_parser import parse_ical
from ..render.presenter import present
from ..render.simulator import render_png
from ..state_engine import compute_view
from ..tracking.base import update_active_sector

_runtime = {"maps_commute_minutes": None}


SETUP_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Ident - first-time setup</title>
<style>
 body{background:#16181c;color:#e8e6de;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
      margin:0;padding:24px;display:flex;justify-content:center}
 .box{background:#20232a;padding:26px;border-radius:14px;max-width:440px;width:100%}
 h1{font-size:21px;margin:0 0 4px} p.sub{color:#9aa0aa;font-size:13.5px;margin:0 0 20px;line-height:1.5}
 label{display:block;font-size:11.5px;color:#9aa0aa;margin:16px 0 5px;letter-spacing:.05em}
 .hint{color:#7b8794;font-size:12px;margin-top:4px}
 input{width:100%;padding:10px;border-radius:8px;border:1px solid #333;background:#15171b;
       color:#e8e6de;font-size:16px;box-sizing:border-box}
 button{width:100%;margin-top:22px;padding:12px;border:0;border-radius:8px;
        background:#ca7034;color:#fff;font-size:15px;font-weight:600}
 .err{background:#4a2020;color:#ffb3b3;padding:9px;border-radius:8px;font-size:13px;margin-top:14px}
 .step{color:#ca7034;font-size:11.5px;letter-spacing:.08em;margin-bottom:6px}
</style>
<form method=post class=box>
<div class=step>FIRST-TIME SETUP</div>
<h1>Let's set up your display</h1>
<p class=sub>Everything here can be changed later from the control panel. Your roster is
stored on this device only - it is never sent anywhere else.</p>

<label>DISPLAY NAME</label>
<input name=device_name placeholder="Kitchen" value="Ident">

<label>HOME BASE (IATA)</label>
<input name=base placeholder="LGW" autocapitalize=characters>

<label>AIRLINE CODE (IATA)</label>
<input name=airline_iata placeholder="U2" autocapitalize=characters>

<label>ROSTER CALENDAR URL (optional)</label>
<input name=ical_url placeholder="https://.../basic.ics">

<label>PANEL USERNAME</label>
<input name=auth_user value="pilot" autocapitalize=none>

<label>PANEL PASSWORD (blank = no login)</label>
<input name=auth_password type=password autocomplete=new-password>

<button type=submit>Finish setup</button>
{% if error %}<div class=err>{{ error }}</div>{% endif %}
</form>"""


LOGIN_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Ident - sign in</title>
<style>
 body{background:#16181c;color:#e8e6de;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
 form{background:#20232a;padding:28px;border-radius:14px;width:300px;box-shadow:0 8px 30px #0008}
 h1{font-size:19px;margin:0 0 4px} p.sub{color:#9aa0aa;font-size:13px;margin:0 0 18px}
 label{display:block;font-size:12px;color:#9aa0aa;margin:12px 0 4px;letter-spacing:.04em}
 input{width:100%;padding:10px;border-radius:8px;border:1px solid #333;background:#15171b;
       color:#e8e6de;font-size:16px;box-sizing:border-box}
 button{width:100%;margin-top:18px;padding:11px;border:0;border-radius:8px;
        background:#ca7034;color:#fff;font-size:15px;font-weight:600}
 .err{background:#4a2020;color:#ffb3b3;padding:9px;border-radius:8px;font-size:13px;margin-top:14px}
</style>
<form method=post><h1>Ident</h1><p class=sub>Sign in to the control panel</p>
<label>USERNAME</label><input name=username autocomplete=username autocapitalize=none autofocus>
<label>PASSWORD</label><input name=password type=password autocomplete=current-password>
<button type=submit>Sign in</button>
{% if error %}<div class=err>{{ error }}</div>{% endif %}</form>"""


def create_app() -> Flask:
    app = Flask(__name__)

    from .. import auth as _auth
    app.secret_key = _auth.secret_key()

    @app.before_request
    def _first_run():
        if request.endpoint in ("setup", "static"):
            return None
        cfg = Config.load()
        if not getattr(cfg, "setup_complete", False):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Setup not complete"}), 409
            return redirect(url_for("setup"))
        return None

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        cfg = Config.load()
        if getattr(cfg, "setup_complete", False):
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            f = request.form
            pw = (f.get("auth_password") or "").strip()
            if pw and len(pw) < 6:
                error = "Password must be at least 6 characters (or leave it blank)."
            else:
                cfg.device_name = (f.get("device_name") or "Ident").strip() or "Ident"
                cfg.base = (f.get("base") or cfg.base).strip().upper()
                cfg.airline_iata = (f.get("airline_iata") or cfg.airline_iata).strip().upper()
                cfg.ical_url = (f.get("ical_url") or "").strip()
                cfg.auth_user = (f.get("auth_user") or "pilot").strip() or "pilot"
                if pw:
                    cfg.auth_password_hash = _auth.hash_password(pw)
                    session["fw_auth"] = True
                cfg.setup_complete = True
                cfg.save()
                if cfg.ical_url:
                    try:
                        from ..config import refresh_from_ical
                        refresh_from_ical(cfg)
                    except Exception:
                        pass
                return redirect(url_for("index"))
        return render_template_string(SETUP_PAGE, error=error), 200

    @app.before_request
    def _require_login():
        cfg = Config.load()
        if not _auth.is_enabled(cfg):
            return None                                  # no password set: open
        if request.endpoint in ("login", "setup", "static"):
            return None
        if session.get("fw_auth") is True:
            return None
        if getattr(cfg, "auth_trust_lan", False) and \
           _auth.is_private_address(request.remote_addr):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Login required"}), 401
        return redirect(url_for("login", next=request.path))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        cfg = Config.load()
        if not _auth.is_enabled(cfg):
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            if _auth.check(cfg, request.form.get("username", ""),
                           request.form.get("password", "")):
                session["fw_auth"] = True
                session.permanent = True
                nxt = request.args.get("next") or url_for("index")
                return redirect(nxt if nxt.startswith("/") else url_for("index"))
            error = "Incorrect username or password."
        return render_template_string(LOGIN_PAGE, error=error), (401 if error else 200)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/api/set_password", methods=["POST"])
    def api_set_password():
        cfg = Config.load()
        form = request.get_json(force=True, silent=True) or request.form
        new = (form.get("password") or "").strip()
        user = (form.get("username") or cfg.auth_user or "pilot").strip()
        if _auth.is_enabled(cfg) and not session.get("fw_auth"):
            return jsonify({"ok": False, "error": "Sign in first"}), 401
        if new and len(new) < 6:
            return jsonify({"ok": False, "error": "Use at least 6 characters"}), 400
        cfg.auth_user = user
        cfg.auth_password_hash = _auth.hash_password(new) if new else ""
        cfg.save()
        session["fw_auth"] = bool(new)
        return jsonify({"ok": True, "enabled": bool(new), "username": user})

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
            from ..config import refresh_from_ical
            n = refresh_from_ical(cfg)
            return jsonify({"ok": True, "duties": n})
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

    @app.route("/api/wifi", methods=["GET"])
    def api_wifi_list():
        from ..wifi import list_saved, current_ssid
        return jsonify({"saved": list_saved(), "current": current_ssid()})

    @app.route("/api/wifi/scan")
    def api_wifi_scan():
        from ..wifi import scan
        return jsonify({"visible": scan()})

    @app.route("/api/wifi", methods=["POST"])
    def api_wifi_add():
        from ..wifi import add, connect_now
        d = request.get_json(force=True, silent=True) or {}
        fn = connect_now if d.get("connect") else add
        ok, msg = fn((d.get("ssid") or "").strip(), d.get("password") or "")
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/wifi/delete", methods=["POST"])
    def api_wifi_delete():
        from ..wifi import remove
        d = request.get_json(force=True, silent=True) or {}
        ok, msg = remove((d.get("name") or "").strip())
        return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/upload_logo", methods=["POST"])
    def api_upload_logo():
        code = (request.form.get("code") or "").strip().upper()
        f = request.files.get("logo")
        if not code or not f:
            return jsonify({"ok": False, "message": "Pick an airline code and an image file."}), 400
        import os as _os
        data_dir = _os.path.expanduser(_os.environ.get("IDENT_DATA", "~/.ident"))
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

    @app.route("/api/update/check")
    def api_update_check():
        from ..updates import check
        cfg = Config.load()
        return jsonify(check(cfg.update_repo))

    @app.route("/api/update/install", methods=["POST"])
    def api_update_install():
        from ..updates import check, install, _sha256_from_notes
        cfg = Config.load()
        info = check(cfg.update_repo)
        if not info.get("ok"):
            return jsonify({"ok": False, "error": info.get("error") or "Could not reach GitHub"}), 502
        if not info.get("update_available"):
            return jsonify({"ok": False, "error": "Already up to date"}), 400
        res = install(info["url"], _sha256_from_notes(info.get("notes", "")))
        return jsonify(res), (200 if res.get("ok") else 500)

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
