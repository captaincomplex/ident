"""Self-updating: check GitHub Releases, verify, install.

The device *pulls* updates - it checks a public Releases feed over HTTPS on a
schedule, so nothing needs to reach in from outside and there is no server to
run. Nothing personal is sent; the only request is an unauthenticated GET of
the releases endpoint.

An update is applied only when asked for (from the panel), never silently:

  1. download the release's zip asset to a temp file
  2. check its SHA-256 against the digest published in the release notes
     (a line reading  sha256: <hex>  ), when one is present
  3. unpack to a staging dir and sanity-check it imports
  4. back up the current app, swap the new one in, restart the service

If any step fails the running install is left untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
DEFAULT_REPO = "captaincomplex/ident"
UA = {"User-Agent": "ident-updater"}


def _ver_tuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3] or [0])


def is_newer(remote: str, local: str) -> bool:
    return _ver_tuple(remote) > _ver_tuple(local)


def check(repo: str = DEFAULT_REPO, timeout: int = 20) -> dict:
    """Look up the latest release. Returns a dict; never raises."""
    from . import __version__
    out = {"ok": False, "current": __version__, "latest": "", "update_available": False,
           "url": "", "notes": "", "error": ""}
    try:
        req = urllib.request.Request(RELEASES_API.format(repo=repo), headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        tag = (data.get("tag_name") or "").lstrip("vV")
        notes = data.get("body") or ""
        asset = ""
        for a in data.get("assets", []):
            if (a.get("name") or "").endswith(".zip"):
                asset = a.get("browser_download_url", "")
                break
        if not asset:
            asset = data.get("zipball_url", "")
        out.update(ok=True, latest=tag, url=asset, notes=notes,
                   update_available=is_newer(tag, __version__))
    except Exception as e:
        out["error"] = str(e)
    return out


def _sha256_from_notes(notes: str) -> str:
    m = re.search(r"sha256[:=]\s*([0-9a-fA-F]{64})", notes or "")
    return m.group(1).lower() if m else ""


def install(url: str, expect_sha: str = "", app_dir: str = "",
            service: str = "ident", timeout: int = 120) -> dict:
    """Download, verify and swap in a new version. Returns {'ok', 'error'}."""
    app_dir = app_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp(prefix="ident-update-")
    try:
        zpath = os.path.join(tmp, "update.zip")
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f)

        if expect_sha:
            h = hashlib.sha256()
            with open(zpath, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != expect_sha.lower():
                return {"ok": False, "error": "Checksum mismatch - update refused"}

        stage = os.path.join(tmp, "stage")
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():                    # guard against path escapes
                p = os.path.normpath(os.path.join(stage, name))
                if not p.startswith(os.path.abspath(stage)):
                    return {"ok": False, "error": f"Unsafe path in archive: {name}"}
            z.extractall(stage)

        # find the package root inside the archive (…/ident/ident/__init__.py)
        src = ""
        for root, dirs, files in os.walk(stage):
            if os.path.basename(root) == "ident" and "__init__.py" in files \
               and "render" in dirs:
                src = os.path.dirname(root)
                break
        if not src:
            return {"ok": False, "error": "Archive did not contain an ident package"}

        # sanity-check the new code before swapping it in
        chk = subprocess.run([sys.executable, "-c",
                              "import sys;sys.path.insert(0,%r);import ident;print(ident.__version__)" % src],
                             capture_output=True, text=True, timeout=60)
        if chk.returncode != 0:
            return {"ok": False, "error": "New version failed to import: " + chk.stderr.strip()[:200]}

        backup = app_dir + ".backup"
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(os.path.join(app_dir, "ident"), os.path.join(backup, "ident"))
        for item in os.listdir(src):
            s = os.path.join(src, item); d = os.path.join(app_dir, item)
            if os.path.isdir(s):
                shutil.rmtree(d, ignore_errors=True); shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        subprocess.Popen(["sudo", "systemctl", "restart", service])
        return {"ok": True, "version": chk.stdout.strip(), "backup": backup}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
