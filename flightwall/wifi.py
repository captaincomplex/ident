"""Manage saved Wi-Fi networks via NetworkManager (nmcli).

Lets the web UI pre-load networks (e.g. a hotel or crashpad) so the Pi connects
automatically when it's in range - no SSH needed at the destination. Networks can
be added even when they're not currently visible.

The web app runs as your normal user; modifying system Wi-Fi connections usually
needs root, so calls fall back to `sudo -n nmcli`. To allow that without a
password prompt, add a one-line sudoers rule (see INSTALL_PI.md):

    echo "$USER ALL=(root) NOPASSWD: /usr/bin/nmcli" | sudo tee /etc/sudoers.d/flightwall-nmcli
"""
from __future__ import annotations

import shutil
import subprocess


def _run(args, timeout=25):
    """Run nmcli; if not authorized, retry via non-interactive sudo."""
    if not shutil.which("nmcli"):
        return False, "NetworkManager (nmcli) not found on this system."
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return True, r.stdout.strip()
        blob = (r.stderr + r.stdout).lower()
        if "not authorized" in blob or "permission" in blob or "access denied" in blob or "insufficient" in blob:
            r2 = subprocess.run(["sudo", "-n", "nmcli", *args],
                                capture_output=True, text=True, timeout=timeout)
            if r2.returncode == 0:
                return True, r2.stdout.strip()
            if "a password is required" in (r2.stderr or "").lower() or "sudo:" in (r2.stderr or "").lower():
                return False, ("Permission denied. Allow the app to manage Wi-Fi with:\n"
                               "  echo \"$USER ALL=(root) NOPASSWD: /usr/bin/nmcli\" "
                               "| sudo tee /etc/sudoers.d/flightwall-nmcli")
            return False, (r2.stderr or r.stderr or "nmcli error").strip()
        return False, (r.stderr or r.stdout or "nmcli error").strip()
    except Exception as e:
        return False, str(e)


def list_saved():
    """Names of saved Wi-Fi connections, current one first."""
    ok, out = _run(["-t", "-f", "NAME,TYPE", "connection", "show"])
    nets = []
    if ok:
        for line in out.splitlines():
            p = line.split(":")
            if len(p) >= 2 and p[1] in ("802-11-wireless", "wifi"):
                nets.append(p[0])
    return nets


def current_ssid():
    ok, out = _run(["-t", "-f", "ACTIVE,SSID", "device", "wifi"])
    if ok:
        for line in out.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1]
    return None


def scan():
    """SSIDs currently visible (best-effort)."""
    ok, out = _run(["-t", "-f", "SIGNAL,SSID", "device", "wifi", "list", "--rescan", "yes"])
    seen = []
    if ok:
        for line in out.splitlines():
            ssid = line.split(":", 1)[1] if ":" in line else ""
            if ssid and ssid not in seen:
                seen.append(ssid)
    return seen


def add(ssid, password="", hidden=False):
    """Save (or update) a Wi-Fi network so the Pi auto-joins it when in range.

    Works even if the network isn't currently visible.
    """
    ssid = (ssid or "").strip()
    if not ssid:
        return False, "Enter a network name (SSID)."
    if password and len(password) < 8:
        return False, "Wi-Fi passwords are at least 8 characters."

    if ssid not in list_saved():
        ok, out = _run(["connection", "add", "type", "wifi", "con-name", ssid,
                        "ssid", ssid, "connection.autoconnect", "yes"])
        if not ok:
            return False, out
    steps = [["connection", "modify", ssid, "802-11-wireless.ssid", ssid,
              "connection.autoconnect", "yes",
              "802-11-wireless.hidden", "yes" if hidden else "no"]]
    if password:
        steps.append(["connection", "modify", ssid,
                      "802-11-wireless-security.key-mgmt", "wpa-psk",
                      "802-11-wireless-security.psk", password])
    else:
        steps.append(["connection", "modify", ssid,
                      "802-11-wireless-security.key-mgmt", ""])
    for s in steps:
        ok, out = _run(s)
        if not ok:
            return False, out
    return True, f"Saved '{ssid}'. The Pi will join it automatically when in range."


def remove(name):
    name = (name or "").strip()
    if not name:
        return False, "Which network?"
    ok, out = _run(["connection", "delete", name])
    return ok, (f"Removed '{name}'." if ok else out)


def connect_now(ssid, password=""):
    """Save and try to connect immediately (only works if in range)."""
    ok, msg = add(ssid, password)
    if not ok:
        return ok, msg
    ok2, out = _run(["connection", "up", ssid])
    return (True, f"Connected to '{ssid}'.") if ok2 else (True, msg + " (not in range yet)")
