"""Récupère le calendrier de contributions public, sans token.

GitHub sert le calendrier en HTML sur `/users/<login>/contributions` — le même
fragment que la page de profil consomme. Pas d'API GraphQL, pas de personal
access token, donc rien à stocker en secret de dépôt.

Structure réelle du fragment (vérifiée le 16/08/2026) :

    <td class="ContributionCalendar-day"
        data-date="2026-06-07" data-level="4"
        id="contribution-day-component-0-42">

Le **compteur n'est pas dans la cellule**. Il vit dans un élément séparé :

    <tool-tip for="contribution-day-component-0-42">1 contribution on June 7th.</tool-tip>

Il faut donc joindre les deux par `id`, sinon on ne récupère que des niveaux
(0-4) sans jamais le nombre réel de contributions.

Sortie : data/contributions.json

Usage : python scripts/fetch_contributions.py [login]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"

DEFAULT_USER = "quentin-moraine"
URL = "https://github.com/users/{user}/contributions"
TIMEOUT = 20

COUNT_RE = re.compile(r"^([\d,]+)\s+contribution")
TOTAL_RE = re.compile(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", re.S)


def fetch_html(user: str) -> str:
    response = requests.get(
        URL.format(user=user),
        timeout=TIMEOUT,
        headers={
            "User-Agent": "github-profile-art/1.0 (+https://github.com/%s)" % user,
            "Accept": "text/html",
        },
    )
    response.raise_for_status()
    if "ContributionCalendar-day" not in response.text:
        raise SystemExit(
            "Réponse reçue mais sans grille de contributions. "
            "Le login est-il correct, et le profil public ?"
        )
    return response.text


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Compteurs, indexés par l'id de la cellule qu'ils décrivent.
    counts: dict[str, int] = {}
    for tip in soup.find_all("tool-tip"):
        target = tip.get("for")
        if not target:
            continue
        match = COUNT_RE.match(tip.get_text(strip=True))
        counts[target] = int(match.group(1).replace(",", "")) if match else 0

    days = []
    for cell in soup.select("td.ContributionCalendar-day"):
        date = cell.get("data-date")
        if not date:
            continue  # cellules de remplissage en début et fin de grille
        days.append(
            {
                "date": date,
                "level": int(cell.get("data-level", 0)),
                "count": counts.get(cell.get("id", ""), 0),
            }
        )

    if not days:
        raise SystemExit("Grille trouvée mais aucune cellule datée — le format a changé.")

    days.sort(key=lambda d: d["date"])

    # Le total affiché par GitHub fait autorité : il compte aussi les
    # contributions qui ne sont pas des commits (issues, PR, revues).
    heading = soup.find(id="js-contribution-activity-description")
    match = TOTAL_RE.search(heading.get_text(" ", strip=True)) if heading else None
    total = int(match.group(1).replace(",", "")) if match else sum(d["count"] for d in days)

    return {
        "total": total,
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "days": days,
    }


def main() -> None:
    user = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USER
    data = parse(fetch_html(user))
    data["user"] = user
    data["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    active = [d for d in data["days"] if d["count"]]
    print(f"utilisateur   {user}")
    print(f"periode       {data['range']['start']} -> {data['range']['end']}"
          f"  ({len(data['days'])} jours)")
    print(f"total         {data['total']} contributions")
    print(f"jours actifs  {len(active)}")
    print(f"ecrit         {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
