"""Rend le calendrier de contributions en SVG animé.

Grille classique 53 semaines x 7 jours, cases arrondies, révélation en diagonale
puis figée. On garde volontairement l'échelle de couleurs réelle de GitHub :
la grille doit se lire instantanément comme un graphe de contributions, pas
comme une imitation stylisée.

Pied de page **sobre** : total de l'année et légende `Less -> More`, rien de
plus. Les « current streak / longest streak / best day » de l'article n'ont de
sens qu'avec du volume ; sur un compte jeune ils soulignent la rareté au lieu
de la masquer. À réintroduire quand la grille se remplira.

Usage : python scripts/render_heatmap_svg.py
        STATIC=1 python scripts/render_heatmap_svg.py   (sans animation)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import theme

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "contributions.json"
OUT = ROOT / "contrib-heatmap.svg"

CELL = 11.0
GAP = 4.0
PITCH = CELL + GAP
RADIUS = 2.5

PAD = 16.0
GUTTER = 30.0  # colonne des jours de semaine
MONTH_H = 20.0  # bandeau des mois
FOOT_GAP = 22.0

FONT_SIZE = 11.0
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}  # comme GitHub : une ligne sur deux

CELL_DURATION = 0.42
DIAGONAL_STEP = 0.022  # décalage d'une diagonale à la suivante
EASING = "cubic-bezier(0.25, 1, 0.5, 1)"


def grid_row(day: date) -> int:
    """Index de ligne, dimanche en haut — la convention de GitHub."""
    return (day.weekday() + 1) % 7


def layout(days: list[dict]) -> tuple[list[dict], int]:
    """Place chaque jour en (colonne, ligne) et renvoie le nombre de colonnes."""
    first = date.fromisoformat(days[0]["date"])
    origin = first - timedelta(days=grid_row(first))

    placed = []
    for entry in days:
        day = date.fromisoformat(entry["date"])
        placed.append(
            {
                **entry,
                "col": (day - origin).days // 7,
                "row": grid_row(day),
                "day": day,
            }
        )
    return placed, max(p["col"] for p in placed) + 1


def month_labels(placed: list[dict]) -> list[tuple[int, str]]:
    """Un label par mois, posé sur la colonne où le mois commence.

    On saute un mois dont la première colonne est déjà occupée par le
    précédent : sur les bords de grille deux mois peuvent tomber sur la même
    semaine et les labels se chevaucheraient.
    """
    seen: dict[tuple[int, int], int] = {}
    for p in sorted(placed, key=lambda p: p["day"]):
        seen.setdefault((p["day"].year, p["day"].month), p["col"])

    labels, last_col = [], -2
    for (_, month), col in sorted(seen.items(), key=lambda kv: seen[kv[0]]):
        if col - last_col >= 3:
            labels.append((col, MONTHS[month - 1]))
            last_col = col
    return labels


def build_svg(data: dict, animated: bool) -> str:
    placed, cols = layout(data["days"])

    grid_x = PAD + GUTTER
    grid_y = PAD + MONTH_H
    grid_w = cols * PITCH - GAP
    grid_h = 7 * PITCH - GAP

    width = round(grid_x + grid_w + PAD)
    foot_y = grid_y + grid_h + FOOT_GAP + FONT_SIZE
    height = round(foot_y + PAD)

    motion = theme.motion_guard(
        f""".cell {{
  animation: pop {CELL_DURATION}s {EASING} var(--d) both;
  transform-box: fill-box;
  transform-origin: center;
}}
@keyframes pop {{
  from {{ opacity: 0; transform: translateY(-5px) scale(0.72); }}
  to   {{ opacity: 1; transform: translateY(0) scale(1); }}
}}"""
    )

    styles = [
        theme.css_variables(),
        f"""    text {{ font-size: {FONT_SIZE}px; fill: var(--dim); }}
    .total {{ fill: var(--ink); }}
    .cell {{ opacity: 1; }}
    .l0 {{ fill: var(--heat-0); }}
    .l1 {{ fill: var(--heat-1); }}
    .l2 {{ fill: var(--heat-2); }}
    .l3 {{ fill: var(--heat-3); }}
    .l4 {{ fill: var(--heat-4); }}""",
    ]
    if animated:
        styles.append(motion)

    total = data["total"]
    plural = "" if total == 1 else "s"
    parts = [
        theme.svg_header(
            width,
            height,
            f"GitHub contribution calendar for {data['user']}",
            f"{total} contribution{plural} over the past year, "
            f"from {data['range']['start']} to {data['range']['end']}, "
            "laid out as 53 weeks by 7 days.",
        ),
        "  <style>\n" + "\n".join(styles) + "\n  </style>\n",
    ]

    for col, name in month_labels(placed):
        parts.append(
            f'  <text x="{round(grid_x + col * PITCH, 2)}" '
            f'y="{round(grid_y - 7, 2)}">{name}</text>\n'
        )

    for row, name in WEEKDAYS.items():
        parts.append(
            f'  <text x="{PAD}" y="{round(grid_y + row * PITCH + CELL - 1.5, 2)}">'
            f"{name}</text>\n"
        )

    parts.append("  <g>\n")
    for p in placed:
        x = round(grid_x + p["col"] * PITCH, 2)
        y = round(grid_y + p["row"] * PITCH, 2)
        # Révélation en diagonale : le décalage suit col + row, donc la vague
        # traverse la grille du coin haut-gauche vers le bas-droit.
        style = (
            f' style="--d:{round((p["col"] + p["row"]) * DIAGONAL_STEP, 3)}s"'
            if animated
            else ""
        )
        # Pas de <title> par case : le README inclut ce SVG via <img>, donc
        # sans interaction ni infobulle. 365 titres seraient du poids mort.
        # Le résumé lisible vit dans le <desc> du document.
        parts.append(
            f'    <rect class="cell l{p["level"]}" x="{x}" y="{y}" '
            f'width="{CELL}" height="{CELL}" rx="{RADIUS}"{style}/>\n'
        )
    parts.append("  </g>\n")

    # Pied : total à gauche, légende à droite.
    parts.append(
        f'  <text class="total" x="{PAD}" y="{round(foot_y, 2)}">'
        f"{total:,} contribution{plural} in the last year</text>\n"
    )

    legend_w = 5 * PITCH - GAP
    legend_x = width - PAD - legend_w - 4 * FONT_SIZE * 0.6 - 6
    parts.append(
        f'  <text x="{round(legend_x - 6, 2)}" y="{round(foot_y, 2)}" '
        f'text-anchor="end">Less</text>\n'
    )
    for level in range(5):
        parts.append(
            f'    <rect class="l{level}" x="{round(legend_x + level * PITCH, 2)}" '
            f'y="{round(foot_y - CELL + 2, 2)}" width="{CELL}" height="{CELL}" '
            f'rx="{RADIUS}"/>\n'
        )
    parts.append(
        f'  <text x="{round(legend_x + legend_w + 6, 2)}" y="{round(foot_y, 2)}">'
        f"More</text>\n"
    )

    parts.append("</svg>\n")
    return "".join(parts)


def main() -> None:
    if not SRC.exists():
        raise SystemExit("data/contributions.json manquant — lancer fetch_contributions.py")

    data = json.loads(SRC.read_text(encoding="utf-8"))
    svg = build_svg(data, animated=not os.environ.get("STATIC"))
    OUT.write_text(svg, encoding="utf-8")

    _, cols = layout(data["days"])
    print(f"{OUT.relative_to(ROOT)}  {len(svg) / 1024:.1f} Ko  "
          f"{cols} semaines, {len(data['days'])} jours, {data['total']} contributions")


if __name__ == "__main__":
    main()
