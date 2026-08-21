"""Ident — illustrated assembly guide. Original line-art, drawn with reportlab."""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import math

W, H = A4
INK = (0.10, 0.11, 0.13)
GREY = (0.55, 0.58, 0.62)
LIGHT = (0.88, 0.89, 0.91)
ACC = (0.16, 0.60, 0.86)
RED = (0.80, 0.25, 0.25)
GREEN = (0.20, 0.60, 0.42)
PAPER = (0.98, 0.98, 0.97)

c = canvas.Canvas("/tmp/asm/ident_assembly_guide.pdf", pagesize=A4)
c.setTitle("Ident — Assembly Guide")
c.setAuthor("Ident")
c.setSubject("How to assemble your Ident roster display")


# ---------- primitives ----------
def stroke(col=INK, w=1.6):
    c.setStrokeColorRGB(*col); c.setLineWidth(w)
    c.setLineCap(1); c.setLineJoin(1)

def fill(col):
    c.setFillColorRGB(*col)

def rrect(x, y, w, h, r=4, s=INK, f=None, lw=1.6):
    stroke(s, lw)
    if f: fill(f); c.roundRect(x, y, w, h, r, stroke=1, fill=1)
    else: c.roundRect(x, y, w, h, r, stroke=1, fill=0)

def label(x, y, t, size=9.5, col=INK, font="Helvetica", align="l"):
    fill(col); c.setFont(font, size)
    if align == "c": c.drawCentredString(x, y, t)
    elif align == "r": c.drawRightString(x, y, t)
    else: c.drawString(x, y, t)

def stepnum(x, y, n, r=9, col=INK):
    stroke(col, 1.6); fill((1, 1, 1))
    c.circle(x, y, r, stroke=1, fill=1)
    fill(col); c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x, y - 3.8, str(n))

def arrow(x1, y1, x2, y2, col=ACC, w=1.8, head=5):
    stroke(col, w); c.line(x1, y1, x2, y2)
    a = math.atan2(y2 - y1, x2 - x1)
    fill(col)
    p = c.beginPath(); p.moveTo(x2, y2)
    p.lineTo(x2 - head * math.cos(a - 0.4), y2 - head * math.sin(a - 0.4))
    p.lineTo(x2 - head * math.cos(a + 0.4), y2 - head * math.sin(a + 0.4))
    p.close(); c.drawPath(p, stroke=0, fill=1)

def dashed(x1, y1, x2, y2, col=GREY):
    c.saveState(); stroke(col, 1.0); c.setDash(3, 3)
    c.line(x1, y1, x2, y2); c.restoreState()

def crossout(cx, cy, r=26):
    stroke(RED, 3.0); c.circle(cx, cy, r, stroke=1, fill=0)
    d = r * 0.707; c.line(cx - d, cy + d, cx + d, cy - d)

def tick(cx, cy, s=1.0, col=GREEN):
    stroke(col, 3.0)
    c.line(cx - 7*s, cy, cx - 2*s, cy - 6*s); c.line(cx - 2*s, cy - 6*s, cx + 8*s, cy + 7*s)


# ---------- objects ----------
def pi_board(x, y, s=1.0, pins=True):
    """Raspberry Pi Zero, top view."""
    bw, bh = 92*s, 42*s
    rrect(x, y, bw, bh, 3*s, INK, (0.93, 0.95, 0.94), 1.6)
    if pins:
        stroke(GREY, 1.0)
        for i in range(20):
            px = x + 7*s + i*(bw - 16*s)/19
            c.rect(px - 1.1*s, y + bh - 9*s, 2.2*s, 6*s, stroke=1, fill=0)
        stroke(GREY, 1.0)
        for i in range(20):
            px = x + 7*s + i*(bw - 16*s)/19
            c.rect(px - 1.1*s, y + bh - 16*s, 2.2*s, 6*s, stroke=1, fill=0)
    # SoC + connectors
    rrect(x + 34*s, y + 12*s, 16*s, 14*s, 1.5*s, GREY, None, 1.2)
    stroke(INK, 1.4)
    c.rect(x + 4*s, y + 3*s, 11*s, 6*s, stroke=1, fill=0)      # PWR micro-usb
    c.rect(x + 22*s, y + 3*s, 11*s, 6*s, stroke=1, fill=0)     # DATA micro-usb
    c.rect(x + bw - 20*s, y + 2*s, 14*s, 5*s, stroke=1, fill=0)  # sd slot
    return bw, bh

def display(x, y, s=1.0, screen_text=True, buttons=True):
    """Inky Impression panel, front view."""
    bw, bh = 120*s, 78*s
    rrect(x, y, bw, bh, 4*s, INK, (0.97, 0.97, 0.96), 1.8)
    rrect(x + 7*s, y + 7*s, bw - 14*s, bh - 20*s, 2*s, GREY, (1, 1, 1), 1.2)
    if buttons:
        stroke(INK, 1.4)
        for i in range(4):
            c.circle(x + 4*s, y + bh - 16*s - i*13*s, 2.6*s, stroke=1, fill=0)
    if screen_text:
        fill((0.35, 0.37, 0.40)); c.setFont("Helvetica-Bold", 9*s)
        c.drawString(x + 13*s, y + bh - 24*s, "LGW-CPH")
        c.setFont("Helvetica", 5.6*s)
        c.drawString(x + 13*s, y + bh - 33*s, "LANDS 09:05")
        c.drawString(x + 13*s, y + bh - 41*s, "HOME  12:20")
    return bw, bh

def sd_card(x, y, s=1.0):
    p = c.beginPath()
    p.moveTo(x, y); p.lineTo(x + 13*s, y); p.lineTo(x + 13*s, y + 17*s)
    p.lineTo(x + 4*s, y + 17*s); p.lineTo(x, y + 12*s); p.close()
    stroke(INK, 1.5); fill((0.95, 0.95, 0.93)); c.drawPath(p, stroke=1, fill=1)
    stroke(GREY, 0.9)
    for i in range(4): c.line(x + 3*s + i*2.6*s, y + 2*s, x + 3*s + i*2.6*s, y + 6*s)

def psu(x, y, s=1.0):
    rrect(x, y, 26*s, 20*s, 3*s, INK, (0.95, 0.95, 0.94), 1.5)
    stroke(INK, 1.4)
    c.line(x + 8*s, y + 20*s, x + 8*s, y + 26*s); c.line(x + 18*s, y + 20*s, x + 18*s, y + 26*s)
    stroke(INK, 1.5)
    p = c.beginPath(); p.moveTo(x + 26*s, y + 8*s)
    p.curveTo(x + 46*s, y + 8*s, x + 40*s, y - 12*s, x + 60*s, y - 8*s)
    c.drawPath(p, stroke=1, fill=0)
    c.rect(x + 60*s, y - 12*s, 9*s, 7*s, stroke=1, fill=0)

def phone(x, y, s=1.0):
    rrect(x, y, 30*s, 56*s, 4*s, INK, (1, 1, 1), 1.6)
    rrect(x + 3*s, y + 6*s, 24*s, 44*s, 1.5*s, LIGHT, None, 0.9)
    stroke(GREY, 1.2); c.line(x + 11*s, y + 3.5*s, x + 19*s, y + 3.5*s)

def laptop(x, y, s=1.0):
    rrect(x, y + 10*s, 58*s, 36*s, 2.5*s, INK, (1, 1, 1), 1.6)
    rrect(x + 4*s, y + 14*s, 50*s, 28*s, 1.2*s, LIGHT, None, 0.9)
    stroke(INK, 1.6)
    p = c.beginPath(); p.moveTo(x - 6*s, y); p.lineTo(x + 64*s, y)
    p.lineTo(x + 58*s, y + 10*s); p.lineTo(x, y + 10*s); p.close()
    fill((0.96, 0.96, 0.95)); c.drawPath(p, stroke=1, fill=1)

def clockface(x, y, r=13, mins=3):
    stroke(INK, 1.6); fill((1, 1, 1)); c.circle(x, y, r, stroke=1, fill=1)
    stroke(INK, 1.8); c.line(x, y, x, y + r*0.6)
    a = math.radians(90 - mins*30)
    c.line(x, y, x + r*0.75*math.cos(a), y + r*0.75*math.sin(a))

def wifi(x, y, s=1.0, bars=3, col=INK):
    stroke(col, 1.8)
    for i in range(1, bars+1):
        r = 6*i*s
        c.arc(x - r, y - r, x + r, y + r, 45, 90)
    fill(col); c.circle(x, y, 1.8*s, stroke=0, fill=1)


# ---------- page furniture ----------
def page_header(title, n, total):
    fill(INK); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(20*mm, H - 15*mm, "IDENT")
    fill(GREY); c.setFont("Helvetica", 8.5)
    c.drawRightString(W - 20*mm, H - 15*mm, f"{n} / {total}")
    stroke(LIGHT, 1.0); c.line(20*mm, H - 18*mm, W - 20*mm, H - 18*mm)
    if title:
        fill(INK); c.setFont("Helvetica-Bold", 15)
        c.drawString(20*mm, H - 30*mm, title)

def footer(note=""):
    stroke(LIGHT, 1.0); c.line(20*mm, 18*mm, W - 20*mm, 18*mm)
    fill(GREY); c.setFont("Helvetica", 7.5)
    c.drawString(20*mm, 13*mm, note or "ident.xpdr.aero")
    c.drawRightString(W - 20*mm, 13*mm, "Correct as of version 4.3.0")

TOTAL = 8

# ============================== PAGE 1 — COVER ==============================
fill(PAPER); c.rect(0, 0, W, H, stroke=0, fill=1)
fill(INK); c.setFont("Helvetica-Bold", 42)
c.drawString(20*mm, H - 55*mm, "IDENT")
fill(GREY); c.setFont("Helvetica", 13)
c.drawString(20*mm, H - 65*mm, "Assembly guide")
stroke(ACC, 2.5); c.line(20*mm, H - 72*mm, 62*mm, H - 72*mm)

# hero: assembled unit on a stand
cx, cy = W/2 - 60*mm, H/2 - 30*mm
display(cx, cy, 1.5)
stroke(INK, 1.8)
c.line(cx + 60*mm*0.55, cy, cx + 60*mm*0.55, cy - 12*mm)
c.line(cx + 30*mm, cy - 12*mm, cx + 90*mm*0.75, cy - 12*mm)

fill(GREY); c.setFont("Helvetica", 10)
c.drawString(20*mm, 44*mm, "No soldering. No special tools.")
c.drawString(20*mm, 38*mm, "About an hour, most of it waiting.")
fill(INK); c.setFont("Helvetica-Bold", 10)
c.drawString(20*mm, 30*mm, "ident.xpdr.aero")
footer("Read pages 2 and 3 before you start")
c.showPage()

# ============================== PAGE 2 — PARTS ==============================
page_header("What's in front of you", 2, TOTAL)
fill(GREY); c.setFont("Helvetica", 9.5)
c.drawString(20*mm, H - 38*mm, "Lay everything out and check it off. Nothing here is supplied by us — you bought it yourself.")

col1, col2 = 28*mm, 115*mm
row = H - 62*mm
display(col1, row - 6*mm, 0.62, screen_text=False)
label(col1 + 56*mm, row + 34*mm, "Inky Impression display", 10.5, INK, "Helvetica-Bold")
label(col1 + 56*mm, row + 27*mm, "7.3\" recommended. 4.0\" and 13.3\"", 9, GREY)
label(col1 + 56*mm, row + 21*mm, "also work. Glass — handle by the edges.", 9, GREY)
label(col1 + 56*mm, row + 12*mm, "x 1", 9.5, INK, "Helvetica-Bold")

row -= 52*mm
pi_board(col1, row + 6*mm, 0.62)
label(col1 + 56*mm, row + 22*mm, "Raspberry Pi Zero 2 W", 10.5, INK, "Helvetica-Bold")
label(col1 + 56*mm, row + 15*mm, "Must be the version WITH header pins", 9, GREY)
label(col1 + 56*mm, row + 9*mm, "already fitted (\"WH\").", 9, GREY)
label(col1 + 56*mm, row + 0*mm, "x 1", 9.5, INK, "Helvetica-Bold")

row -= 42*mm
sd_card(col1 + 8*mm, row + 4*mm, 1.1)
label(col1 + 56*mm, row + 18*mm, "microSD card", 10.5, INK, "Helvetica-Bold")
label(col1 + 56*mm, row + 11*mm, "16-32GB. You'll also need a way to", 9, GREY)
label(col1 + 56*mm, row + 5*mm, "plug it into your computer.", 9, GREY)
label(col1 + 56*mm, row - 4*mm, "x 1", 9.5, INK, "Helvetica-Bold")

row -= 40*mm
psu(col1 + 4*mm, row + 12*mm, 1.0)
label(col1 + 56*mm, row + 20*mm, "Power supply", 10.5, INK, "Helvetica-Bold")
label(col1 + 56*mm, row + 13*mm, "Micro-USB for a Pi Zero. A Pi 4 or 5", 9, GREY)
label(col1 + 56*mm, row + 7*mm, "needs USB-C instead.", 9, GREY)
label(col1 + 56*mm, row - 2*mm, "x 1", 9.5, INK, "Helvetica-Bold")

rrect(20*mm, 26*mm, W - 40*mm, 22*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
label(26*mm, 40*mm, "Tools needed", 10, INK, "Helvetica-Bold")
label(26*mm, 33*mm, "None. If you find yourself reaching for a screwdriver or a soldering iron, stop and check the parts list.", 9, GREY)
footer()
c.showPage()

# ============================== PAGE 3 — DO / DON'T ==============================
page_header("Before you start", 3, TOTAL)

# DON'T: press on the glass
bx, by = 30*mm, H - 105*mm
display(bx, by, 0.62, screen_text=False, buttons=False)
stroke(INK, 1.6)
c.circle(bx + 38*mm, by + 26*mm, 5*mm, stroke=1, fill=0)
arrow(bx + 38*mm, by + 44*mm, bx + 38*mm, by + 32*mm, RED, 2.0, 5)
crossout(bx + 38*mm, by + 26*mm, 20*mm)
label(bx, by - 8*mm, "Don't press on the screen.", 10, RED, "Helvetica-Bold")
label(bx, by - 14*mm, "It is glass and it will crack.", 9, GREY)
label(bx, by - 20*mm, "Hold both boards by their edges.", 9, GREY)

# DO: hold by edges
bx2 = 115*mm
display(bx2, by, 0.62, screen_text=False, buttons=False)
stroke(INK, 1.6)
c.roundRect(bx2 - 5*mm, by + 14*mm, 8*mm, 14*mm, 3*mm, stroke=1, fill=0)
c.roundRect(bx2 + 41*mm, by + 14*mm, 8*mm, 14*mm, 3*mm, stroke=1, fill=0)
tick(bx2 + 20*mm, by + 50*mm, 1.6)
label(bx2, by - 8*mm, "Hold it like this.", 10, GREEN, "Helvetica-Bold")
label(bx2, by - 14*mm, "Edges only, both hands.", 9, GREY)

# 2.4GHz warning
wy = 62*mm
rrect(20*mm, wy, W - 40*mm, 46*mm, 4, RED, (1.0, 0.97, 0.96), 1.4)
wifi(42*mm, wy + 26*mm, 1.0, 3, RED)
crossout(42*mm, wy + 26*mm, 14*mm)
label(64*mm, wy + 34*mm, "Check your Wi-Fi first", 11, RED, "Helvetica-Bold")
label(64*mm, wy + 26*mm, "The Pi Zero 2 W cannot see 5GHz networks. Only 2.4GHz.", 9.5, INK)
label(64*mm, wy + 19*mm, "If your router only broadcasts 5GHz, or hides both bands behind one", 9, GREY)
label(64*mm, wy + 13*mm, "name and pushes devices onto 5GHz, this build will not connect —", 9, GREY)
label(64*mm, wy + 7*mm, "and no amount of setting up will fix it. Turn 2.4GHz on first.", 9, GREY)
footer()
c.showPage()

# ============================== PAGE 4 — STEP 1: CARD ==============================
page_header("", 4, TOTAL)
stepnum(24*mm, H - 32*mm, 1, 10)
label(34*mm, H - 35.5*mm, "Prepare the memory card", 15, INK, "Helvetica-Bold")
label(34*mm, H - 43*mm, "On your computer, not the Pi.", 9.5, GREY)

laptop(35*mm, H - 105*mm, 1.5)
sd_card(140*mm, H - 96*mm, 1.4)
arrow(132*mm, H - 88*mm, 108*mm, H - 88*mm, ACC, 2.0, 6)
label(35*mm, H - 118*mm, "Install Raspberry Pi Imager, choose your Pi model,", 9.5, INK)
label(35*mm, H - 125*mm, "and pick Raspberry Pi OS Lite (64-bit).", 9.5, INK)

by = H - 196*mm
rrect(20*mm, by, W - 40*mm, 66*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
label(26*mm, by + 57*mm, "In Imager, click Edit Settings and fill in all of this:", 10, INK, "Helvetica-Bold")
items = [("Hostname", "ident"),
         ("Username", "pilot  (and a password you write down)"),
         ("Wi-Fi", "your 2.4GHz network name and password, country GB"),
         ("Time zone", "Europe/London"),
         ("Services tab", "tick Enable SSH, password authentication")]
yy = by + 47*mm
for k, v in items:
    fill(ACC); c.circle(29*mm, yy + 1.2*mm, 1.4*mm, stroke=0, fill=1)
    label(34*mm, yy, k, 9.5, INK, "Helvetica-Bold")
    label(66*mm, yy, v, 9.5, GREY)
    yy -= 8*mm
label(26*mm, by + 5*mm, "Then Save, Write, and wait. This erases the card.", 9, GREY)
footer()
c.showPage()

# ============================== PAGE 5 — STEP 2: FIT ==============================
page_header("", 5, TOTAL)
stepnum(24*mm, H - 32*mm, 2, 10)
label(34*mm, H - 35.5*mm, "Fit the display to the Pi", 15, INK, "Helvetica-Bold")
label(34*mm, H - 43*mm, "Power off. Line up the pins. Press straight down.", 9.5, GREY)

# exploded view
dx, dy = 55*mm, H - 92*mm
display(dx, dy, 0.95, screen_text=False)
pi_board(dx + 12*mm, dy - 34*mm, 0.95)
for off in (16*mm, 27*mm, 38*mm):
    dashed(dx + off, dy - 2*mm, dx + off, dy - 20*mm)
arrow(dx + 66*mm, dy - 22*mm, dx + 46*mm, dy - 22*mm, ACC, 2.0, 5)
label(dx + 69*mm, dy - 21*mm, "all 40 pins engaged", 8.5, ACC, "Helvetica-Bold")
label(dx + 69*mm, dy - 27*mm, "no pin left over at either end", 8, GREY)

by = H - 192*mm
rrect(20*mm, by, 80*mm, 48*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
tick(30*mm, by + 38*mm, 1.2)
label(38*mm, by + 36*mm, "Right", 10, GREEN, "Helvetica-Bold")
label(26*mm, by + 27*mm, "Every pin in its socket.", 9, GREY)
label(26*mm, by + 20*mm, "Boards parallel, no gap at", 9, GREY)
label(26*mm, by + 13*mm, "one end. Pressed home evenly.", 9, GREY)

rrect(110*mm, by, 80*mm, 48*mm, 4, LIGHT, (1.0, 0.98, 0.97), 1.2)
crossout(120*mm, by + 37*mm, 6*mm)
label(130*mm, by + 36*mm, "Wrong", 10, RED, "Helvetica-Bold")
label(116*mm, by + 27*mm, "Offset by one row, or one", 9, GREY)
label(116*mm, by + 20*mm, "pin hanging over the end.", 9, GREY)
label(116*mm, by + 13*mm, "Check both ends before pressing.", 9, GREY)

label(20*mm, by - 12*mm, "If the kit came with standoffs, use those screws — longer ones can crack the glass.", 9, GREY)
footer()
c.showPage()

# ============================== PAGE 6 — STEP 3: POWER ==============================
page_header("", 6, TOTAL)
stepnum(24*mm, H - 32*mm, 3, 10)
label(34*mm, H - 35.5*mm, "Card in, power on", 15, INK, "Helvetica-Bold")
label(34*mm, H - 43*mm, "The two sockets look identical. Only one of them works.", 9.5, GREY)

px, py = 50*mm, H - 100*mm
bw, bh = pi_board(px, py, 1.5)
sd_card(px + bw - 22*mm, py + bh + 10*mm, 1.0)
arrow(px + bw - 18*mm, py + bh + 8*mm, px + bw - 18*mm, py + bh - 1*mm, ACC, 2.0, 5)
label(px + bw - 12*mm, py + bh + 14*mm, "card in, contacts down", 8.5, ACC)

# correct / wrong ports
cxp = px + 6*mm*1.5
arrow(cxp, py - 22*mm, cxp, py - 4*mm, GREEN, 2.2, 6)
label(cxp - 16*mm, py - 28*mm, "PWR IN — use this one", 9, GREEN, "Helvetica-Bold")
wxp = px + 27*mm*1.5
crossout(wxp, py + 4*mm, 8*mm)
label(wxp + 12*mm, py - 6*mm, "the middle socket is", 9, RED)
label(wxp + 12*mm, py - 12*mm, "data only — it will not", 9, RED)
label(wxp + 12*mm, py - 18*mm, "power the Pi properly", 9, RED)

by = H - 178*mm
rrect(20*mm, by, W - 40*mm, 44*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
clockface(38*mm, by + 24*mm, 12)
label(58*mm, by + 30*mm, "Now wait 2 to 3 minutes.", 10.5, INK, "Helvetica-Bold")
label(58*mm, by + 21*mm, "The first start-up is slow. A small green light will flicker — that is normal", 9, GREY)
label(58*mm, by + 15*mm, "and means it is working. The screen stays blank for now.", 9, GREY)
label(58*mm, by + 6*mm, "Nothing on the display yet? That is expected at this stage.", 9, GREY)
footer()
c.showPage()

# ============================== PAGE 7 — STEP 4: SETUP ==============================
page_header("", 7, TOTAL)
stepnum(24*mm, H - 32*mm, 4, 10)
label(34*mm, H - 35.5*mm, "Set it up from your phone", 15, INK, "Helvetica-Bold")
label(34*mm, H - 43*mm, "Same Wi-Fi as the display. No cables, no typing of code.", 9.5, GREY)

ph = 62*mm
phone(ph, H - 118*mm, 1.45)
fill(INK); c.setFont("Helvetica-Bold", 7)
c.drawString(ph + 7*mm, H - 76*mm, "Set up your display")
fill(GREY); c.setFont("Helvetica", 5.5)
for i, t in enumerate(["Display name", "Home base", "Airline code", "Roster calendar URL", "Password"]):
    c.drawString(ph + 7*mm, H - 82*mm - i*7*mm, t)
    stroke(LIGHT, 0.8); c.rect(ph + 7*mm, H - 85*mm - i*7*mm, 26*mm, 2.6*mm, stroke=1, fill=0)
fill(ACC); c.roundRect(ph + 7*mm, H - 116*mm, 26*mm, 5*mm, 1.2, stroke=0, fill=1)
fill((1,1,1)); c.setFont("Helvetica-Bold", 5.5)
c.drawCentredString(ph + 20*mm, H - 114.5*mm, "Finish setup")

label(115*mm, H - 72*mm, "In any browser, go to:", 9.5, GREY)
fill(INK); c.setFont("Courier-Bold", 12)
c.drawString(115*mm, H - 81*mm, "ident.local:8080")
label(115*mm, H - 92*mm, "The first time, you get a setup page.", 9.5, INK)
label(115*mm, H - 99*mm, "Fill it in and press Finish.", 9.5, INK)
label(115*mm, H - 111*mm, "Can't reach it? Find the device's IP", 9, GREY)
label(115*mm, H - 117*mm, "in your router's device list and use", 9, GREY)
label(115*mm, H - 123*mm, "that instead, with :8080 on the end.", 9, GREY)

by = H - 190*mm
rrect(20*mm, by, W - 40*mm, 52*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
label(26*mm, by + 43*mm, "What to enter", 10, INK, "Helvetica-Bold")
rows = [("Display name", "Anything. \"Kitchen\". Useful if you build a second one."),
        ("Home base", "Your base airport code, e.g. LGW."),
        ("Airline code", "Two letters, e.g. U2."),
        ("Roster calendar", "Your crew .ics link. Can be left blank and added later."),
        ("Password", "Locks the control panel. Leave blank for no login.")]
yy = by + 34*mm
for k, v in rows:
    fill(ACC); c.circle(29*mm, yy + 1.2*mm, 1.4*mm, stroke=0, fill=1)
    label(34*mm, yy, k, 9.5, INK, "Helvetica-Bold")
    label(72*mm, yy, v, 9.5, GREY)
    yy -= 7.5*mm
footer()
c.showPage()

# ============================== PAGE 8 — DONE ==============================
page_header("Done", 8, TOTAL)

dx, dy = 58*mm, H - 112*mm
display(dx, dy, 1.15)
tick(dx + 106*mm, dy + 66*mm, 2.0)
label(20*mm, H - 128*mm, "Within a minute or two the screen draws your duty. It takes about 30 seconds to redraw —", 9.5, GREY)
label(20*mm, H - 135*mm, "that is how colour e-paper works, and it is why the display uses almost no power.", 9.5, GREY)

by = H - 176*mm
rrect(20*mm, by - 8*mm, 80*mm, 42*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
label(26*mm, by + 25*mm, "The four buttons", 10, INK, "Helvetica-Bold")
for i, t in enumerate(["A  on / off", "B  change style", "C  contrast", "D  next duty"]):
    label(26*mm, by + 17*mm - i*7*mm, t, 9, GREY)

rrect(110*mm, by - 8*mm, 80*mm, 42*mm, 4, LIGHT, (0.99, 0.99, 0.98), 1.2)
label(116*mm, by + 25*mm, "If it shows the wrong day", 10, INK, "Helvetica-Bold")
label(116*mm, by + 17*mm, "It has lost Wi-Fi. The Pi has no", 9, GREY)
label(116*mm, by + 11*mm, "battery clock, so it freezes on the", 9, GREY)
label(116*mm, by + 5*mm, "last date it knew. Reconnect it.", 9, GREY)

fill(INK); c.setFont("Helvetica-Bold", 11)
c.drawString(20*mm, 46*mm, "Stuck?")
fill(GREY); c.setFont("Helvetica", 9.5)
c.drawString(20*mm, 39*mm, "Every question we get asked is answered at ident.xpdr.aero/faq")
c.drawString(20*mm, 32*mm, "If yours isn't there, the support form is at ident.xpdr.aero/support")
footer()
c.save()
print("PDF written")
