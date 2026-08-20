# Installing Ident on a Raspberry Pi (headless, e-paper only)

You don't need a monitor. The Pi is set up entirely over your network: you SSH
in to install it, and you configure it from your phone's browser. The e-ink
panel is the only display it ever drives.

**You need:** the Pi (Zero 2 W / 3 / 4 / 5), the Inky Impression 5.7" on its
40-pin header, a microSD card, and a computer with an SD slot or USB SD reader.

---

## 1. Flash the SD card (with headless settings baked in)

1. On your computer, install **Raspberry Pi Imager** (raspberrypi.com/software).
2. Insert the SD card. In Imager:
   - **Choose Device:** your Pi model.
   - **Choose OS:** *Raspberry Pi OS Lite (64-bit)* (under "Raspberry Pi OS (other)"). Lite = no desktop, which is all you need.
   - **Choose Storage:** the SD card.
3. Click **Next → Edit Settings** (the customisation dialog). This is the important part for headless setup:
   - **Set hostname:** `ident`
   - **Set username and password:** e.g. user `pilot`, and a password you'll remember.
   - **Configure wireless LAN:** your Wi-Fi SSID + password, and set the **Wi-Fi country** (GB).
   - **Set locale:** your timezone.
   - On the **Services** tab: tick **Enable SSH** → *Use password authentication*.
4. **Save**, then **Write**. When it finishes, eject the card.

## 2. First boot + find the Pi

1. Put the card in the Pi, plug the Inky in, power it on. Wait ~2 minutes for the first boot.
2. From your computer's terminal, connect by hostname:
   ```bash
   ssh pilot@ident.local
   ```
   (If `.local` doesn't resolve, find the Pi's IP in your router's device list and use `ssh pilot@192.168.x.x`.)

## 3. Enable SPI and I2C (the Inky needs both)

```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo reboot
```
Wait a minute, then SSH back in.

## 4. Install system packages

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-pip git unzip
```

## 5. Get the app onto the Pi

Copy the `ident.zip` from your computer (run this in a terminal **on your computer**, not the Pi):
```bash
scp ~/Downloads/ident.zip pilot@ident.local:~/
```
Then back **on the Pi**:
```bash
unzip ident.zip          # creates ~/ident
cd ident
```

## 6. Create a virtual environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-epaper.txt    # inky + qrcode
```
The `inky` install detects your panel automatically at runtime via `inky.auto`.

## 7. Tell it to use the e-paper output

Generate the default config, then point it at the e-paper + your style:
```bash
python -m ident.main --no-web &      # starts once to create ~/.ident/config.json
sleep 3 ; kill %1                          # stop it
nano ~/.ident/config.json
```
Set these values (the rest can stay default):
```json
"renderer": "epaper",
"epaper_style": "board_solari",
"base": "LGW",
"airline_iata": "U2",
"airline_icao": "EZY",
"ical_url": "https://calendar.google.com/calendar/ical/.../public/basic.ics"
```
Save with `Ctrl+O`, `Enter`, exit with `Ctrl+X`. (You can also change all of this later from the web panel.)

## 8. Run it and load your roster from your phone

```bash
source ~/ident/.venv/bin/activate
python -m ident.main
```
On your **phone** (same Wi-Fi), open:
```
http://ident.local:8080
```
There you can: pick the e-paper style, set the sliders (commute / walk / debrief),
choose the timezone, paste your iCal URL and tap **Pull feed now**, or upload your
eCrew PDF. Within a minute the Inky repaints with your roster. (The panel takes
~20-35 s to refresh and only repaints when something changes.)

Press `Ctrl+C` in the SSH window to stop it once you've confirmed it works.

## 9. Make it start on boot (systemd service)

```bash
sudo tee /etc/systemd/system/ident.service >/dev/null <<EOF
[Unit]
Description=Ident
After=network-online.target
Wants=network-online.target

[Service]
User=pilot
WorkingDirectory=/home/pilot/ident
ExecStart=/home/pilot/ident/.venv/bin/python -m ident.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now ident.service
```
Check it's running:
```bash
systemctl status ident.service
journalctl -u ident.service -f      # live logs; Ctrl+C to exit
```

That's it. The Pi now boots straight into the wall, repaints the Inky as your
duty progresses, and you manage everything from `http://ident.local:8080`
on your phone. No monitor ever required.

---

### Troubleshooting

- **`ident.local` won't resolve:** use the Pi's IP from your router instead.
- **Inky not detected** (`inky.auto` error): re-check SPI **and** I2C are enabled (step 3); the I2C EEPROM is what auto-detects the panel.
- **Permission errors on SPI/GPIO:** the default user is already in the `spi`, `gpio` and `i2c` groups; if you made a different user, add them with `sudo usermod -aG spi,gpio,i2c pilot` then reboot.
- **Roster won't parse from the feed:** upload the eCrew PDF in the web panel instead — that path is fully tested.
- **Change the look any time:** web panel → *Advanced → E-paper style*.

### Managing Wi-Fi from the web page (optional)

The web panel can save extra Wi-Fi networks (handy for pre-loading a crashpad or
hotel network before you travel, so the Pi joins it automatically when you arrive).
Saving a system Wi-Fi network needs admin rights, so grant the app permission once:

```
echo "$USER ALL=(root) NOPASSWD: /usr/bin/nmcli" | sudo tee /etc/sudoers.d/ident-nmcli
sudo systemctl restart ident
```

After that, the **Wi-Fi networks** card on the web page can add, list, and remove
networks. (Without this rule the card still shows, but saving returns a permission
message.) Networks must be 2.4GHz — the Pi Zero 2 W can't see 5GHz.
