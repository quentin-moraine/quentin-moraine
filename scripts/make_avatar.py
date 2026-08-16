"""Compose l'avatar du compte GitHub à partir de la même photo que le portrait.

⚠️ **L'API GitHub ne permet pas de définir un avatar de compte.** Il n'existe
aucun endpoint REST pour ça. Ce script produit le fichier ; le dépôt se fait à
la main dans Settings → Profile → Edit picture.

Deux contraintes dictent la composition, et aucune ne vient de l'affichage en
grand :

1. **L'avatar est rogné en cercle.** Les coins sont perdus, et un sujet centré
   géométriquement paraît tomber vers le bas. D'où le centrage *optique* :
   sommet du crâne à 15 % de la hauteur.

2. **Il est surtout vu à 26 px**, dans les listes de commits, d'issues et de
   revues. C'est cette taille qui décide, pas la page de profil. Un fond clair
   y fait disparaître la chemise blanche et il ne reste qu'une tête flottante —
   raison pour laquelle le fond est sombre.

On **compose sur un canevas** plutôt que de recadrer la photo : recadrer
contraint le cadrage aux bords de l'original (ici seulement 49 px au-dessus des
cheveux), composer laisse choisir librement l'échelle et la position.

Usage : python scripts/make_avatar.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from prep_photo import DEFAULT_SOURCE, subject_metrics

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "avatar.png"

SIZE = 1000  # net sur écran haute densité ; GitHub n'affiche jamais plus de 460
BACKGROUND = (33, 38, 45)  # #21262d — reste un disque distinct dans les deux thèmes

HEAD_RATIO = 0.60  # part de la hauteur du canevas occupée par la tête
HEAD_TOP = 0.15  # position du sommet du crâne, pour le centrage optique


def main() -> None:
    if not DEFAULT_SOURCE.exists():
        raise SystemExit(f"Photo introuvable : {DEFAULT_SOURCE}")

    src = Image.open(DEFAULT_SOURCE).convert("RGBA")
    m = subject_metrics(np.array(src)[..., 3])

    scale = (SIZE * HEAD_RATIO) / m["head_h"]
    subject = src.resize(
        (round(src.width * scale), round(src.height * scale)), Image.LANCZOS
    )

    canvas = Image.new("RGBA", (SIZE, SIZE), BACKGROUND + (255,))
    canvas.alpha_composite(
        subject,
        (
            SIZE // 2 - round(m["head_cx"] * scale),
            round(SIZE * HEAD_TOP) - round(m["head_top"] * scale),
        ),
    )

    OUT.parent.mkdir(exist_ok=True)
    canvas.convert("RGB").save(OUT, optimize=True)
    print(f"{OUT.relative_to(ROOT)}  {SIZE}x{SIZE}  {OUT.stat().st_size / 1024:.0f} Ko")
    print("À déposer à la main : Settings → Profile → Edit picture (l'API ne le permet pas).")


if __name__ == "__main__":
    main()
