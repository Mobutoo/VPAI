#!/usr/bin/env python3
"""Génère les assets de marque Yinda pour TREK (trip.ewutelo.cloud).

Tous les SVG sont *font-independent* : le wordmark "Yinda" est vectorisé en
<path> via fontTools (MuseoModerno 800, la police de marque de TREK). Aucun
font-family — sinon le rendu en mode static (favicon, <img>) retombe sur Arial.

Sortie (convention de fichiers TREK, cf. /app/public/) :
  text-light.svg  text-dark.svg          wordmark seul
  logo-light.svg  logo-dark.svg          icône soleil + wordmark
  icons/icon.svg  icon-dark.svg  icon-white.svg   favicon (soleil)
  icons/icon-192x192.png  icon-512x512.png  apple-touch-icon-180x180.png

Idempotent. Police téléchargée une fois dans /tmp.
"""
import os
import math
import subprocess
import urllib.request
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")
os.makedirs(ICONS, exist_ok=True)

FONT = "/tmp/MuseoModerno-800.ttf"
FONT_URL = ("https://raw.githubusercontent.com/google/fonts/main/ofl/"
            "museomoderno/MuseoModerno%5Bwght%5D.ttf")

# ---- Palette Yinda (extraite de l'apple-touch validé + festival) -----------
BG_DARK = "#0B0418"      # fond sombre (app icon, navbar dark)
BG_LIGHT = "#F7F8FA"     # fond clair
INK = "#1A1036"          # texte sur fond clair
PAPER = "#FFF7EC"        # texte sur fond sombre
SUN_CORE = "#FFEAA2"
SUN_MID = "#FF9324"
SUN_OUT = "#FE791A"
HOT = "#E5006D"          # rose festival
VIOLET = "#7A2BFF"

WORD = "Yinda"           # 'i' rendu via dotlessi + soleil en point


def ensure_font():
    if os.path.exists(FONT) and os.path.getsize(FONT) > 1000:
        return
    # Variable font -> on extrait l'instance wght=800
    raw = "/tmp/MuseoModerno-VF.ttf"
    urllib.request.urlretrieve(FONT_URL, raw)
    from fontTools.varLib.instancer import instantiateVariableFont
    vf = TTFont(raw)
    instantiateVariableFont(vf, {"wght": 800}, inplace=True)
    vf.save(FONT)


def sun_markup(cx, cy, r, prefix, rays=12, with_rays=True, mono=None,
               core=SUN_CORE, mid=SUN_MID, out=SUN_OUT, ray_color=SUN_OUT):
    """Soleil festival. Monochrome (mono=<couleur>) : disque plein + rayons
    détachés d'une seule teinte. Sinon : disque dégradé chaud."""
    body = []

    def rays_path():
        rl_in, rl_out, rw = r * 1.22, r * 1.66, r * 0.16
        seg = []
        for k in range(rays):
            a = (2 * math.pi * k) / rays
            bx1 = cx + math.cos(a - rw / r) * rl_in
            by1 = cy + math.sin(a - rw / r) * rl_in
            bx2 = cx + math.cos(a + rw / r) * rl_in
            by2 = cy + math.sin(a + rw / r) * rl_in
            tx = cx + math.cos(a) * rl_out
            ty = cy + math.sin(a) * rl_out
            seg.append(f'M{bx1:.2f} {by1:.2f} L{tx:.2f} {ty:.2f} '
                       f'L{bx2:.2f} {by2:.2f} Z')
        return " ".join(seg)

    if mono:
        if with_rays:
            body.append(f'<path d="{rays_path()}" fill="{mono}"/>')
        body.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
                    f'fill="{mono}"/>')
        return "", "".join(body)

    gid = f"sun_{prefix}"
    defs = (f'<defs><radialGradient id="{gid}" cx="0.42" cy="0.40" r="0.72">'
            f'<stop offset="0" stop-color="{core}"/>'
            f'<stop offset="0.55" stop-color="{mid}"/>'
            f'<stop offset="1" stop-color="{out}"/></radialGradient></defs>')
    if with_rays:
        body.append(f'<path d="{rays_path()}" fill="{ray_color}"/>')
    body.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
                f'fill="url(#{gid})"/>')
    body.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r*0.40:.2f}" '
                f'fill="{core}" fill-opacity="0.9"/>')
    return defs, "".join(body)


def wordmark_paths(fill, scale=0.1, baseline=86.0, x0=4.0):
    """Vectorise 'Yinda' (dotless i) en <path>. Renvoie (svg_fragment, width,
    i_center_x, x_top_y) pour positionner le soleil-point."""
    f = TTFont(FONT)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    hmtx = f["hmtx"]
    seq = ["Y", "dotlessi", "n", "d", "a"]
    adv_for = {
        "Y": hmtx[cmap[ord("Y")]][0],
        "dotlessi": hmtx["dotlessi"][0],
        "n": hmtx[cmap[ord("n")]][0],
        "d": hmtx[cmap[ord("d")]][0],
        "a": hmtx[cmap[ord("a")]][0],
    }
    penx = x0
    frags = []
    i_center = None
    track = 6.0  # léger tracking en px
    for gname in seq:
        spen = SVGPathPen(gs)
        tpen = TransformPen(spen, (scale, 0, 0, -scale, penx, baseline))
        gs[gname].draw(tpen)
        d = spen.getCommands()
        if d:
            frags.append(f'<path d="{d}" fill="{fill}"/>')
        if gname == "dotlessi":
            i_center = penx + (adv_for[gname] * scale) / 2.0
        penx += adv_for[gname] * scale + track
    width = penx - track + x0
    # haut du fût du i ~ x-height (520 upm) -> y px
    x_top_y = baseline - 520 * scale
    return "".join(frags), width, i_center, x_top_y


def build_text(fill, name):
    """Wordmark monochrome : soleil-point de la même teinte que le lettrage."""
    frag, width, icx, _ = wordmark_paths(fill)
    r = 6.8
    cy = 15.0
    _, sun = sun_markup(icx, cy, r, f"dot_{name}", rays=10, mono=fill)
    vb_w = math.ceil(width + 4)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w} 100" '
           f'width="{vb_w*2.3:.0f}" height="230" role="img" '
           f'aria-label="Yinda">{frag}{sun}</svg>')
    return svg


def build_logo(fill, name):
    """Emblème soleil + wordmark, tout monochrome (teinte = fill)."""
    icon_cx, icon_cy, icon_r = 42, 50, 27
    _, sun_i = sun_markup(icon_cx, icon_cy, icon_r, f"logo_{name}",
                          rays=12, mono=fill)
    frag, width, icx, _ = wordmark_paths(fill, x0=92.0)
    r = 6.8
    _, sun_d = sun_markup(icx, 15.0, r, f"logodot_{name}", rays=10, mono=fill)
    vb_w = math.ceil(width + 4)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w} 100" '
           f'width="{vb_w*2.3:.0f}" height="230" role="img" '
           f'aria-label="Yinda">{sun_i}{frag}{sun_d}</svg>')
    return svg


def build_icon(bg, sun_color, name):
    """Favicon carré 512 : soleil monochrome centré sur fond (ou transparent)."""
    cx = cy = 256
    r = 132
    _, sun = sun_markup(cx, cy, r, f"ic_{name}", rays=12, mono=sun_color)
    bg_rect = ""
    if bg:
        bg_rect = (f'<rect x="0" y="0" width="512" height="512" rx="112" '
                   f'fill="{bg}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
           f'width="512" height="512" role="img" aria-label="Yinda">'
           f'{bg_rect}{sun}</svg>')
    return svg


# ------------------------ PNG (Pillow, dessin direct) -----------------------
def lerp(c1, c2, t):
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))


def hx(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def draw_png(path, size, bg=None, sun="#FFF7EC"):
    """App icon : soleil monochrome (teinte `sun`) sur fond `bg` arrondi."""
    from PIL import Image, ImageDraw
    SS = 4  # supersampling
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg:
        rad = int(0.22 * S)
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=rad, fill=hx(bg))
    cx = cy = S / 2
    r = S * 0.255
    col = hx(sun)
    # rayons détachés
    rays = 12
    rl_in, rl_out, rw = r * 1.22, r * 1.66, r * 0.16
    for k in range(rays):
        a = 2 * math.pi * k / rays
        p1 = (cx + math.cos(a - rw / r) * rl_in, cy + math.sin(a - rw / r) * rl_in)
        p2 = (cx + math.cos(a + rw / r) * rl_in, cy + math.sin(a + rw / r) * rl_in)
        tip = (cx + math.cos(a) * rl_out, cy + math.sin(a) * rl_out)
        d.polygon([p1, tip, p2], fill=col)
    # disque plein monochrome
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    img = img.resize((size, size), Image.LANCZOS)
    img.save(path)


def w(path, content):
    with open(path, "w") as fh:
        fh.write(content + "\n")
    print("  wrote", os.path.relpath(path, HERE))


def main():
    ensure_font()
    # Wordmark monochrome (sur sombre = crème ; sur clair = encre)
    w(os.path.join(HERE, "text-light.svg"), build_text(PAPER, "tl"))
    w(os.path.join(HERE, "text-dark.svg"), build_text(INK, "td"))
    # Logo (emblème + wordmark), même règle monochrome
    w(os.path.join(HERE, "logo-light.svg"), build_logo(PAPER, "ll"))
    w(os.path.join(HERE, "logo-dark.svg"), build_logo(INK, "ld"))
    # Favicons — soleil noir sur clair/transparent, crème sur fond sombre
    w(os.path.join(ICONS, "icon.svg"), build_icon(None, INK, "plain"))
    w(os.path.join(ICONS, "icon-dark.svg"), build_icon(BG_DARK, PAPER, "dark"))
    w(os.path.join(ICONS, "icon-white.svg"), build_icon("#FFFFFF", INK, "white"))
    # PNG PWA / apple-touch — soleil crème sur fond sombre arrondi
    for nm, sz in [("icon-192x192.png", 192), ("icon-512x512.png", 512),
                   ("apple-touch-icon-180x180.png", 180)]:
        draw_png(os.path.join(ICONS, nm), sz, bg=BG_DARK, sun=PAPER)
        print(f"  wrote icons/{nm}")


if __name__ == "__main__":
    main()
