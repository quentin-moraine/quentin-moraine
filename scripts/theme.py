"""Palette partagée et helpers SVG communs aux trois modules du profil.

Un seul endroit définit les couleurs et le mécanisme clair/sombre. Les trois
générateurs (portrait, carte, heatmap) importent d'ici : sans ça ils divergent
au premier ajustement.

Deux contraintes portent tout ce fichier :

1. GitHub sert le README en thème clair OU sombre selon le lecteur, et un SVG
   inclus via <img> ne peut pas le savoir autrement qu'avec `prefers-color-scheme`.
2. L'animation doit être une *amélioration* d'un état déjà lisible, jamais une
   condition d'affichage. D'où `prefers-reduced-motion: no-preference` : par
   défaut tout est visible et figé, le mouvement ne s'ajoute que si le lecteur
   ne l'a pas refusé. C'est aussi pourquoi on n'utilise pas SMIL, qui ignore
   les media queries.
"""

# --- Fonds de référence GitHub (pour la vérification de contraste) -----------

BG_LIGHT = "#ffffff"
BG_DARK = "#0d1117"

# --- Rôles de couleur -------------------------------------------------------
# `ink`   : texte principal, portrait ASCII
# `dim`   : texte secondaire, labels, légende
# `faint` : filets, séparateurs
# `accent`: le `$` du prompt et les valeurs mises en avant

LIGHT = {
    "ink": "#1f2328",
    "dim": "#59636e",
    "faint": "#d1d9e0",
    "accent": "#1a7f37",
}

DARK = {
    "ink": "#e6edf3",
    "dim": "#9198a1",
    "faint": "#3d444d",
    "accent": "#3fb950",
}

# Échelle de la heatmap, 5 niveaux (0 = aucune contribution).
# Ce sont les échelles réelles de GitHub : la grille doit se lire
# instantanément comme un graphe de contributions, pas comme une imitation.
HEAT_LIGHT = ["#ebedf0", "#aceebb", "#4ac26b", "#2da44e", "#116329"]
HEAT_DARK = ["#151b23", "#033a16", "#196c2e", "#2ea043", "#56d364"]

# Pile monospace : aucune police externe n'est chargeable depuis un SVG sur
# GitHub (CSP). On se rabat sur ce que la machine du lecteur possède déjà.
MONO = (
    "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
    "'Liberation Mono', monospace"
)


# --- Contraste --------------------------------------------------------------


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(fg: str, bg: str) -> float:
    """Ratio de contraste WCAG 2.1 entre deux couleurs hex."""
    a, b = relative_luminance(fg), relative_luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


# --- Fragments SVG ----------------------------------------------------------


def css_variables() -> str:
    """Bloc `:root` qui bascule les variables de couleur selon le thème."""
    light = "\n".join(f"      --{k}: {v};" for k, v in LIGHT.items())
    dark = "\n".join(f"        --{k}: {v};" for k, v in DARK.items())
    heat_light = "\n".join(
        f"      --heat-{i}: {c};" for i, c in enumerate(HEAT_LIGHT)
    )
    heat_dark = "\n".join(f"        --heat-{i}: {c};" for i, c in enumerate(HEAT_DARK))
    return (
        "    :root {\n"
        f"{light}\n{heat_light}\n"
        "    }\n"
        "    @media (prefers-color-scheme: dark) {\n"
        "      :root {\n"
        f"{dark}\n{heat_dark}\n"
        "      }\n"
        "    }"
    )


def motion_guard(rules: str) -> str:
    """Enveloppe des règles d'animation pour qu'elles ne s'appliquent qu'aux
    lecteurs qui n'ont pas demandé la réduction des animations.

    L'état par défaut du SVG doit être l'état *final* (contenu visible). Ces
    règles ne font que rejouer l'arrivée. Un lecteur en `reduce`, un moteur de
    rendu sans animation ou un onglet en arrière-plan voient le résultat fini
    plutôt qu'un cadre vide.
    """
    indented = "\n".join("  " + line if line.strip() else line for line in rules.splitlines())
    return (
        "    @media (prefers-reduced-motion: no-preference) {\n"
        f"{indented}\n"
        "    }"
    )


def svg_header(width: int, height: int, title: str, desc: str) -> str:
    """Ouvre un SVG accessible et correctement dimensionné.

    `role="img"` + <title>/<desc> : le README l'inclut via <img>, dont le alt
    ne décrit que le fichier. Le contenu textuel réel, lui, vit ici.
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-labelledby="title desc" '
        f'font-family="{MONO}">\n'
        f"  <title id=\"title\">{title}</title>\n"
        f"  <desc id=\"desc\">{desc}</desc>\n"
    )


def escape(text: str) -> str:
    """Échappe le texte destiné à un nœud SVG."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    # Vérification de contraste — exécuter après toute retouche de palette.
    print(f"{'paire':<28} {'ratio':>7}  seuil  verdict")
    print("-" * 56)
    checks = [
        ("light ink / blanc", LIGHT["ink"], BG_LIGHT, 4.5),
        ("light dim / blanc", LIGHT["dim"], BG_LIGHT, 4.5),
        ("light accent / blanc", LIGHT["accent"], BG_LIGHT, 4.5),
        ("dark ink / #0d1117", DARK["ink"], BG_DARK, 4.5),
        ("dark dim / #0d1117", DARK["dim"], BG_DARK, 4.5),
        ("dark accent / #0d1117", DARK["accent"], BG_DARK, 4.5),
        ("heat L4 / blanc", HEAT_LIGHT[4], BG_LIGHT, 3.0),
        ("heat D4 / #0d1117", HEAT_DARK[4], BG_DARK, 3.0),
    ]
    worst_ok = True
    for label, fg, bg, threshold in checks:
        ratio = contrast_ratio(fg, bg)
        ok = ratio >= threshold
        worst_ok &= ok
        print(f"{label:<28} {ratio:>6.2f}:1  {threshold:>4}  {'OK' if ok else 'ECHEC'}")
    print("\n" + ("Toutes les paires passent." if worst_ok else "AU MOINS UNE PAIRE ECHOUE."))
