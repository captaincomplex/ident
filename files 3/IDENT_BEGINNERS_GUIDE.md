# Ident — Complete Beginner's Guide

This guide builds a small screen that hangs on your wall and shows your next
flight, your current flight's progress, and your estimated time home. It assumes
you have **never written code or used a Raspberry Pi before**. If you can follow
a recipe and copy-and-paste, you can do this. Take it slowly; there's no rush and
nothing here can break your computer.

Set aside about **two hours** for the first build (most of it is waiting).

---

## Part 1 — What you're building, in plain English

A **Raspberry Pi** is a tiny, cheap computer the size of a stick of gum. It has no
screen or keyboard of its own. We'll give it instructions from your normal laptop.

An **e-paper display** (the "Inky") is a screen like a Kindle — it looks like
printed paper, uses almost no power, and holds its picture even when switched off.
It clips onto the Raspberry Pi. This is what shows your flight info on the wall.

The Pi runs a small program (the "Ident" software you've been given). The
program reads your easyJet roster, works out what to show, and draws it on the
e-paper screen. You control everything from a **web page** on your phone — no
keyboard needed once it's set up.

That's the whole thing: **a tiny computer + a paper-like screen + the program.**

---

## Part 2 — Shopping list

Prices are rough (early 2026) and will vary — check the page for the current price.
Links are UK shops since that's likely closest to you; all of these ship from the UK.

| # | What | Why you need it | Rough price | Where |
|---|------|-----------------|-------------|-------|
| 1 | **Raspberry Pi Zero 2 W — *with pre-soldered header*** | The tiny computer. "With header" means the row of pins is already attached, so **no soldering**. This is important — don't buy the plain version. | ~£20 | [Pimoroni](https://shop.pimoroni.com/products/raspberry-pi-zero-2-w) · [The Pi Hut](https://thepihut.com/products/raspberry-pi-zero-2) (choose the "with header" option) |
| 2 | **Pimoroni Inky Impression 5.7"** | The 7-colour e-paper screen with the four buttons. Clips straight onto the Pi, no soldering. | ~£70 | [Pimoroni](https://shop.pimoroni.com/products/inky-impression-5-7) |
| 3 | **Official Raspberry Pi power supply (micro-USB, 5V 2.5A)** | Powers the Pi. A phone charger *might* work but an official one avoids "not enough power" gremlins. | ~£8 | [The Pi Hut](https://thepihut.com/products/raspberry-pi-universal-power-supply) |
| 4 | **microSD card, 16–32GB (A1/A2 class)** | This is the Pi's "hard drive". 16GB is plenty. | ~£8 | [The Pi Hut](https://thepihut.com/products/sandisk-microsd-card-class-10-a1) |
| 5 | **microSD-to-USB adapter** *(only if your laptop has no SD slot)* | Lets you plug the tiny card into your laptop to set it up. | ~£6 | [The Pi Hut](https://thepihut.com/products/microsd-card-usb-reader) |

**Optional but nice:** a small desk stand or a 5×7" photo frame to mount it in,
and a short USB cable + plug if you don't already have a spare.

> **Two things people get wrong when buying:**
> 1. Get the Pi **"with header"** (pins already attached). Without it you'd need to solder.
> 2. The Pi Zero 2 W only does **2.4GHz Wi-Fi**, not 5GHz. That matters in Part 4.

---

## Part 3 — Get the software onto the memory card

The Pi needs an "operating system" (its basic software, like Windows or macOS is
for your laptop) plus our Ident program. We put the operating system on the
card first.

1. On your **laptop**, download and install **Raspberry Pi Imager** from the
   official site: <https://www.raspberrypi.com/software/>. It's a free, official app.
2. Put the microSD card into your laptop (using the USB adapter if needed).
3. Open Raspberry Pi Imager. You'll see three buttons:
   - **Choose Device** → pick *Raspberry Pi Zero 2 W*.
   - **Choose OS** → click *Raspberry Pi OS (other)* → *Raspberry Pi OS Lite (64-bit)*.
     ("Lite" means no desktop — we don't need one. Don't worry that it looks bare.)
   - **Choose Storage** → pick your SD card. **Double-check** you picked the card and
     not your laptop's own drive.
4. Click **Next**. It will ask *"Would you like to apply OS customisation settings?"*
   Click **Edit Settings**. This is the most important screen — it sets the Pi up so
   it works without a keyboard or monitor:
   - **Set hostname:** type `ident`
   - **Set username and password:** username `pilot` (or your name), and a password
     you'll remember. **Write the password down.**
   - **Configure wireless LAN:** type your home Wi-Fi **name** and **password**
     exactly (capital letters matter), and set **Wireless LAN country** to `GB`.
     Remember: it must be your **2.4GHz** network.
   - **Set locale / time zone:** `Europe/London`.
   - Click the **Services** tab at the top → tick **Enable SSH** → choose
     *Use password authentication*. ("SSH" is just the way your laptop will send
     instructions to the Pi.)
5. Click **Save**, then **Yes** to write. It takes a few minutes and will erase the
   card. When it says it's finished, take the card out.

---

## Part 4 — First switch-on

1. **Gently** push the Inky screen onto the Pi's pins (line up the 40 pins; it only
   fits one way). Hold the boards by their **edges** — the screen is glass and cracks
   if you press on it.
2. Put the microSD card into the Pi's card slot.
3. Plug the power into the Pi's **PWR IN** socket — on the Pi Zero that's the
   micro-USB socket **nearest the corner**, *not* the middle one. The middle one is
   for data and won't power it properly.
4. Wait **2–3 minutes** for it to start up the first time. A tiny green light will
   flicker — that's normal and good.

The Pi is now (hopefully) on your Wi-Fi. It has no screen output we can see yet —
we talk to it from the laptop next.

---

## Part 5 — Talk to the Pi from your laptop

We'll open a "Terminal", which is just a window where you type instructions. It
looks intimidating but you'll only copy-and-paste.

- **On a Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
- **On Windows:** click Start, type `Terminal` (or `PowerShell`), press Enter.

In that window, type this and press Enter:

```
ssh pilot@ident.local
```

(Use the username you chose if it wasn't `pilot`.)

- The first time, it asks *"Are you sure you want to continue connecting?"* — type
  `yes` and Enter.
- Then it asks for a password — type the password you set in Part 3. **The screen
  won't show anything as you type the password — no dots, no stars. That's normal.**
  Press Enter.
- When the line changes to something ending in `ident:~ $`, **you're in.** You're
  now typing instructions *to the Pi*.

> **If it can't connect** ("could not resolve hostname" or it just hangs): give the
> Pi another few minutes (first boot is slow), make sure your laptop is on the **same
> Wi-Fi**, and that you typed the Wi-Fi details correctly in Part 3. If `ident.local`
> never works, log into your home router's admin page, find the device called
> `ident`, note its IP address (like `192.168.1.81`), and use
> `ssh pilot@192.168.1.81` instead.

---

## Part 6 — Turn on the screen connection

The e-paper screen talks to the Pi over two little data channels called SPI and
I2C. We switch them on, then restart. Type these **one line at a time**, pressing
Enter after each:

```
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo reboot
```

("sudo" just means "do this as the administrator." The reboot will disconnect you —
that's expected.) Wait a minute, then reconnect with the same `ssh pilot@ident.local`.

---

## Part 7 — Install the helper software and the fonts

These commands fetch the bits the program needs. Copy-paste each line, press Enter,
and wait for it to finish before the next.

First, the system tools and — importantly — the **fonts** (without these, all the
text comes out microscopic):

```
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-pip unzip fonts-dejavu-core python3-lgpio
```

---

## Part 8 — Put the Ident program on the Pi

The program came to you as a file called `ident.zip`. We copy it from your
laptop to the Pi.

1. Open a **second** Terminal window **on your laptop** (leave the Pi one open).
   Don't type `ssh` in this one — this is your laptop.
2. Assuming the zip is in your Downloads folder, type (one line):
   ```
   scp ~/Downloads/ident.zip pilot@ident.local:~/
   ```
   Enter your Pi password when asked. This copies the file across.
3. Switch **back to the Pi Terminal** window and unpack it:
   ```
   cd ~
   unzip -o ident.zip
   cd ident
   ```

Now set up the program's own little workspace and install its parts:

```
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-epaper.txt
pip install gpiozero
```

(You'll see lots of text scroll by — that's normal. The `--system-site-packages`
bit lets the program use the button software we installed earlier.)

---

## Part 9 — Tell it to use the e-paper screen, and start it

Open the settings file in a simple editor called `nano`:

```
python -m ident.main --no-web
```

Wait about 3 seconds, then press `Ctrl + C` to stop it. (That first run just creates
the settings file.) Now edit it:

```
nano ~/.ident/config.json
```

Use the arrow keys to find these lines and change them so they read like this
(leave the others alone):

```
"renderer": "epaper",
"epaper_style": "board_solari",
"base": "LGW",
"airline_iata": "U2",
"airline_icao": "EZY",
```

Save and exit: press `Ctrl + O`, then Enter, then `Ctrl + X`.

Now run it for real:

```
python -m ident.main
```

You should see lines like `Inky detected: 600x448` and `side buttons A/B/C/D armed`.
Within a minute the screen will draw your wall. (It refreshes slowly — 20-35
seconds — that's normal for e-paper.)

---

## Part 10 — Load your roster and settings from your phone

While the program is running, on your **phone** (connected to the same Wi-Fi) open
a web browser and go to:

```
http://ident.local:8080
```

This is your control panel. From here you can, with no typing of code:

- **Roster:** upload your eCrew PDF, or paste your roster calendar (iCal) link and
  tap **Pull feed now**.
- **Add a personal flight:** type a flight number and date for a non-work trip — it
  looks up the route and times and tracks it (with a 90-minute "report" time).
- **Airline logos:** upload your easyJet logo (use code `U2`) so the boarding-pass
  style shows it; add others (e.g. `BA`) for personal flights. Use PNG images with a
  see-through background for the best look.
- **Display style:** tap a thumbnail to choose how the wall looks.
- **Timing sliders:** set your commute, walk-to-car, and debrief minutes so the
  "home" time is right for you.
- **All settings:** the section at the very bottom exposes every option if you ever
  want to fine-tune.

Once you've set it up, go back to the Pi Terminal and press `Ctrl + C` to stop the
test run. We'll now make it start by itself.

---

## Part 11 — Make it run automatically forever

Right now the wall only runs while your Terminal is open. This step makes the Pi
start it on its own every time it's powered on, so you can unplug the Terminal and
forget about it.

Copy-paste this **whole block** at once and press Enter (it writes a small startup
instruction file). If your username isn't `pilot`, change both `pilot` words:

```
sudo tee /etc/systemd/system/ident.service >/dev/null <<EOF
[Unit]
Description=Ident
After=network-online.target

[Service]
User=pilot
WorkingDirectory=/home/pilot/ident
ExecStart=/home/pilot/ident/.venv/bin/python -m ident.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

Then switch it on:

```
sudo systemctl daemon-reload
sudo systemctl enable --now ident
```

Check it's happy (press `q` to exit the view):

```
systemctl status ident
```

That's it. **You're done.** You can close everything, unplug the Pi, move it to the
wall, plug it back in, and a minute later your Ident lights up by itself. You
manage it forever from `http://ident.local:8080` on your phone.

---

## The four buttons on the screen

- **Button A** — turn the display on/off
- **Button B** — change the style (it remembers your choice)
- **Button C** — boost the colour/contrast, then back to normal
- **Button D** — show a big QR code for 5 seconds; scan it with your phone to open
  the live flight on Flightradar24

---

## If something goes wrong

- **Text is tiny:** the fonts didn't install. Run `sudo apt install -y fonts-dejavu-core`
  then `sudo systemctl restart ident`.
- **Screen says "Woah there, some pins are in use":** run this once, then reboot —
  `echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt` then `sudo reboot`.
- **Can't reach the web page:** make sure the address ends in **:8080**, and that
  your phone is on the same Wi-Fi.
- **Want to change which Wi-Fi the Pi uses:** connect with SSH and run `sudo nmtui`,
  choose *Activate a connection*, pick the new network and enter its password.
  (Remember: 2.4GHz only, and you'll briefly lose the connection while it switches.)
- **Updating to a new version later:** copy the new `ident.zip` across (Part 8
  step 2), then on the Pi: `cd ~ && unzip -o ident.zip`, then
  `find ~/ident -name __pycache__ -type d -exec rm -rf {} +`, then
  `sudo systemctl restart ident`. Check the version it prints on startup.

---

## A few honest notes

- The e-paper screen is **glass and fragile** — handle it by the edges.
- It refreshes slowly (20-35 seconds) and isn't a touchscreen — that's normal for
  this kind of display and is why it sips power and reads like paper.
- Live flight tracking and the home-drive-time estimate use online services
  (AeroDataBox, Flightradar24, Google Maps) that need free/cheap API keys — you can
  add those later in the control panel's Advanced section. The wall works fine
  without them; you just won't get the live in-air position until they're set.
- Airline logos are trademarks, so the app doesn't come with any — it simply shows
  the image files *you* upload, which is exactly what you want for your own display.
