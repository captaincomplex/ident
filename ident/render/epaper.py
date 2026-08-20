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
INK_=(30,30,34)
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
        print("[ident] WARNING: DejaVu fonts not found - text will be tiny. "
              "Fix with:  sudo apt install -y fonts-dejavu-core")
        _FONT_WARNED = True
    return ImageFont.load_default()

def _tl(d,s,f): return d.textlength(s,font=f)
def _notz(v):
    v=v or ""
    return v[:-1] if v[-1:] in ("Z","L") else v
def _cond(px):
    for c in ("DejaVuSansCondensed-Bold.ttf", _font_file("DejaVuSansCondensed-Bold.ttf")):
        try: return ImageFont.truetype(c,px)
        except Exception: continue
    return _ttf(px)

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
    data_dir = os.path.expanduser(os.environ.get("IDENT_DATA", "~/.ident"))
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
    if c.get("state")=="DAY_OFF" and c.get("next_summary"):
        gy=346; d.line([(24,gy),(w-24,gy)],fill=(110,95,45),width=2)
        d.text((24,gy+12),"NEXT DUTY",font=_ttf(22,mono=True),fill=ORANGE)
        d.text((24,gy+40),c["next_summary"][:24],font=_ttf(34,mono=True),fill=WHITE)
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
    SEA=(206,220,234); LAND=(227,223,206); COAST=(150,150,138); GRID=(168,182,200)
    LINE=(44,50,62); ROUTE=(160,58,98); TXT=(34,38,48); DIM=(108,118,134); PROG=(206,96,44)
    img=Image.new("RGB",(w,h),SEA); d=ImageDraw.Draw(img)
    pa=_lalo(c.get("dep","")); pb=_lalo(c.get("arr",""))
    if c.get("fid") and pa and pb:
        P=_mapbase(d,w,h,pa,pb,SEA,LAND,COAST,GRID,DIM,c)
        p0=P(*pa); p1=P(*pb); peak=min(72,16+abs(p1[0]-p0[0])*0.12); pts=[]
        for i in range(61):
            t=i/60; x=p0[0]+(p1[0]-p0[0])*t; y=p0[1]+(p1[1]-p0[1])*t-peak*math.sin(math.pi*t); pts.append((x,y))
        d.line(pts,fill=ROUTE,width=3)
        for t in (0.34,0.66):
            fx,fy=pts[int(t*60)]; d.ellipse([fx-4,fy-4,fx+4,fy+4],outline=ROUTE,width=2,fill=SEA)
        dp=int(float(c.get("prog") or 0)*60); dx,dy=pts[dp]; d.ellipse([dx-8,dy-8,dx+8,dy+8],fill=PROG,outline=WHITE,width=2)
        for (px,py),code in ((p0,c.get("dep")),(p1,c.get("arr"))):
            d.ellipse([px-6,py-6,px+6,py+6],fill=WHITE,outline=LINE,width=2); d.ellipse([px-2,py-2,px+2,py+2],fill=LINE)
            d.text((px+9,py-9),code,font=_cond(22),fill=TXT)
        lbl=f'{int(_bearing(pa,pb)):03d}°  {int(_haversine(pa,pb)/1.852)} NM'
        mx,my=pts[30]; twd=_tl(d,lbl,_cond(16))
        d.rectangle([mx-twd/2-6,my-32,mx+twd/2+6,my-10],fill=(244,242,232),outline=ROUTE,width=1)
        d.text((mx-twd/2,my-30),lbl,font=_cond(16),fill=ROUTE)
        d.rectangle([0,0,w,30],fill=(236,233,221)); d.line([(0,30),(w,30)],fill=LINE,width=1)
        d.text((12,5),"ENROUTE  LOW",font=_cond(18),fill=LINE)
        idx=f'{c.get("dep","")} – {c.get("arr","")}'; d.text((w-12-_tl(d,idx,_cond(18)),5),idx,font=_cond(18),fill=LINE)
        d.rectangle([0,h-46,w,h],fill=(236,233,221)); d.line([(0,h-46),(w,h-46)],fill=LINE,width=1)
        d.text((12,h-40),c.get("fid",""),font=_cond(24),fill=TXT); d.text((12,h-18),c.get("status",""),font=_cond(15),fill=DIM)
        def blk(x,lab,val): d.text((x,h-40),lab,font=_cond(14),fill=ROUTE); d.text((x,h-24),val,font=_cond(24),fill=TXT)
        blk(w-250,"LANDS",c.get("land") or "--:--"); blk(w-120,"HOME",c.get("home") or "--:--")
    else:
        d.rectangle([0,0,w,30],fill=(236,233,221)); d.line([(0,30),(w,30)],fill=LINE,width=1)
        d.text((12,5),"ENROUTE  LOW",font=_cond(18),fill=LINE)
        hero=c.get("hero") or ""; d.text((w/2-_tl(d,hero,_cond(120 if len(hero)<=4 else 70))/2,150),hero,font=_cond(120 if len(hero)<=4 else 70),fill=TXT)
        sub=c.get("sub") or ""; d.text((w/2-_tl(d,sub,_cond(30))/2,300),sub,font=_cond(30),fill=DIM)
        ns=c.get("next_summary")
        if ns: d.text((18,h-58),"NEXT DUTY",font=_cond(20),fill=ROUTE); d.text((18,h-34),ns[:26],font=_cond(26),fill=TXT)
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


# ---- airport coords for the map style (offline airportsdata) ----
try:
    from ..timezones import _AIRPORTS as _APTS
except Exception:
    _APTS = {}
def _lalo(iata):
    a=_APTS.get((iata or "").upper())
    if a:
        try: return float(a["lat"]), float(a["lon"])
        except Exception: pass
    return None

# ============================ NEW STYLES (v3.2) ============================

def _tiles(w,h,c):
    img=Image.new("RGB",(w,h),WHITE); d=ImageDraw.Draw(img)
    if c.get("fid"):
        cells=[("FLIGHT", c.get("flight_no") or c.get("fid"), BLUE),
               ("ROUTE", c.get("route") or "--", ORANGE),
               ("LANDS", _notz(c.get("land")) or "--:--", GREEN),
               ("HOME", c.get("home") or "--:--", RED),
               ("STATUS", "__BAR__", BLUE),
               ("ETA IN", c.get("eta_dur") or "--", ORANGE)]
    else:
        cells=[(c.get("title") or "STATUS", c.get("hero") or "--", BLUE),
               ("WHEN", c.get("sub") or "--", ORANGE),
               ("STATUS", c.get("status") or "--", GREEN),
               ("NEXT", c.get("next_summary") or "--", RED)]
    mx,my,gap=16,16,12; cols=3 if len(cells)>4 else 2
    rows=(len(cells)+cols-1)//cols
    cw=(w-2*mx-(cols-1)*gap)//cols; ch=(h-2*my-(rows-1)*gap)//rows
    for i,(lab,val,col) in enumerate(cells):
        r,cc=divmod(i,cols); x=mx+cc*(cw+gap); y=my+r*(ch+gap)
        d.rounded_rectangle([x,y,x+cw,y+ch],radius=10,fill=(245,243,235),outline=(208,203,188),width=2)
        d.rectangle([x,y+8,x+cw,y+30],fill=col); d.rounded_rectangle([x,y,x+cw,y+18],radius=10,fill=col)
        d.text((x+12,y+6),lab,font=_ttf(15,mono=False),fill=WHITE)
        if val=="__BAR__":
            prog=float(c.get("prog") or 0.0)
            d.text((x+12,y+40),(c.get("status") or "ENROUTE"),font=_cond(26),fill=INK_)
            bx0,bx1,by=x+12,x+cw-12,y+ch-26
            d.rounded_rectangle([bx0,by,bx1,by+16],radius=6,outline=(150,140,90),width=2)
            d.rounded_rectangle([bx0+2,by+2,bx0+2+int((bx1-bx0-4)*prog),by+14],radius=5,fill=col)
            d.text((x+cw-12-_tl(d,f"{int(prog*100)}%",_ttf(16,mono=True)),y+36),f"{int(prog*100)}%",font=_ttf(16,mono=True),fill=col)
        else:
            fs=46 if len(val)<=6 else 30 if len(val)<=9 else 22 if len(val)<=16 else 16
            f=_cond(fs); d.text((x+cw/2-_tl(d,val,f)/2, y+ch/2-fs*0.55), val[:24], font=f, fill=INK_)
    return img

# rough coastlines (lat,lon) for the UK->Denmark map overlay
_GB=[(58.6,-3.0),(57.7,-3.9),(57.6,-1.8),(56.0,-2.6),(55.0,-1.5),(54.1,-0.2),(52.9,0.3),(52.1,1.7),
     (51.4,1.4),(50.9,0.3),(50.7,-1.9),(50.1,-5.7),(51.2,-4.2),(51.6,-5.3),(52.8,-4.7),(53.3,-3.1),
     (54.1,-3.6),(55.0,-5.0),(55.9,-5.6),(56.6,-5.9),(57.6,-5.8),(58.5,-5.3),(58.6,-3.0)]
_IE=[(55.2,-7.3),(54.5,-5.5),(53.3,-6.1),(52.2,-6.4),(51.6,-8.9),(52.1,-10.4),(53.4,-9.9),(54.3,-8.5),(55.2,-7.3)]
_EUR=[(46.0,-1.2),(48.4,-4.7),(49.7,-1.6),(49.9,1.6),(51.0,1.6),(51.4,3.2),(51.9,4.1),(52.9,4.7),
      (53.4,6.8),(53.9,8.9),(54.0,8.3),(55.0,8.2),(56.5,8.2),(57.7,10.6),(57.0,10.5),(56.0,10.2),
      (55.0,9.8),(54.4,11.0),(54.1,13.8),(54.6,16.5),(54.6,20.0),(46.0,20.0),(46.0,-1.2)]
_ZL=[(56.1,11.8),(56.0,12.6),(55.3,12.7),(55.0,11.5),(55.6,11.0),(56.1,11.8)]
_SCAN=[(61.0,4.8),(58.0,6.5),(58.4,11.2),(56.2,12.6),(55.4,13.0),(57.0,16.5),(59.0,18.5),(61.0,17.5),(61.0,4.8)]
_LONMIN,_LONMAX,_LATMIN,_LATMAX=-11.0,20.0,46.0,61.0
def _mproj(lat,lon,w,h):
    x=(lon-_LONMIN)/(_LONMAX-_LONMIN)*w; y=(_LATMAX-lat)/(_LATMAX-_LATMIN)*h; return (x,y)

def _haversine(a,b):
    R=6371.0; (la1,lo1),(la2,lo2)=a,b
    p1,p2=math.radians(la1),math.radians(la2); dp=math.radians(la2-la1); dl=math.radians(lo2-lo1)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(min(1.0,math.sqrt(x)))
def _bearing(a,b):
    (la1,lo1),(la2,lo2)=a,b
    y=math.sin(math.radians(lo2-lo1))*math.cos(math.radians(la2))
    x=math.cos(math.radians(la1))*math.sin(math.radians(la2))-math.sin(math.radians(la1))*math.cos(math.radians(la2))*math.cos(math.radians(lo2-lo1))
    return (math.degrees(math.atan2(y,x))+360)%360
_HUBS=["LGW","LHR","CPH","AMS","BRU","CDG","GVA","ZRH","MXP","FCO","NAP","BCN","MAD",
       "AGP","LIS","FAO","PMI","IBZ","NCE","LYS","BER","MUC","HAM","PRG","VIE","BUD",
       "ATH","SKG","HER","CFU","DBV","SPU","TFS","LPA","ACE","RAK","HRG","SSH","AYT",
       "IST","KEF","EDI","GLA","DUB","WAW","KRK","OTP","SOF","MLA","TLS","OPO","ALC"]

def _mapbase(d,w,h,pa,pb,SEA,LAND,COAST,GRID,DOT,c,label_hubs=True):
    """Shared geographic base: dynamic bbox around the route, cached coastline
    landmasses, graticule and reference hubs. Returns the projection P(lat,lon)."""
    lats=[pa[0],pb[0]]; lons=[pa[1],pb[1]]
    dla=max(2.0,max(lats)-min(lats)); dlo=max(2.0,max(lons)-min(lons)); pad=0.5
    la0,la1=min(lats)-dla*pad,max(lats)+dla*pad; lo0,lo1=min(lons)-dlo*pad,max(lons)+dlo*pad
    cosm=math.cos(math.radians((la0+la1)/2)) or 1e-3; aspect=w/h
    wdeg=(lo1-lo0)*cosm; hdeg=(la1-la0)
    if wdeg/hdeg<aspect:
        need=hdeg*aspect/cosm; ce=(lo0+lo1)/2; lo0,lo1=ce-need/2,ce+need/2
    else:
        need=wdeg/aspect; ce=(la0+la1)/2; la0,la1=ce-need/2,ce+need/2
    def P(lat,lon):
        return ((lon-lo0)/(lo1-lo0)*w, (la1-lat)/(la1-la0)*h)
    try:
        from ..geo import get_land
        for item in get_land():
            b=item["b"]
            if b[2]<lo0 or b[0]>lo1 or b[3]<la0 or b[1]>la1: continue
            pts=[P(y,x) for x,y in item["r"]]
            if len(pts)>=3: d.polygon(pts,fill=LAND,outline=COAST)
    except Exception:
        pass
    span=lo1-lo0; step=10 if span>30 else 5 if span>14 else 2 if span>6 else 1
    g=math.ceil(lo0/step)*step
    while g<=lo1: x=P(0,g)[0]; d.line([(x,0),(x,h)],fill=GRID,width=1); g+=step
    g=math.ceil(la0/step)*step
    while g<=la1: y=P(g,0)[1]; d.line([(0,y),(w,y)],fill=GRID,width=1); g+=step
    for code in _HUBS:
        pc=_lalo(code)
        if pc and la0<=pc[0]<=la1 and lo0<=pc[1]<=lo1 and code not in (c.get("dep"),c.get("arr")):
            x,y=P(*pc); d.ellipse([x-2,y-2,x+2,y+2],fill=DOT)
            if label_hubs: d.text((x+4,y-7),code,font=_ttf(11,mono=True),fill=DOT)
    return P

def _greatcircle(w,h,c):
    SEA=(30,44,76); LAND=(46,74,54); COAST=(92,122,96); GRID=(44,60,96); DOT=(150,175,215)
    img=Image.new("RGB",(w,h),SEA); d=ImageDraw.Draw(img)
    pa=_lalo(c.get("dep","")); pb=_lalo(c.get("arr",""))
    if c.get("fid") and pa and pb:
        P=_mapbase(d,w,h,pa,pb,SEA,LAND,COAST,GRID,DOT,c)
        p0=P(*pa); p1=P(*pb); peak=min(80,16+abs(p1[0]-p0[0])*0.12); pts=[]
        for i in range(61):
            t=i/60; x=p0[0]+(p1[0]-p0[0])*t; y=p0[1]+(p1[1]-p0[1])*t-peak*math.sin(math.pi*t); pts.append((x,y))
        d.line(pts,fill=(235,225,170),width=3)
        dp=int(float(c.get("prog") or 0)*60); dx,dy=pts[dp]; d.ellipse([dx-9,dy-9,dx+9,dy+9],fill=YELLOW,outline=WHITE,width=2)
        for (px,py),code in ((p0,c.get("dep")),(p1,c.get("arr"))):
            d.ellipse([px-5,py-5,px+5,py+5],fill=WHITE,outline=BLACK); d.text((px+7,py-26),code,font=_ttf(24,mono=True),fill=WHITE)
        d.rectangle([0,0,w,34],fill=(20,30,52)); d.text((14,7),c.get("fid",""),font=_ttf(22,mono=True),fill=YELLOW)
        info=f'{int(_haversine(pa,pb)/1.852)}NM  {int(_bearing(pa,pb)):03d}°'
        d.text((w-14-_tl(d,info,_ttf(20,mono=True)),8),info,font=_ttf(20,mono=True),fill=(150,175,215))
        d.rectangle([0,h-34,w,h],fill=(20,30,52))
        d.text((14,h-28),f'LAND {c.get("land") or "--:--"}',font=_ttf(22,mono=True),fill=WHITE)
        hm=f'HOME {c.get("home") or "--:--"}'; d.text((w-14-_tl(d,hm,_ttf(22,mono=True)),h-28),hm,font=_ttf(22,mono=True),fill=ORANGE)
    else:
        for y in range(0,h,52): d.line([(0,y),(w,y)],fill=GRID,width=1)
        for x in range(0,w,52): d.line([(x,0),(x,h)],fill=GRID,width=1)
        d.text((24,18),(c.get("title") or "").upper(),font=_ttf(30,mono=True),fill=YELLOW)
        hero=c.get("hero") or ""; hf=_ttf(110 if len(hero)<=4 else 70,mono=True)
        d.text((w/2-_tl(d,hero,hf)/2,150),hero,font=hf,fill=WHITE)
        sub=c.get("sub") or ""; d.text((w/2-_tl(d,sub,_ttf(30,mono=True))/2,290),sub,font=_ttf(30,mono=True),fill=(205,205,195))
        ns=c.get("next_summary")
        if ns: d.text((24,h-66),"NEXT DUTY",font=_ttf(20,mono=True),fill=ORANGE); d.text((24,h-40),ns[:24],font=_ttf(28,mono=True),fill=WHITE)
    return img

def _minimal(w,h,c):
    img=Image.new("RGB",(w,h),WHITE); d=ImageDraw.Draw(img)
    top=c.get("fid") or c.get("title") or ""
    d.text((40,40),top,font=_ttf(24,mono=False),fill=INK_)
    ds=c.get("date") or ""; d.text((w-40-_tl(d,ds,_ttf(24,mono=False)),40),ds,font=_ttf(24,mono=False),fill=(120,120,120))
    d.line([(40,84),(w-40,84)],fill=RED,width=4)
    big=(c.get("arr") if c.get("fid") else c.get("hero")) or ""
    bf=_cond(190 if len(big)<=3 else 150 if len(big)<=4 else 120)
    d.text((40,118),big,font=bf,fill=INK_)
    if c.get("fid"):
        sub=f'{APT.get(c.get("dep"),c.get("dep"))} → {APT.get(c.get("arr"),c.get("arr"))}'
        d.text((44,318),sub[:34],font=_ttf(24,mono=False),fill=(90,90,90))
        d.text((44,360),"LANDS",font=_ttf(18),fill=RED); d.text((44,382),_notz(c.get("land")) or "--:--",font=_cond(40),fill=INK_)
        d.text((320,360),"HOME",font=_ttf(18),fill=RED); d.text((320,382),_notz(c.get("home")) or "--:--",font=_cond(40),fill=INK_)
    else:
        sub=c.get("sub") or ""; d.text((44,322),sub[:34],font=_ttf(24,mono=False),fill=(90,90,90))
        ns=c.get("next_summary")
        if ns:
            d.text((44,372),"NEXT DUTY",font=_ttf(18),fill=RED); d.text((44,396),ns[:26],font=_cond(30),fill=INK_)
    return img

def _timeline(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((24,22),(c.get("title") or "DUTY")[:16],font=_ttf(30,mono=True),fill=YELLOW)
    ds=c.get("date") or ""; d.text((w-24-_tl(d,ds,_ttf(20,mono=True)),30),ds,font=_ttf(20,mono=True),fill=(150,140,90))
    d.line([(24,70),(w-24,70)],fill=ORANGE,width=3)
    segs=c.get("segments") or []
    ax,ay,aw=44,250,w-88
    if segs:
        d.line([(ax,ay),(ax+aw,ay)],fill=(110,95,45),width=4)
        cols=[BLUE,GREEN,ORANGE,RED]
        for i,sg in enumerate(segs):
            x0=ax+aw*sg["a"]; x1=ax+aw*sg["b"]; col=cols[i%len(cols)]
            d.rounded_rectangle([x0,ay-18,x1,ay+18],radius=6,fill=col)
            if x1-x0>54: d.text(((x0+x1)/2-_tl(d,sg["label"],_ttf(16,mono=True))/2,ay-11),sg["label"],font=_ttf(16,mono=True),fill=WHITE)
        nf=c.get("now_frac")
        if nf is not None:
            nx=ax+aw*nf; d.line([(nx,ay-40),(nx,ay+40)],fill=RED,width=3)
            d.text((nx-_tl(d,"NOW",_ttf(18,mono=True))/2,ay-64),"NOW",font=_ttf(18,mono=True),fill=RED)
        if c.get("fid"): d.text((24,300),f'{c.get("fid")}  {c.get("route")}',font=_ttf(32,mono=True),fill=WHITE)
        d.text((24,348),f'LAND {c.get("land") or "--:--"}',font=_ttf(26,mono=True),fill=GREEN)
        d.text((300,348),f'HOME {c.get("home") or "--:--"}',font=_ttf(26,mono=True),fill=ORANGE)
        d.text((24,392),(c.get("status") or ""),font=_ttf(22,mono=True),fill=(150,140,90))
    else:
        hero=c.get("hero") or ""; hf=_ttf(110 if len(hero)<=4 else 64,mono=True)
        d.text((w/2-_tl(d,hero,hf)/2,150),hero,font=hf,fill=WHITE)
        sub=c.get("sub") or ""; d.text((w/2-_tl(d,sub,_ttf(30,mono=True))/2,290),sub,font=_ttf(30,mono=True),fill=(205,205,195))
        ns=c.get("next_summary")
        if ns:
            d.text((24,h-70),"NEXT DUTY",font=_ttf(20,mono=True),fill=ORANGE); d.text((24,h-44),ns[:24],font=_ttf(28,mono=True),fill=WHITE)
    return img

STYLES={
    "boarding":_boarding, "board_solari":_board_solari, "board_yellow":_board_yellow,
    "board_rail":_board_rail, "board_flip":_board_flip, "board_dot":_board_dot,
    "swiss":_swiss, "chart":_chart, "cockpit":_cockpit,
    "tiles":_tiles, "greatcircle":_greatcircle, "minimal":_minimal, "timeline":_timeline,
}
STYLE_LABELS=[
    ("boarding","Boarding pass (QR to FR24)"),
    ("board_solari","Departure board \u2014 Solari"),
    ("board_yellow","Departure board \u2014 yellow grid"),
    ("board_rail","Departure board \u2014 rail blue"),
    ("board_flip","Departure board \u2014 flip clock"),
    ("board_dot","Departure board \u2014 LED dot sign"),
    ("swiss","Swiss minimalist"),
    ("chart","Enroute chart — Lido"),
    ("cockpit","Cockpit / EFIS"),
    ("tiles","Tiles dashboard"),
    ("greatcircle","Great circle map"),
    ("minimal","Minimal — XL destination"),
    ("timeline","Duty timeline"),
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
        title = title or "NO ROSTER"; hero = "IDENT"; sub = ""; rows = []
    _smap={"IN_FLIGHT":"ENROUTE","PRE_FLIGHT":"REPORTED","TURNAROUND":"TURNAROUND",
           "POST_DUTY":"HEADING HOME","BETWEEN_DUTIES":(cdl or "NEXT"),
           "STANDBY":"STANDBY","DAY_OFF":"DAY OFF","NO_ROSTER":"NO ROSTER"}
    d.update(header=screen.header, accent=screen.accent, title=title,
             hero=hero, sub=sub, rows=rows, land=land, home=home,
             status=_smap.get(st,""))
    return d

def render(screen: Screen, style="boarding", w=600, h=448) -> Image.Image:
    ctx = _ctx(screen)
    fn = STYLES.get(style, _board_solari)
    img = fn(600, 448, ctx)                       # design at canonical resolution
    if (w, h) != (600, 448):                      # scale to fill the real panel
        img = img.resize((w, h), Image.LANCZOS)
    return dither(img)


def _next_duty_overlay(w,h,c):
    img=Image.new("RGB",(w,h),BLACK); d=ImageDraw.Draw(img)
    d.text((24,22),"NEXT DUTY",font=_ttf(30,mono=True),fill=ORANGE)
    d.line([(24,66),(w-24,66)],fill=ORANGE,width=3)
    nd=c.get("next_date") or ""
    if not nd:
        d.text((24,180),"No upcoming duty",font=_ttf(40,mono=True),fill=WHITE); return img
    d.text((24,88),nd,font=_ttf(54,mono=True),fill=WHITE)
    route=c.get("next_route") or ""
    if route: d.text((24,168),route[:26],font=_ttf(38,mono=True),fill=YELLOW)
    y=244
    rep=c.get("next_report")
    if rep:
        d.text((24,y+6),"REPORT",font=_ttf(22,mono=True),fill=(150,140,90)); d.text((230,y),rep,font=_ttf(44,mono=True),fill=WHITE); y+=72
    dep=c.get("next_dep")
    if dep:
        d.text((24,y+6),"1st DEP",font=_ttf(22,mono=True),fill=(150,140,90)); d.text((230,y),dep,font=_ttf(44,mono=True),fill=WHITE); y+=72
    ns=c.get("next_summary") or ""
    d.text((24,h-44),ns[:30],font=_ttf(24,mono=True),fill=(205,205,195))
    return img

def render_next_duty(screen, w=600, h=448):
    ctx=_ctx(screen); img=_next_duty_overlay(600,448,ctx)
    if (w,h)!=(600,448): img=img.resize((w,h),Image.LANCZOS)
    return dither(img)

class InkyRenderer(Renderer):
    """Push the selected style to a Pimoroni Inky Impression panel.

    Also owns the 4 side buttons (A..D):
        A: display on/off      B: cycle style
        C: contrast/saturation max <-> default      D: next-duty card (7 s)
    """
    def __init__(self, style="boarding", width=600, height=448, saturation=0.6,
                 styles=None, on_style_change=None):
        from inky.auto import auto          # lazy: only on the Pi
        self.inky = auto()
        self.width = getattr(self.inky, "width", width)
        self.height = getattr(self.inky, "height", height)
        print(f"[ident] Inky detected: {self.width}x{self.height}")
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

    def show_next_duty_5s(self):
        if self._last_screen is None:
            return
        img = render_next_duty(self._last_screen, self.width, self.height)
        self._push(img)
        import threading
        def _restore():
            self._last = None
            if self._last_screen is not None and self.power:
                self.show(self._last_screen)
        threading.Timer(7.0, _restore).start()

    def _setup_buttons(self):
        # Inky Impression buttons A,B,C,D on BCM pins 5,6,16,24
        try:
            from gpiozero import Button
            pins = {5: self.toggle_power, 6: self.cycle_style,
                    16: self.toggle_brightness, 24: self.show_next_duty_5s}
            self._buttons = []
            for pin, action in pins.items():
                b = Button(pin, pull_up=True, bounce_time=0.1)
                b.when_pressed = (lambda a=action: a())
                self._buttons.append(b)
            print("[ident] side buttons A/B/C/D armed")
        except Exception as e:
            print(f"[ident] buttons unavailable ({e}); display will still update")

    def clear(self): pass

