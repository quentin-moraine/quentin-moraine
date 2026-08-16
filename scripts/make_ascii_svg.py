"""Convertit la photo préparée en un portrait ASCII qui se tape tout seul.

Deux partis pris qui font la différence entre un portrait lisible et de la neige :

- **Monochrome.** Une seule couleur. La coloration par caractère est
  précisément ce qui fait ressembler la plupart des portraits ASCII à de la
  friture d'écran.
- **Fond effacé.** L'espace est en tête de la rampe, donc le fond blanc pur
  produit du vide et seul le sujet s'imprime.

Trois détails techniques que l'article d'origine n'aborde pas :

- `textLength` + `lengthAdjust="spacingAndGlyphs"` sur chaque ligne. Sans ça
  on suppose que la police monospace du lecteur a l'avance qu'on a prévue ;
  elle varie d'une machine à l'autre et le texte déborde du viewBox.
- Animation en **keyframes CSS et non en SMIL**, parce que SMIL ignore
  `prefers-reduced-motion`. L'état par défaut est le portrait fini ; le
  mouvement ne s'ajoute que pour qui ne l'a pas refusé.
- **Deux grilles de glyphes, une par thème.** Un portrait ASCII place des
  glyphes denses là où il y a de l'encre. Sur fond blanc l'encre est sombre,
  donc dense = ombre. Sur fond sombre l'encre devient claire : la même grille
  s'y lit en négatif, cheveux lumineux et visage sombre. Le thème sombre a
  donc sa propre grille, calculée avec la rampe inversée, et le masque du
  sujet empêche le fond d'y devenir la zone la plus dense de l'image.

Usage : python scripts/make_ascii_svg.py
        STATIC=1 python scripts/make_ascii_svg.py   (sans animation)
        PREVIEW=1 python scripts/make_ascii_svg.py  (rendu texte au terminal)
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

import theme

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "portrait-prepped.png"
MASK = ROOT / "assets" / "portrait-mask.png"
OUT = ROOT / "ascii-portrait.svg"

# Rampe de densité : clair (rare) -> sombre (dense).
# L'espace en tête est ce qui efface le fond.
RAMP = " .`:-=+*cs#%@"

COLS, ROWS = 92, 46  # un glyphe monospace fait ~2x plus haut que large,
#                      donc 92 x 0.5 = 46 : la grille reçoit un cadre carré.

FONT_SIZE = 12.0
CHAR_W = FONT_SIZE * 0.6  # avance nominale d'une monospace
CHAR_H = CHAR_W * 2  # hauteur de cellule, pour un ratio de 0,5
PAD = 10.0

# >1 éclaircit les demi-tons. Indispensable ici : à gamma 1 le visage sort en
# demi-teintes et les lunettes, sourcils et cheveux ne tranchent plus sur lui.
GAMMA = 1.7

ROW_DURATION = 0.45  # durée du balayage d'une ligne
ROW_STAGGER = 0.055  # décalage d'une ligne à la suivante


def downsample(image: np.ndarray) -> np.ndarray:
    """Ramène l'image à la grille de caractères, par moyenne de zone."""
    small = Image.fromarray(image, mode="L").resize((COLS, ROWS), Image.BOX)
    return np.asarray(small, dtype=np.float64) / 255.0


def to_ascii(values: np.ndarray, mask: np.ndarray, invert: bool) -> list[str]:
    """Mappe la grille de luminance sur la rampe de densité.

    `invert=False` (thème clair) : dense là où c'est sombre. Le fond, blanc pur,
    tombe naturellement sur l'espace.

    `invert=True` (thème sombre) : dense là où c'est clair, puisque les glyphes
    y sont lumineux. Le fond serait alors la zone la plus dense de l'image —
    d'où la pondération par le masque du sujet, qui le ramène à zéro.
    """
    density = (values if invert else 1.0 - values) ** GAMMA
    if invert:
        density *= mask
    idx = np.clip(np.rint(density * (len(RAMP) - 1)), 0, len(RAMP) - 1).astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]


def build_svg(light: list[str], dark: list[str], animated: bool) -> str:
    width = round(COLS * CHAR_W + 2 * PAD, 2)
    height = round(ROWS * CHAR_H + 2 * PAD, 2)
    text_len = round(COLS * CHAR_W, 2)

    motion = theme.motion_guard(
        f""".row {{
  animation: type {ROW_DURATION}s steps({COLS}, end) var(--d) both;
}}
.cursor {{
  animation: ride {ROW_DURATION}s steps({COLS}, end) var(--d) both;
}}
@keyframes type {{
  from {{ clip-path: inset(0 100% 0 0); }}
  to   {{ clip-path: inset(0 0 0 0); }}
}}
@keyframes ride {{
  0%   {{ transform: translateX(0); opacity: 1; }}
  92%  {{ opacity: 1; }}
  100% {{ transform: translateX({text_len}px); opacity: 0; }}
}}"""
    )

    styles = [
        theme.css_variables(),
        f"""    .row {{
      fill: var(--ink);
      font-size: {FONT_SIZE}px;
      white-space: pre;
      clip-path: inset(0 0 0 0);
    }}
    .cursor {{
      fill: var(--accent);
      opacity: 0;
    }}
    .art-dark {{ display: none; }}
    @media (prefers-color-scheme: dark) {{
      .art-light {{ display: none; }}
      .art-dark {{ display: block; }}
    }}""",
    ]
    if animated:
        styles.append(motion)

    parts = [
        theme.svg_header(
            int(width),
            int(height),
            "ASCII portrait of Quentin Moraine",
            "Monochrome ASCII-art portrait, printed line by line, "
            "generated from a photograph.",
        ),
        "  <style>\n" + "\n".join(styles) + "\n  </style>\n",
    ]

    for variant, lines in (("art-light", light), ("art-dark", dark)):
        parts.append(f'  <g class="{variant}">\n')
        for i, line in enumerate(lines):
            y = round(PAD + (i + 0.8) * CHAR_H, 2)
            delay = round(i * ROW_STAGGER, 3)
            parts.append(
                f'    <text class="row" x="{PAD}" y="{y}" '
                f'textLength="{text_len}" lengthAdjust="spacingAndGlyphs" '
                f'xml:space="preserve" style="--d:{delay}s">{theme.escape(line)}</text>\n'
            )
            if animated:
                parts.append(
                    f'    <rect class="cursor" x="{PAD}" y="{round(y - CHAR_H * 0.72, 2)}" '
                    f'width="{round(CHAR_W, 2)}" height="{round(CHAR_H * 0.78, 2)}" '
                    f'style="--d:{delay}s"/>\n'
                )
        parts.append("  </g>\n")

    parts.append("</svg>\n")
    return "".join(parts)


def main() -> None:
    for path in (SRC, MASK):
        if not path.exists():
            raise SystemExit(f"{path.name} manquant — lancer d'abord prep_photo.py")

    values = downsample(np.asarray(Image.open(SRC).convert("L")))
    mask = downsample(np.asarray(Image.open(MASK).convert("L")))

    light = to_ascii(values, mask, invert=False)
    dark = to_ascii(values, mask, invert=True)

    if os.environ.get("PREVIEW"):
        which = os.environ["PREVIEW"]
        lines = dark if which == "dark" else light
        print("\n".join(lines))
        used = sorted({c for line in lines for c in line}, key=RAMP.index)
        print(f"\ngrille {COLS}x{ROWS} | variante {'sombre' if which == 'dark' else 'claire'}"
              f" | glyphes utilisés : {len(used)}/{len(RAMP)} -> {''.join(used)!r}")
        return

    svg = build_svg(light, dark, animated=not os.environ.get("STATIC"))
    OUT.write_text(svg, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}  {len(svg) / 1024:.1f} Ko  "
          f"{int(COLS * CHAR_W + 2 * PAD)}x{int(ROWS * CHAR_H + 2 * PAD)}  "
          f"(2 grilles : claire + sombre)")


if __name__ == "__main__":
    main()
