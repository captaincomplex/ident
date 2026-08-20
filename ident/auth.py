"""Optional username/password protection for the web control panel.

Off by default: with no password set the panel behaves exactly as before, so a
fresh install on your home network needs no configuration. Set a password (from
the panel, or `python -m ident.main --set-password`) and every page then
requires a login.

Passwords are stored only as a salted PBKDF2-SHA256 hash. The session cookie is
signed with a secret key generated once and kept in the data directory.

NOTE: over plain HTTP a password crosses the network in the clear. On your own
LAN that's normally fine; if you expose the panel to the internet, put it behind
HTTPS (e.g. a Cloudflare Tunnel) rather than forwarding port 8080 directly.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets

_ITERATIONS = 120_000


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


# ---------- signing key for session cookies ----------

def secret_key() -> bytes:
    from .config import DATA_DIR
    path = os.path.join(DATA_DIR, "secret.key")
    if os.path.exists(path):
        try:
            data = open(path, "rb").read().strip()
            if data:
                return data
        except Exception:
            pass
    os.makedirs(DATA_DIR, exist_ok=True)
    key = secrets.token_bytes(32)
    with open(path, "wb") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return key


# ---------- helpers ----------

def is_enabled(cfg) -> bool:
    return bool(getattr(cfg, "auth_password_hash", ""))


def is_private_address(addr: str) -> bool:
    """True for LAN / loopback callers (used by the optional trust-LAN setting)."""
    try:
        ip = ipaddress.ip_address((addr or "").split("%")[0])
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except Exception:
        return False


def check(cfg, username: str, password: str) -> bool:
    want_user = (getattr(cfg, "auth_user", "") or "").strip()
    if want_user and (username or "").strip() != want_user:
        return False
    return verify_password(password or "", getattr(cfg, "auth_password_hash", ""))
