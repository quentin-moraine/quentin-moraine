"""Compose la carte d'information façon `neofetch`.

Le contenu est écrit à la main ici, pas dérivé de l'API GitHub : la heatmap
couvre déjà les chiffres, cette carte est là pour ce que les chiffres ne disent
pas. En anglais — la cible est Cranfield et les recruteurs internationaux.

Comme pour le portrait, chaque ligne porte `textLength` : la carte doit occuper
exactement la même boîte quelle que soit la monospace résolue chez le lecteur,
sinon la mise en page à deux colonnes du README se décale.

Usage : python scripts/make_info_card.py
        STATIC=1 python scripts/make_info_card.py   (sans animation)
"""

from __future__ import annotations

import os
from pathlib import Path

import theme

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "info-card.svg"

PROMPT = "quentin@github"

# (label, valeur). Un label vide continue le bloc précédent.
ROWS: list[tuple[str, str]] = [
    ("Now", "MSc Robotics — Cranfield University (2026–27)"),
    ("Prev", "General engineering — ICAM Strasbourg (2022–27)"),
    ("", "Exchange semester — MCAST, Malta (2023)"),
    ("Focus", "Modern C++ for robotics · perception · control · embedded"),
    ("Lang", "C++ · Python · C · MATLAB"),
    ("Tools", "OpenCV · YOLO/Ultralytics · NumPy · Git · Linux"),
    ("Boards", "Raspberry Pi · ESP32 · Arduino"),
    ("CAD/EDA", "SolidWorks · Inventor · KiCad · EasyEDA"),
    ("Built", "Vision-based screw sorter — YOLO11 on Pi 5, >95% acc."),
    ("", "team lead · 9-month engineering project"),
    ("", "Budget tracker — C++, written from scratch"),
    # Aucune stack annoncée pour les deux applis qui suivent : elles ont été
    # largement générées par IA. Revendiquer Next.js ou Swift serait une ligne
    # indéfendable en entretien. On les décrit par ce qu'elles font.
    ("", "Finanza — personal finance app, local-only by design"),
    ("", "JARVIS — desktop assistant running a local LLM"),
    # Allemand et espagnol sont à A2 sur le CV. Une langue listée sans niveau
    # laisse supposer un niveau de travail ; l'annoter « A2 » la disqualifie
    # elle-même. Deux langues solides valent mieux que quatre lignes molles.
    ("Speaks", "FR native · EN C1 (TOEIC 950)"),
]

WIDTH = 700
FONT_SIZE = 14.0
CHAR_W = FONT_SIZE * 0.6
PAD_X = 30.0
LABEL_X = PAD_X
VALUE_X = PAD_X + 13 * CHAR_W
# Interligne calé pour que la carte, affichée à 470 px dans le README, tombe à
# la même hauteur que le portrait affiché à 370 px. À réajuster si on ajoute ou
# retire des lignes, sinon les deux colonnes se décalent.
LINE_H = 31.0

TITLE_SIZE = 18.0
TITLE_Y = 52.0
RULE_Y = 72.0
FIRST_ROW_Y = 112.0

ROW_DURATION = 0.5
ROW_STAGGER = 0.07
# Ease-out quart : l'arrivée décélère franchement, sans rebond.
EASING = "cubic-bezier(0.25, 1, 0.5, 1)"


def text(cls: str, x: float, y: float, content: str, size: float, extra: str = "") -> str:
    """Nœud texte à largeur verrouillée."""
    if not content:
        return ""
    length = round(len(content) * size * 0.6, 2)
    return (
        f'  <text class="{cls}" x="{x}" y="{y}" '
        f'textLength="{length}" lengthAdjust="spacingAndGlyphs" '
        f'xml:space="preserve"{extra}>{theme.escape(content)}</text>\n'
    )


def build_svg(animated: bool) -> str:
    height = round(FIRST_ROW_Y + (len(ROWS) - 1) * LINE_H + 42)

    motion = theme.motion_guard(
        f""".line {{
  animation: rise {ROW_DURATION}s {EASING} var(--d) both;
}}
@keyframes rise {{
  from {{ opacity: 0; transform: translateY(7px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}"""
    )

    styles = [
        theme.css_variables(),
        f"""    text {{ font-size: {FONT_SIZE}px; }}
    .title {{ fill: var(--accent); font-size: {TITLE_SIZE}px; font-weight: 600; }}
    .label {{ fill: var(--dim); }}
    .value {{ fill: var(--ink); }}
    .rule  {{ stroke: var(--faint); stroke-width: 1; }}
    .line  {{ opacity: 1; }}""",
    ]
    if animated:
        styles.append(motion)

    parts = [
        theme.svg_header(
            WIDTH,
            height,
            "Carte d'information de Quentin Moraine",
            "Panneau façon neofetch : formation, domaines, langages, outils, "
            "projets et langues parlées.",
        ),
        "  <style>\n" + "\n".join(styles) + "\n  </style>\n",
    ]

    def delay(i: int) -> str:
        return f' style="--d:{round(i * ROW_STAGGER, 3)}s"'

    parts.append(
        f'  <g class="line"{delay(0)}>\n  '
        + text("title", LABEL_X, TITLE_Y, PROMPT, TITLE_SIZE).lstrip()
        + "  </g>\n"
    )
    parts.append(
        f'  <g class="line"{delay(1)}>\n'
        f'    <line class="rule" x1="{PAD_X}" y1="{RULE_Y}" '
        f'x2="{WIDTH - PAD_X}" y2="{RULE_Y}"/>\n'
        "  </g>\n"
    )

    for i, (label, value) in enumerate(ROWS):
        y = round(FIRST_ROW_Y + i * LINE_H, 2)
        inner = text("label", LABEL_X, y, label, FONT_SIZE) + text(
            "value", VALUE_X, y, value, FONT_SIZE
        )
        parts.append(f'  <g class="line"{delay(i + 2)}>\n' + inner + "  </g>\n")

    parts.append("</svg>\n")
    return "".join(parts)


def main() -> None:
    svg = build_svg(animated=not os.environ.get("STATIC"))
    OUT.write_text(svg, encoding="utf-8")
    widest = max(len(v) for _, v in ROWS)
    overflow = VALUE_X + widest * CHAR_W
    print(f"{OUT.relative_to(ROOT)}  {len(svg) / 1024:.1f} Ko  "
          f"{WIDTH}x{round(FIRST_ROW_Y + (len(ROWS) - 1) * LINE_H + 42)}")
    print(f"ligne la plus longue : {widest} car. -> x={overflow:.0f} "
          f"(marge droite {WIDTH - PAD_X - overflow:.0f} px)")


if __name__ == "__main__":
    main()
