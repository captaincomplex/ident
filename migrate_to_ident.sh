#!/usr/bin/env bash
# Migrate a Flight Wall install (v3.x) to Ident (v4.0.0).
#
# Run on the Pi, after copying ident_4-3-0.zip to your home directory:
#     bash ~/ident_migrate/migrate_to_ident.sh
# or, if you unzipped it already:
#     bash ~/ident/migrate_to_ident.sh
#
# Safe to re-run. Does not delete your old app directory - it's left in place
# until you're happy, so you can roll back by re-enabling flightwall.service.
set -uo pipefail

USER_NAME="$(id -un)"
HOME_DIR="$HOME"
OLD_APP="$HOME_DIR/flightwall"
NEW_APP="$HOME_DIR/ident"
OLD_DATA="$HOME_DIR/.flightwall"
NEW_DATA="$HOME_DIR/.ident"
ZIP="${ZIP:-$HOME_DIR/ident_4-3-0.zip}"

say() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

say "1/7  Stopping the old service"
sudo systemctl disable --now flightwall.service 2>/dev/null && echo "   flightwall.service stopped and disabled" \
  || echo "   (no flightwall.service found - continuing)"

say "2/7  Unpacking Ident to $NEW_APP"
if [ -f "$ZIP" ]; then
  cd "$HOME_DIR" && unzip -o -q "$ZIP" && echo "   unpacked $ZIP"
else
  echo "   $ZIP not found - assuming $NEW_APP is already in place"
fi
[ -d "$NEW_APP/ident" ] || { echo "ERROR: $NEW_APP/ident missing. Copy ident_4-3-0.zip to $HOME_DIR first."; exit 1; }

say "3/7  Moving your settings, roster and logos"
if [ -d "$OLD_DATA" ] && [ ! -d "$NEW_DATA" ]; then
  mv "$OLD_DATA" "$NEW_DATA" && echo "   $OLD_DATA -> $NEW_DATA"
elif [ -d "$NEW_DATA" ]; then
  echo "   $NEW_DATA already exists - left alone"
else
  echo "   no previous data found - Ident will start fresh"
fi

say "4/7  Building the Python environment (a few minutes on a Pi Zero)"
# A venv can't be relocated - its paths are absolute - so build a fresh one.
cd "$NEW_APP"
python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q -r requirements-epaper.txt
echo "   environment ready"

say "5/7  Installing ident.service"
sudo tee /etc/systemd/system/ident.service >/dev/null <<UNIT
[Unit]
Description=Ident - flight roster display
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$NEW_APP
ExecStart=$NEW_APP/.venv/bin/python -m ident.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
sudo rm -f /etc/systemd/system/flightwall.service
sudo systemctl daemon-reload
sudo systemctl enable --now ident.service
echo "   ident.service enabled and started"

say "6/7  Renaming the Pi to 'ident'"
CUR_HOST="$(hostnamectl --static 2>/dev/null || hostname)"
if [ "$CUR_HOST" != "ident" ]; then
  sudo hostnamectl set-hostname ident
  sudo sed -i "s/\b${CUR_HOST}\b/ident/g" /etc/hosts
  echo "   hostname $CUR_HOST -> ident  (takes effect after reboot)"
else
  echo "   already 'ident'"
fi

say "7/7  Done"
cat <<NOTE

  Ident v4.0.0 is installed and running.

  Check it:      systemctl status ident.service --no-pager
  Watch logs:    journalctl -u ident.service -f
  Panel now at:  http://ident.local:8080     (after the reboot below)

  Your old app folder is still at $OLD_APP - delete it once you're happy:
      rm -rf $OLD_APP

  Reboot now to apply the new hostname:
      sudo reboot

  After rebooting, your Mac will object that the SSH key changed (expected,
  it's a new hostname). Clear the old entry and reconnect:
      ssh-keygen -R ident.local
      ssh $USER_NAME@ident.local

NOTE
