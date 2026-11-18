"""Langue de l'interface : français et anglais, la clé est le texte français affiché.

Choix assumés, à ne pas inverser :

- La clé de traduction **est** le texte visible. `rg "à garder"` doit continuer
  à retrouver la ligne du widget. Une clé opaque du type `banner.tip.tag_keep`
  détruirait le seul outil de recherche utile sur l'interface.
- Pas de table `fr` : le français sert d'identité, seule la table `en` est écrite.
- Une clé absente de la table `en` retombe sur le français sans lever. Un texte
  non traduit est un défaut visible, jamais un plantage ; c'est le test
  `tests/test_rules.py::test_table_anglaise_est_complete` qui rend
  l'incomplétude impossible, pas une exception au lancement.
- Interdit, et vérifié par test : `t(f"...")`. La clé doit être un littéral,
  sinon elle change selon les valeurs et ne se retrouve plus dans la table.
- L'ordre des mots des dates et les unités de taille dépendent de la langue :
  ils vivent ici, pas dans les widgets.

Dépendances : stdlib seulement. `app/i18n.py` n'importe ni Qt ni un module du
projet, sinon tout le monde finirait par dépendre de tout le monde.
"""

from __future__ import annotations

from typing import Final, Literal

from app.translations.en import EN

Language = Literal["fr", "en"]

LANGUAGES: tuple[Language, ...] = ("fr", "en")
DEFAULT_LANGUAGE: Final[Language] = "fr"

# Libellés des langues, écrits dans leur propre langue : un sélecteur de langue
# doit rester lisible même quand on ne parle pas encore la langue cible.
LANGUAGE_NAMES: dict[Language, str] = {"fr": "Français", "en": "English"}

# Unités de taille lues par `app/widgets/notes_dock.py::human_size` et par la
# barre de progression du téléchargement.
SIZE_UNITS: dict[Language, tuple[str, ...]] = {
    "fr": ("Ko", "Mo", "Go"),
    "en": ("kB", "MB", "GB"),
}

_ACTIVE: Language = DEFAULT_LANGUAGE


def normalize_language(raw: object) -> Language:
    """Force n'importe quelle valeur (souvent venue de `state.json`) vers « fr » ou « en ».

    Un `language` écrit à la main peut valoir `"FR"`, `"fr_FR"`, `"en-US"` ou
    n'importe quoi : on ne rejette rien, on rapproche au mieux, sinon
    l'application refuserait de démarrer sur un JSON édité à la main.
    """
    if not isinstance(raw, str):
        return DEFAULT_LANGUAGE
    code = raw.strip().lower().replace("_", "-")
    if code.startswith("en"):
        return "en"
    if code.startswith("fr"):
        return "fr"
    return DEFAULT_LANGUAGE


def language() -> Language:
    """Langue active de l'interface."""
    return _ACTIVE


def set_language(raw: object) -> Language:
    """Fixe la langue active et la renvoie normalisée.

    Ne re-textute rien : c'est `MainWindow.set_language()` qui parcourt les
    widgets. Appeler cette fonction sans re-textuter laisse l'écran dans
    l'ancienne langue, ce qui est le comportement attendu pour les fils en cours.
    """
    global _ACTIVE

    _ACTIVE = normalize_language(raw)
    return _ACTIVE


def t(key: str) -> str:
    """Texte dans la langue active, la clé étant le texte français affiché."""
    if _ACTIVE == "fr":
        return key
    return EN.get(key, key)


def size_units() -> tuple[str, ...]:
    """Unités de taille de la langue active (Ko/Mo/Go ou kB/MB/GB)."""
    return SIZE_UNITS[_ACTIVE]


def format_date(iso: str) -> str:
    """Date courte à 8 caractères, dans l'ordre que la langue active sait lire.

    `"2026-04-18T09:00:00Z"` devient `"18/04/26"` en français et `"26/04/18"` en
    anglais. L'anglais garde l'ordre chronologique inverse (année d'abord) parce
    que c'est l'ordre ISO, pas l'ordre jour/mois américain : `18/04` serait
    ambigu entre les deux lecteurs.

    La valeur vient du réseau : un format inattendu ne lève jamais, il rend une
    chaîne vide, ce qui masque la méta plutôt que d'afficher du bruit.
    """
    parts = iso[:10].split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return ""
    year, month, day = parts
    short_year = year[2:]
    if _ACTIVE == "fr":
        return f"{day}/{month}/{short_year}"
    return f"{short_year}/{month}/{day}"
