"""Prépare la photo source pour la conversion en ASCII.

Trois problèmes à régler avant de pouvoir mapper des pixels sur des glyphes :

1. **Le cadrage.** Sur la photo d'origine le visage n'occupe qu'un tiers du
   cadre. À ~92x46 caractères il serait illisible. On recadre tête + épaules.
   Le recadrage est *dérivé du canal alpha*, pas codé en dur : on repère le
   sommet du crâne, le cou (largeur minimale) et la ligne d'épaules, puis on
   compose une fenêtre carrée autour. Changer de photo ne casse rien tant que
   le sujet est détouré.

2. **Le contraste.** L'éclairage est frontal et plat, peau claire sur fond
   clair : une conversion directe donne une silhouette floue. On applique un
   CLAHE (égalisation d'histogramme adaptative à contraste limité), qui
   travaille par tuiles et fait donc ressortir le modelé local au lieu
   d'écraser toute l'image sur une seule courbe.

3. **Le fond.** Il doit finir en blanc *pur* pour tomber sur l'espace en tête
   de la rampe ASCII. On l'exclut aussi du calcul du CLAHE : une grande plage
   uniforme fausserait les histogrammes des tuiles qui la touchent.

Sortie : assets/portrait-source.png (recadrage RGBA, source de vérité versionnée)
         assets/portrait-prepped.png (niveaux de gris, entrée de make_ascii_svg)
         assets/portrait-mask.png (masque du sujet, blanc = sujet)

Le masque est indispensable au thème sombre : la rampe y est inversée (dense =
clair) et sans masque le fond blanc deviendrait la zone la plus dense de
l'image, remplissant tout le cadre de `@`.

Usage : python scripts/prep_photo.py [chemin/vers/photo]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path.home() / "Documents/Projets/portfolio/assets/portrait.webp"

# Marges du recadrage, exprimées en fraction de la hauteur de tête — donc
# stables si la photo change de résolution ou de cadrage.
HEADROOM = 0.06  # espace au-dessus du crâne
SHOULDER_DROP = 0.34  # descente sous la ligne d'épaules

CLAHE_TILES = 8
CLAHE_CLIP = 2.5

# Fondu vers le blanc sur le bas de l'image. La chemise rayée est du détail
# haute fréquence : à 92 colonnes elle ne produit que du bruit, qui concurrence
# le visage au lieu de le servir. Le fondu la dissout — c'est le geste du
# portrait studio, pas un contournement.
FADE_START = 0.68  # hauteur relative où le fondu commence
FADE_STRENGTH = 0.85  # 1.0 = blanc pur en bas de l'image

# Le masque se fond plus tôt et plus fort que l'image, pour une raison qui
# n'apparaît qu'en thème sombre : la rampe y est inversée, et la chemise —
# blanche, donc claire — y devient la zone la plus DENSE de l'image. Le fondu
# de l'image ne la calme pas, il l'aggrave. Seul le masque la fait disparaître.
MASK_FADE_START = 0.52
MASK_FADE_STRENGTH = 1.0


def subject_metrics(alpha: np.ndarray) -> dict[str, int]:
    """Repère crâne, cou et épaules à partir du masque de détourage."""
    mask = alpha > 128
    widths = mask.sum(axis=1)
    rows = np.nonzero(widths > 20)[0]
    if rows.size == 0:
        raise SystemExit("Aucun sujet détecté : la photo a-t-elle bien un fond détouré ?")

    head_top, bottom = int(rows[0]), int(rows[-1])

    # Largeur de tête : maximum sur le quart supérieur du sujet. C'est l'unité
    # de mesure de tout le reste — se caler dessus plutôt que sur la hauteur
    # totale rend la détection indépendante du cadrage de la photo (buste,
    # plan large, plein pied).
    quarter = head_top + max(1, (bottom - head_top) // 4)
    head_max_w = int(widths[head_top:quarter].max())

    # Le cou : minimum de largeur dans la bande où il se trouve forcément,
    # soit entre 0,9 et 2,2 largeurs de tête sous le crâne. Sans cette borne
    # supérieure, l'évasement des épaules est pris pour le maximum de la tête
    # et la détection part en vrille.
    lo = min(head_top + round(0.9 * head_max_w), bottom - 1)
    hi = min(head_top + round(2.2 * head_max_w), bottom)
    neck = lo + int(np.argmin(widths[lo:hi])) if hi > lo else lo
    neck_w = int(widths[neck])

    # Les épaules commencent quand la largeur dépasse nettement celle du cou.
    below = widths[neck:]
    flare = np.nonzero(below > neck_w * 1.5)[0]
    shoulders = neck + int(flare[0]) if flare.size else neck

    head_h = neck - head_top
    head_cols = np.nonzero(mask[head_top:neck].any(axis=0))[0]
    head_cx = int((head_cols[0] + head_cols[-1]) // 2)

    return {
        "head_top": head_top,
        "head_max_w": head_max_w,
        "neck": neck,
        "neck_w": neck_w,
        "shoulders": shoulders,
        "head_h": head_h,
        "head_cx": head_cx,
    }


def square_crop_box(m: dict[str, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Fenêtre carrée tête + épaules, recentrée si elle sort de l'image.

    Carrée parce que la grille ASCII fait 92x46 caractères et qu'un glyphe
    monospace est à peu près deux fois plus haut que large : 92 x 0.5 = 46.
    Un cadre carré arrive donc sans déformation.
    """
    w, h = size
    top = m["head_top"] - round(HEADROOM * m["head_h"])
    bottom = m["shoulders"] + round(SHOULDER_DROP * m["head_h"])
    side = bottom - top

    left = m["head_cx"] - side // 2
    left = max(0, min(left, w - side)) if side <= w else 0
    top = max(0, min(top, h - side)) if side <= h else 0
    return (left, top, left + side, top + side)


def clahe(gray: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Égalisation d'histogramme adaptative à contraste limité.

    Découpe l'image en tuiles, construit une LUT par tuile à partir d'un
    histogramme écrêté (le clip évite d'amplifier le bruit des zones plates),
    puis interpole bilinéairement entre les quatre LUT voisines pour ne pas
    laisser apparaître les frontières de tuiles.

    `valid` masque les pixels à ignorer dans les histogrammes — ici le fond,
    dont l'aplat uniforme écraserait les tuiles de bord.
    """
    h, w = gray.shape
    ty, tx = CLAHE_TILES, CLAHE_TILES
    th, tw = h / ty, w / tx

    luts = np.zeros((ty, tx, 256), dtype=np.float64)
    for j in range(ty):
        for i in range(tx):
            y0, y1 = int(j * th), int((j + 1) * th)
            x0, x1 = int(i * tw), int((i + 1) * tw)
            tile = gray[y0:y1, x0:x1]
            keep = valid[y0:y1, x0:x1]
            values = tile[keep] if keep.any() else tile.ravel()

            hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
            limit = max(1.0, CLAHE_CLIP * values.size / 256)
            excess = np.maximum(hist - limit, 0).sum()
            hist = np.minimum(hist, limit) + excess / 256  # redistribution uniforme

            cdf = np.cumsum(hist)
            cdf /= cdf[-1] if cdf[-1] else 1
            luts[j, i] = cdf * 255

    # Coordonnées du pixel dans le repère des centres de tuiles.
    yy = np.clip(np.arange(h) / th - 0.5, 0, ty - 1)
    xx = np.clip(np.arange(w) / tw - 0.5, 0, tx - 1)
    j0, i0 = yy.astype(int), xx.astype(int)
    j1, i1 = np.minimum(j0 + 1, ty - 1), np.minimum(i0 + 1, tx - 1)
    fy, fx = (yy - j0)[:, None], (xx - i0)[None, :]

    g = gray.astype(int)
    tl = luts[j0[:, None], i0[None, :], g]
    tr = luts[j0[:, None], i1[None, :], g]
    bl = luts[j1[:, None], i0[None, :], g]
    br = luts[j1[:, None], i1[None, :], g]

    out = (
        tl * (1 - fy) * (1 - fx)
        + tr * (1 - fy) * fx
        + bl * fy * (1 - fx)
        + br * fy * fx
    )
    return np.clip(out, 0, 255).astype(np.uint8)


def fade_bottom(gray: np.ndarray, start: float, strength: float, toward=255) -> np.ndarray:
    """Fond progressivement le bas de l'image vers `toward`."""
    h = gray.shape[0]
    ramp = np.clip((np.arange(h) / h - start) / (1 - start), 0, 1)
    t = (ramp * strength)[:, None]
    return np.clip(gray * (1 - t) + toward * t, 0, 255).astype(np.uint8)


def stretch(gray: np.ndarray, valid: np.ndarray, low=1.0, high=99.0) -> np.ndarray:
    """Étire la dynamique du sujet sur toute la plage 0-255."""
    values = gray[valid]
    if values.size == 0:
        return gray
    lo, hi = np.percentile(values, [low, high])
    if hi <= lo:
        return gray
    return np.clip((gray.astype(np.float64) - lo) * 255 / (hi - lo), 0, 255).astype(np.uint8)


def main() -> None:
    source = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        raise SystemExit(f"Photo introuvable : {source}")

    img = Image.open(source).convert("RGBA")
    alpha = np.array(img)[..., 3]
    m = subject_metrics(alpha)
    box = square_crop_box(m, img.size)

    print(f"source            {source}  {img.size[0]}x{img.size[1]}")
    print(f"sommet du crane   y={m['head_top']}")
    print(f"cou               y={m['neck']}  (largeur {m['neck_w']} px)")
    print(f"epaules           y={m['shoulders']}")
    print(f"hauteur de tete   {m['head_h']} px")
    print(f"recadrage         {box}  -> {box[2]-box[0]}x{box[3]-box[1]}")

    cropped = img.crop(box)
    (ROOT / "assets").mkdir(exist_ok=True)
    cropped.save(ROOT / "assets" / "portrait-source.png")

    # Le sujet, aplati sur blanc puis converti en gris.
    a = np.array(cropped)[..., 3]
    valid = a > 128
    flat = Image.new("RGBA", cropped.size, (255, 255, 255, 255))
    flat.alpha_composite(cropped)
    gray = np.array(flat.convert("L"))

    gray = clahe(gray, valid)
    gray = stretch(gray, valid)
    gray = fade_bottom(gray, FADE_START, FADE_STRENGTH)
    gray[~valid] = 255  # fond en blanc pur -> espace dans la rampe ASCII

    out = ROOT / "assets" / "portrait-prepped.png"
    Image.fromarray(gray, mode="L").save(out)

    mask = np.where(valid, 255, 0).astype(np.uint8)
    mask = fade_bottom(mask, MASK_FADE_START, MASK_FADE_STRENGTH, toward=0)
    Image.fromarray(mask, mode="L").save(ROOT / "assets" / "portrait-mask.png")

    subject = gray[valid]
    print(f"tons du sujet     min={subject.min()} median={int(np.median(subject))} max={subject.max()}")
    print(f"ecrit             {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
