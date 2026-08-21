"""Wi-Fi onboarding without a keyboard, a laptop or a Terminal.

If the device boots and can't get onto a network, it raises its own hotspot.
The owner joins that from a phone, picks their home network from a list and
types the password. No Imager settings, no SSH, no typing of commands.

Only 2.4GHz networks are offered on hardware that can't see 5GHz (the Pi Zero
2 W), because listing a network the radio physically cannot join is the single
most reliable way to waste somebody's evening.
"""
from __future__ import annotations

import subprocess
import time

AP_SSID = "Ident-Setup"
AP_CON = "ident-setup-ap"
AP_ADDR = "10.42.0.1"


def _nm(args, timeout=25):
    from .wifi import _run
    return _run(args, timeout=timeout)


# ---------- state ----------

def is_online() -> bool:
    """True when NetworkManager reports full or limited connectivity."""
    ok, out = _nm(["-t", "networking", "connectivity", "check"])
    if ok and out.strip() in ("full", "portal", "limited"):
        return True
    ok, out = _nm(["-t", "-f", "STATE", "general", "status"])
    return ok and out.strip().startswith("connected")


def ap_active() -> bool:
    ok, out = _nm(["-t", "-f", "NAME", "connection", "show", "--active"])
    return ok and AP_CON in out.split("\n")


# ---------- scanning ----------

def parse_scan(raw: str, only_24ghz: bool = True) -> list[dict]:
    """Turn `nmcli -t -f SSID,FREQ,SIGNAL,SECURITY device wifi list` into dicts.

    Sorted strongest first, one entry per SSID. 5GHz rows are dropped when the
    radio can't use them, so the list only shows joinable networks.
    """
    seen: dict[str, dict] = {}
    for line in (raw or "").splitlines():
        # nmcli escapes colons inside fields as '\:' - split on unescaped ones
        parts, buf, esc = [], "", False
        for ch in line:
            if esc:
                buf += ch; esc = False
            elif ch == "\\":
                esc = True
            elif ch == ":":
                parts.append(buf); buf = ""
            else:
                buf += ch
        parts.append(buf)
        if len(parts) < 3:
            continue
        ssid = parts[0].strip()
        if not ssid:
            continue
        try:
            freq = int("".join(c for c in parts[1] if c.isdigit()) or 0)
            signal = int("".join(c for c in parts[2] if c.isdigit()) or 0)
        except ValueError:
            continue
        band24 = freq < 3000
        if only_24ghz and not band24:
            continue
        sec = parts[3].strip() if len(parts) > 3 else ""
        prev = seen.get(ssid)
        if prev is None or signal > prev["signal"]:
            seen[ssid] = {"ssid": ssid, "signal": signal, "band": "2.4GHz" if band24 else "5GHz",
                          "secure": bool(sec and sec != "--")}
    return sorted(seen.values(), key=lambda n: -n["signal"])


def radio_is_24ghz_only() -> bool:
    """Pi Zero 2 W and Zero W have 2.4GHz-only radios."""
    try:
        model = open("/proc/device-tree/model", "rb").read().decode(errors="ignore")
    except Exception:
        return False
    m = model.lower()
    return "zero 2 w" in m or ("zero w" in m and "zero 2" not in m)


def scan(force_all: bool = False) -> list[dict]:
    _nm(["device", "wifi", "rescan"], timeout=30)
    ok, out = _nm(["-t", "-f", "SSID,FREQ,SIGNAL,SECURITY", "device", "wifi", "list"], timeout=30)
    if not ok:
        return []
    return parse_scan(out, only_24ghz=(not force_all) and radio_is_24ghz_only())


# ---------- hotspot ----------

def start_ap() -> tuple[bool, str]:
    if ap_active():
        return True, "already running"
    _nm(["connection", "delete", AP_CON])
    ok, out = _nm(["device", "wifi", "hotspot", "ifname", "wlan0",
                   "con-name", AP_CON, "ssid", AP_SSID])
    if not ok:
        return False, out
    _nm(["connection", "modify", AP_CON, "connection.autoconnect", "no"])
    return True, AP_SSID


def stop_ap() -> None:
    _nm(["connection", "down", AP_CON])
    _nm(["connection", "delete", AP_CON])


def join(ssid: str, password: str = "") -> tuple[bool, str]:
    """Join a network, dropping the hotspot first so the radio is free."""
    ssid = (ssid or "").strip()
    if not ssid:
        return False, "Choose a network."
    if password and len(password) < 8:
        return False, "Wi-Fi passwords are at least 8 characters."
    was_ap = ap_active()
    if was_ap:
        stop_ap(); time.sleep(2)
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    ok, out = _nm(args, timeout=60)
    if ok:
        return True, f"Connected to {ssid}."
    if was_ap:                       # failed - put the hotspot back so we stay reachable
        time.sleep(1); start_ap()
    return False, out or "Could not connect. Check the password."
