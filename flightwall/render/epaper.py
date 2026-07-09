"""E-paper rendering: a registry of selectable styles + an Inky panel renderer.

Every style is a function (w, h, ctx) -> RGB PIL image, drawn for a 7-colour
ACeP panel and then dithered to that palette. The app exposes STYLE_LABELS so a
user can choose between them; the daemon's InkyRenderer pushes the chosen style.
"""
from __future__ import annotations

import math
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .base import Renderer
from .presenter import Screen
from . import font5x7

# muted 7-colour ACeP palette (also used as exact fills -> crisp, no dithering)
BLACK=(22,22,24); WHITE=(236,234,224); RED=(170,55,50); GREEN=(70,118,76)
BLUE=(52,82,140); YELLOW=(208,178,74); ORANGE=(202,112,52)
PAL=[*BLACK,*WHITE,*RED,*GREEN,*BLUE,*YELLOW,*ORANGE]
AMBER=ORANGE
APT={"LGW":"GATWICK","SKG":"THESSALONIKI","MUC":"MUNICH","CFU":"CORFU","NAP":"NAPLES",
     "LJU":"LJUBLJANA","CPH":"COPENHAGEN","MXP":"MILAN","BER":"BERLIN","DBV":"DUBROVNIK",
     "JER":"JERSEY","SVQ":"SEVILLE","NBE":"ENFIDHA"}

import os as _os
_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
              "/usr/share/fonts/TTF", "/usr/share/fonts/truetype",
              "/Library/Fonts", "/System/Library/Fonts"]
_FONT_WARNED = False

def _font_file(name):
    for d in _FONT_DIRS:
        p = _os.path.join(d, name)
        if _os.path.exists(p):
            return p
    return name

def _ttf(px, bold=True, mono=False):
    global _FONT_WARNED
    name = ("DejaVuSansMono-Bold.ttf" if (mono and bold) else "DejaVuSansMono.ttf" if mono
            else "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    for cand in (name, _font_file(name)):
        try:
            return ImageFont.truetype(cand, px)
        except Exception:
            continue
    if not _FONT_WARNED:
        print("[flightwall] WARNING: DejaVu fonts not found - text will be tiny. "
              "Fix with:  sudo apt install -y fonts-dejavu-core")
        _FONT_WARNED = True
    return ImageFont.load_default()

def _tl(d,s,f): return d.textlength(s,font=f)

def make_qr(url, module=3, quiet=4):
    """Real QR via the qrcode lib (Pi) or OpenCV (fallback); else a placeholder."""
    matrix=None
    try:
        import qrcode
        q=qrcode.QRCode(border=0); q.add_data(url); q.make(fit=True)
        m=q.get_matrix(); matrix=[[1 if v else 0 for v in row] for row in m]
    except Exception:
        try:
            import cv2, numpy as np
            enc=cv2.QRCodeEncoder_create(); arr=enc.encode(url)
            matrix=[[1 if arr[r,c]==0 else 0 for c in range(arr.shape[1])]
                    for r in range(arr.shape[0])]
        except Exception:
            matrix=None
    if matrix is None:
        img=Image.new("RGB",(99,99),WHITE); d=ImageDraw.Draw(img)
        d.rectangle([0,0,98,98],outline=BLACK,width=3); return img
    n=len(matrix); size=(n+2*quiet)*module
    img=Image.new("RGB",(size,size),WHITE); d=ImageDraw.Draw(img)
    for r in range(n):
        for c in range(n):
            if matrix[r][c]:
                x=(c+quiet)*module; y=(r+quiet)*module
                d.rectangle([x,y,x+module-1,y+module-1],fill=BLACK)
    return img

def _dot_text(text, color, module=4, gap=1):
    """Render text in the 5x7 LED font as discrete dots (airport-sign look)."""
    w=font5x7.width(text); buf=Image.new("RGB",(w,7),(0,0,0))
    font5x7.blit(buf,0,0,text,(1,1,1))
    cell=module+gap; img=Image.new("RGB",(w*cell, 7*cell),(0,0,0)); d=ImageDraw.Draw(img)
    for y in range(7):
        for x in range(w):
            on=buf.getpixel((x,y))!=(0,0,0)
            cx,cy=x*cell+cell/2, y*cell+cell/2; rr=module*0.46
            d.ellipse([cx-rr,cy-rr,cx+rr,cy+rr], fill=color if on else (28,24,18))
    return img


# ============================ STYLES ============================

def _boarding(w,h,c):
    img=Image.new("RGB",(w,h),WHITE); d=ImageDraw.Draw(img)
    d.rectangle([0,0,w,64],fill=ORANGE)
    logo=_load_logo(c.get("logo_code") or "U2", 40)
    if logo is not None:
        pw=logo.size[0]+16
        d.rounded_rectangle([16,12,16+pw,52],radius=6,fill=WHITE)
        img.paste(logo,(24,16))
    else:
        d.text((20,18),"easyJet",font=_ttf(34),fill=WHITE)
    st=c["header"] or "DUTY"
    d.text((w-20-_tl(d,st,_ttf(20)),22),st,font=_ttf(20),fill=WHITE)
    perf=430
    for y in range(72,h-26,16): d.line([(perf,y),(perf,y+8)],fill=BLACK,width=2)
    d.text((20,82),"FLIGHT",font=_ttf(16),fill=RED)
    d.text((20,102),c["fid"] or "--",font=_ttf(70),fill=BLACK)
    d.text((20,186),APT.get(c["dep"],c["dep"]),font=_ttf(22),fill=BLACK)
    d.text((20,212),"to "+APT.get(c["arr"],c["arr"]),font=_ttf(22),fill=BLACK)
    def fld(x,y,lab,val,col=BLACK):
        d.text((x,y),lab,font=_ttf(15),fill=GREEN); d.text((x,y+18),val,font=_ttf(36),fill=col)
    fld(20,262,"FROM",c["dep"]); fld(150,262,"TO",c["arr"])
    fld(20,332,"LANDS",c["land"] or "--:--"); fld(220,332,"HOME",c["home"] or "--:--",RED)
    # stub: flight, route, QR only (no 'BOARDING', no text under QR)
    d.text((perf+20,86),c["fid"] or "--",font=_ttf(30),fill=BLACK)
    d.text((perf+20,124),c["route"] or "",font=_ttf(22),fill=BLUE)
    if c["fr24_url"]:
        qr=make_qr(c["fr24_url"],module=3,quiet=4)
        qx=perf+20+max(0,((w-16-(perf+20))-qr.size[0])//2)
        img.paste(qr,(qx,168))
    # progress bar along the very bottom (full width)
    by=h-16; d.rectangle([0,by,w,h],fill=(206,200,186))
    d.rectangle([0,by,int(w*c["prog"]),h],fill=ORANGE)
    return img

def _load_logo(code, h):
    """Load a user-supplied airline logo (<data>/logos/<IATA>.png), on white.

    Real airline logos are trademarks, so none are bundled - the app shows
    whatever image you drop in the logos folder; otherwise a text badge.
    """
    import os
    if not code:
        return None
    data_dir = os.path.expanduser(os.environ.get("FLIGHTWALL_DATA", "~/.flightwall"))
    for ext in ("png", "PNG", "jpg", "jpeg"):
        p = os.path.join(data_dir, "logos", f"{code.upper()}.{ext}")
        if os.path.exists(p):
            try:
                logo = Image.open(p)
                if logo.mode in ("RGBA", "LA", "P"):
                    logo = logo.convert("RGBA")
                    bg = Image.new("RGBA", logo.size, (255, 255, 255, 255))
                    logo = Image.alpha_composite(bg, logo).convert("RGB")
                else:
                    logo = logo.convert("RGB")
                s = h / logo.size[1]
                return logo.resize((max(1, int(logo.size[0]*s)), h), Image.LANCZOS)
            except Exception:
                return None
    return None

def _airline_badge(img, x_right, y, code, h=44):
    """Airline logo on a white plate, else a text badge (top-right)."""
    d = ImageDraw.Draw(img)
    logo = _load_logo(code, h-8)
    if logo is not None:
        pw = logo.size[0] + 16
        d.rounded_rectangle([x_right-pw, y, x_right, y+h], radius=6, fill=WHITE)
        img.paste(logo, (x_right-pw+8, y+4)); return
    f = _ttf(int(h*0.6), mono=True); tw = _tl(d, code.upper(), f) + 24
    d.rounded_rectangle([x_right-tw, y, x_right, y+h], radius=6, outline=WHITE, width=2)
    d.text((x_right-tw+12, y+int(h*0.18)), code.upper(), font=f, fill=WHITE)

def _board_solari(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((24,22),c["title"].upper()[:16],font=_ttf(34,mono=True),fill=YELLOW)
    if c.get("personal") and c.get("airline"):
        _airline_badge(img, w-24, 22, c["airline"], h=44)
    elif c.get("date") and c["state"] in ("IN_FLIGHT","PRE_FLIGHT","TURNAROUND","POST_DUTY"):
        ds=c["date"]; d.text((w-24-_tl(d,ds,_ttf(20,mono=True)),34),ds,font=_ttf(20,mono=True),fill=(150,140,90))
    d.line([(24,72),(w-24,72)],fill=ORANGE,width=3)
    hero=c["hero"] or ""
    hf=_ttf(116 if len(hero)<=7 else 90 if len(hero)<=9 else 64,mono=True)
    d.text((24,86),hero,font=hf,fill=WHITE)
    if c["sub"]: d.text((26,212),c["sub"][:22],font=_ttf(38,mono=True),fill=(205,205,195))
    y=276
    for lab,val in (c["rows"] or [])[:2]:
        if not (lab or val): continue
        d.text((24,y+18),lab,font=_ttf(26,mono=True),fill=(150,140,90))
        vc=YELLOW if lab in ("LANDS","NEXT DEP","REPORT") else WHITE
        d.text((250,y),val,font=_ttf(62 if len(val)<=6 else 40,mono=True),fill=vc)
        y+=80
    if c.get("in_flight"):
        by=h-30; d.rectangle([24,by,w-24,by+16],outline=(110,95,45),width=2)
        d.rectangle([26,by+2,26+int((w-52)*c["prog"]),by+14],fill=ORANGE)
    return img

def _board_yellow(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((24,22),c["title"].upper()[:16],font=_ttf(32,mono=True),fill=(150,140,60))
    d.line([(24,66),(w-24,66)],fill=(120,108,30),width=2)
    hero=c["hero"] or ""; hf=_ttf(120 if len(hero)<=7 else 88,mono=True)
    d.text((24,80),hero,font=hf,fill=YELLOW)
    if c["sub"]: d.text((26,210),c["sub"][:22],font=_ttf(40,mono=True),fill=(190,170,70))
    y=280
    for lab,val in (c["rows"] or [])[:2]:
        if not (lab or val): continue
        d.text((24,y+16),lab,font=_ttf(26,mono=True),fill=(140,128,55))
        d.text((250,y),val,font=_ttf(60 if len(val)<=6 else 38,mono=True),fill=YELLOW); y+=78
    if c.get("in_flight"):
        by=h-34; d.rectangle([24,by,w-24,by+18],outline=(120,108,40),width=2)
        d.rectangle([26,by+2,26+int((w-52)*c["prog"]),by+16],fill=YELLOW)
    return img

def _board_rail(w,h,c):
    img=Image.new("RGB",(w,h),BLUE); d=ImageDraw.Draw(img)
    d.rectangle([0,0,w,66],fill=(30,48,88))
    d.text((24,18),c["title"].upper()[:18],font=_ttf(34,mono=True),fill=WHITE)
    hero=c["hero"] or ""; hf=_ttf(118 if len(hero)<=7 else 88,mono=True)
    d.text((24,86),hero,font=hf,fill=WHITE)
    if c["sub"]: d.text((26,214),c["sub"][:22],font=_ttf(40,mono=True),fill=(205,218,240))
    y=284
    for lab,val in (c["rows"] or [])[:2]:
        if not (lab or val): continue
        d.text((24,y+16),lab,font=_ttf(26,mono=True),fill=(170,190,225))
        vc=YELLOW if lab in ("LANDS","NEXT DEP","REPORT") else WHITE
        d.text((250,y),val,font=_ttf(60 if len(val)<=6 else 38,mono=True),fill=vc); y+=78
    if c.get("in_flight"):
        by=h-32; d.rectangle([24,by,w-24,by+16],fill=(40,60,108))
        d.rectangle([24,by,24+int((w-48)*c["prog"]),by+16],fill=WHITE)
    return img

def _flip_card(d,x,y,cw,ch,label,value):
    d.rounded_rectangle([x,y,x+cw,y+ch],radius=10,fill=(34,34,38))
    d.rectangle([x+4,y+4,x+cw-4,y+ch//2],fill=(44,44,49))
    d.rectangle([x+4,y+ch//2+1,x+cw-4,y+ch-4],fill=(30,30,34))
    d.line([x+4,y+ch//2,x+cw-4,y+ch//2],fill=(12,12,14),width=3)
    f=_ttf(86,mono=True); tb=d.textbbox((0,0),value,font=f)
    d.text((x+(cw-(tb[2]-tb[0]))/2-tb[0], y+(ch-(tb[3]-tb[1]))/2-tb[1]),value,font=f,fill=WHITE)
    d.text((x+12,y+ch+8),label,font=_ttf(22,mono=True),fill=AMBER)

def _board_flip(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((24,20),c["title"].upper()[:18],font=_ttf(30,mono=True),fill=AMBER)
    head=(c["hero"] or "")
    if c["sub"] and len(head)<=7: head=head+"  "+c["sub"]
    d.text((24,58),head[:20],font=_ttf(40,mono=True),fill=WHITE)
    rows=list(c["rows"] or [])
    while len(rows)<2: rows.append(("",""))
    cw,ch=256,150
    _flip_card(d,24,140,cw,ch,rows[0][0],rows[0][1] or "--:--")
    _flip_card(d,w-24-cw,140,cw,ch,rows[1][0],rows[1][1] or "--:--")
    if c.get("in_flight"):
        by=h-30; d.rectangle([24,by,w-24,by+16],fill=(46,46,52))
        d.rectangle([24,by,24+int((w-48)*c["prog"]),by+16],fill=AMBER)
    return img

def _board_dot(w,h,c):
    img=Image.new("RGB",(w,h),BLACK)
    lines=[(c["title"].upper()[:18], GREEN), ((c["hero"] or "")[:18], AMBER)]
    if c["sub"]: lines.append((c["sub"][:18], (230,180,60)))
    for lab,val in (c["rows"] or [])[:2]:
        if lab or val: lines.append((f"{lab} {val}".strip()[:18], AMBER))
    y=34
    for txt,col in lines[:5]:
        strip=_dot_text(txt,col,module=5,gap=1)
        if strip.size[0]>w-40:
            strip=strip.resize((w-40,int(strip.size[1]*(w-40)/strip.size[0])),Image.NEAREST)
        img.paste(strip,(28,y)); y+=strip.size[1]+16
    if c.get("in_flight"):
        d=ImageDraw.Draw(img); by=h-28
        for i in range(40):
            on=i/40<=c["prog"]; cx=30+i*((w-60)/40)
            d.ellipse([cx-3,by-3,cx+3,by+3],fill=AMBER if on else (40,30,12))
    return img

def _swiss(w,h,c):
    img=Image.new("RGB",(w,h),WHITE); d=ImageDraw.Draw(img)
    d.text((40,40),f"{c['header']}   {c['fid']}   {c['route']}",font=_ttf(20,False),fill=BLACK)
    d.line([(40,76),(w-40,76)],fill=BLACK,width=2)
    d.text((40,150),"HOME",font=_ttf(26),fill=RED)
    d.text((36,178),c["home"] or "--:--",font=_ttf(150),fill=BLACK)
    d.text((40,348),"LANDS  "+(c["land"] or "--:--"),font=_ttf(30,False),fill=BLACK)
    d.line([(40,410),(w-40,410)],fill=(150,150,150),width=2)
    mx=40+(w-80)*c["prog"]; d.line([(mx,400),(mx,420)],fill=RED,width=4)
    return img

def _chart(w,h,c):
    img=Image.new("RGB",(w,h),WHITE); d=ImageDraw.Draw(img); grid=(150,170,200)
    for x in range(0,w,40): d.line([(x,0),(x,h)],fill=grid,width=1)
    for y in range(0,h,40): d.line([(0,y),(w,y)],fill=grid,width=1)
    d.text((20,16),(c["fid"] or "")+"   "+(c["route"] or ""),font=_ttf(26),fill=BLACK)
    x0,x1,base,amp=70,w-70,300,110
    pts=[(x0+(x1-x0)*i/200, base-amp*math.sin(math.pi*i/200)) for i in range(201)]
    n=int(200*c["prog"])
    for i in range(n,200,4): d.ellipse([pts[i][0]-1,pts[i][1]-1,pts[i][0]+1,pts[i][1]+1],fill=(120,120,120))
    if n>1: d.line(pts[:n+1],fill=BLUE,width=4)
    for px,py,lab in [(pts[0][0],pts[0][1],c["dep"]),(pts[-1][0],pts[-1][1],c["arr"])]:
        d.ellipse([px-7,py-7,px+7,py+7],outline=BLACK,width=2,fill=WHITE)
        d.text((px-10,py+12),lab,font=_ttf(20),fill=BLACK)
    mx,my=pts[n]; d.polygon([(mx+10,my),(mx-8,my-6),(mx-8,my+6)],fill=RED)
    d.text((20,h-58),"LANDS",font=_ttf(16),fill=GREEN); d.text((20,h-40),c["land"] or "--:--",font=_ttf(30),fill=BLACK)
    hs="HOME "+(c["home"] or "--:--"); d.text((w-20-_tl(d,hs,_ttf(30)),h-40),hs,font=_ttf(30),fill=RED)
    return img

def _cockpit(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((20,16),(c["fid"] or "")+"  "+(c["route"] or ""),font=_ttf(24,mono=True),fill=GREEN)
    cx,cy,R=w//2,250,150
    d.ellipse([cx-R,cy-R,cx+R,cy+R],outline=(70,80,70),width=10)
    d.arc([cx-R,cy-R,cx+R,cy+R],-90,-90+360*c["prog"],fill=GREEN,width=12)
    pct=f"{int(c['prog']*100)}%"; f=_ttf(72,mono=True)
    d.text((cx-_tl(d,pct,f)/2,cy-70),pct,font=f,fill=WHITE)
    d.text((cx-_tl(d,'ENROUTE',_ttf(22,mono=True))/2,cy+10),"ENROUTE",font=_ttf(22,mono=True),fill=GREEN)
    a=math.radians(-90+360*c["prog"]); mx,my=cx+R*math.cos(a),cy+R*math.sin(a)
    d.ellipse([mx-9,my-9,mx+9,my+9],fill=YELLOW)
    d.text((20,150),"ETA",font=_ttf(18,mono=True),fill=(120,160,120)); d.text((20,170),c["land"] or "--:--",font=_ttf(40,mono=True),fill=YELLOW)
    d.text((w-20-_tl(d,'HOME',_ttf(18,mono=True)),150),"HOME",font=_ttf(18,mono=True),fill=(120,160,120))
    d.text((w-20-_tl(d,c["home"] or "--:--",_ttf(40,mono=True)),170),c["home"] or "--:--",font=_ttf(40,mono=True),fill=GREEN)
    return img

STYLES={
    "boarding":_boarding, "board_solari":_board_solari, "board_yellow":_board_yellow,
    "board_rail":_board_rail, "board_flip":_board_flip, "board_dot":_board_dot,
    "swiss":_swiss, "chart":_chart, "cockpit":_cockpit,
}
STYLE_LABELS=[
    ("boarding","Boarding pass (QR to FR24)"),
    ("board_solari","Departure board \u2014 Solari"),
    ("board_yellow","Departure board \u2014 yellow grid"),
    ("board_rail","Departure board \u2014 rail blue"),
    ("board_flip","Departure board \u2014 flip clock"),
    ("board_dot","Departure board \u2014 LED dot sign"),
    ("swiss","Swiss minimalist"),
    ("chart","Aeronautical chart"),
    ("cockpit","Cockpit / EFIS"),
]

def dither(img):
    p=Image.new("P",(1,1)); p.putpalette(PAL+[0]*(768-len(PAL)))
    return img.quantize(palette=p, dither=Image.FLOYDSTEINBERG).convert("RGB")

def _ctx(screen: Screen):
    d = dict(screen.data)
    st = d.get("state", ""); fid = d.get("fid", ""); route = d.get("route", "")
    land = (d.get("land") or "").lstrip("~"); home = (d.get("home") or "").lstrip("~")
    rep = d.get("report", ""); date = d.get("date", ""); deptime = d.get("dep_time", "")
    cd = d.get("countdown", ""); cdl = d.get("countdown_label", "")
    title = screen.header; hero = fid or ""; sub = route; rows = []
    if st == "IN_FLIGHT":
        title = "IN FLIGHT"; hero = route or fid; sub = fid
        rows = [("LANDS", land), ("HOME", home)]
    elif st == "PRE_FLIGHT":
        title = "DEPARTS"; hero = deptime or "--:--"; sub = f"{fid}  {route}".strip()
        rows = [("FLIGHT", fid), ("HOME", home)]
    elif st == "TURNAROUND":
        title = "TURNAROUND"; hero = deptime or "--:--"; sub = f"{fid}  {route}".strip()
        rows = [("NEXT DEP", deptime), ("HOME", home)]
    elif st == "POST_DUTY":
        title = "HEADING HOME"; hero = home or "--:--"; sub = route
        rows = [("LANDED", land), ("", "")]
    elif st == "BETWEEN_DUTIES":
        if fid:
            title = "NEXT DUTY"; hero = fid; sub = route
            rows = [("REPORT", rep), ("DATE", date)]
        else:
            title = cdl or "NEXT"; hero = cd or "--:--"; sub = date; rows = []
    elif st == "STANDBY":
        title = "STANDBY"; hero = "STBY"; sub = date; rows = []
    elif st == "DAY_OFF":
        title = "DAY OFF"; hero = "OFF"; sub = date; rows = []
    else:
        title = title or "NO ROSTER"; hero = "FLIGHT WALL"; sub = ""; rows = []
    d.update(header=screen.header, accent=screen.accent, title=title,
             hero=hero, sub=sub, rows=rows, land=land, home=home)
    return d

def render(screen: Screen, style="boarding", w=600, h=448) -> Image.Image:
    ctx = _ctx(screen)
    fn = STYLES.get(style, _board_solari)
    img = fn(600, 448, ctx)                       # design at canonical resolution
    if (w, h) != (600, 448):                      # scale to fill the real panel
        img = img.resize((w, h), Image.LANCZOS)
    return dither(img)


class InkyRenderer(Renderer):
    """Push the selected style to a Pimoroni Inky Impression panel.

    Also owns the 4 side buttons (A..D):
        A: display on/off      B: cycle style
        C: contrast/saturation max <-> default      D: full-screen tracking QR (5 s)
    """
    def __init__(self, style="boarding", width=600, height=448, saturation=0.6,
                 styles=None, on_style_change=None):
        from inky.auto import auto          # lazy: only on the Pi
        self.inky = auto()
        self.width = getattr(self.inky, "width", width)
        self.height = getattr(self.inky, "height", height)
        print(f"[flightwall] Inky detected: {self.width}x{self.height}")
        self.style = style
        self.styles = styles or [k for k, _ in STYLE_LABELS]
        self.on_style_change = on_style_change
        self.saturation = saturation; self._base_sat = saturation
        self.power = True
        self._last = None; self._last_screen = None
        self._setup_buttons()

    # ---- rendering ----
    def show(self, screen: Screen) -> None:
        self._last_screen = screen
        if not self.power:
            return
        img = render(screen, self.style, self.width, self.height)
        self._push(img)

    def _push(self, img):
        key = img.tobytes()
        if key == self._last:
            return                              # e-ink is slow; repaint only on change
        try:
            self.inky.set_image(img, saturation=self.saturation)
        except TypeError:
            self.inky.set_image(img)            # mono panels take no saturation
        self.inky.show(); self._last = key

    # ---- button actions ----
    def toggle_power(self):
        self.power = not self.power
        if not self.power:
            from PIL import Image as _I
            self._push(_I.new("RGB", (self.width, self.height), (255, 255, 255)))
        elif self._last_screen is not None:
            self._last = None; self.show(self._last_screen)

    def cycle_style(self):
        i = (self.styles.index(self.style) + 1) % len(self.styles) \
            if self.style in self.styles else 0
        self.style = self.styles[i]
        if self.on_style_change:
            self.on_style_change(self.style)        # persist the choice
        if self._last_screen is not None:
            self._last = None; self.show(self._last_screen)

    def toggle_brightness(self):
        # e-ink has no backlight; the nearest control is colour saturation/contrast
        self.saturation = 1.0 if self.saturation < 0.99 else self._base_sat
        if self._last_screen is not None:
            self._last = None; self.show(self._last_screen)

    def show_qr_5s(self):
        url = (self._last_screen.data.get("fr24_url") if self._last_screen else "") \
            or "https://www.flightradar24.com"
        qr = make_qr(url, module=max(6, self.width // 60), quiet=4)
        from PIL import Image as _I
        canvas = _I.new("RGB", (self.width, self.height), WHITE)
        canvas.paste(qr, ((self.width - qr.size[0]) // 2, (self.height - qr.size[1]) // 2))
        self._push(dither(canvas))
        import threading
        def _restore():
            self._last = None
            if self._last_screen is not None and self.power:
                self.show(self._last_screen)
        threading.Timer(5.0, _restore).start()

    def _setup_buttons(self):
        # Inky Impression buttons A,B,C,D on BCM pins 5,6,16,24
        try:
            from gpiozero import Button
            pins = {5: self.toggle_power, 6: self.cycle_style,
                    16: self.toggle_brightness, 24: self.show_qr_5s}
            self._buttons = []
            for pin, action in pins.items():
                b = Button(pin, pull_up=True, bounce_time=0.1)
                b.when_pressed = (lambda a=action: a())
                self._buttons.append(b)
            print("[flightwall] side buttons A/B/C/D armed")
        except Exception as e:
            print(f"[flightwall] buttons unavailable ({e}); display will still update")

    def clear(self): pass

