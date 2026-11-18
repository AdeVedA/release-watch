"""Chemins de l'application : le seul module qui sait si le programme est gelé.

Deux racines distinctes, et c'est tout le sujet du module :

- `app_root()` : le dossier ou l'on ECRIT (`data/state.json`, journaux de scripts).
  Gelé, ce dossier est celui de l'executable. Ne jamais utiliser `__file__` pour
  cela : dans un paquet PyInstaller, `__file__` designe l'interieur du paquet, et
  en one-file ce paquet est un dossier temporaire detruit a la fermeture.
- `bundle_root()` : la racine de LECTURE des ressources embarquees (`resources/`,
  `assets/`). Gelé, c'est le paquet lui-meme.

Module feuille : stdlib seule (aucune dependance a PySide6), importable partout.
"""

from __future__ import annotations

import sys
from pathlib import Path

DATA_DIRNAME: str = "data"
RESOURCES_DIRNAME: str = "resources"
ASSETS_DIRNAME: str = "assets"
INTERNAL_DIRNAME: str = "_internal"


def is_frozen() -> bool:
    """Vrai dans un executable PyInstaller (`--onefile` comme `--onedir`)."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Racine du projet source : le dossier qui contient `app/`, `resources/`, `assets/`."""
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    """Dossier ecrivable de l'application, a cote de l'executable quand il est gele."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def bundle_root() -> Path:
    """Racine des ressources en lecture seule embarquees dans le paquet gele."""
    if not is_frozen():
        return project_root()
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(str(meipass)).resolve()
    # one-dir : PyInstaller 6 pose les donnees dans `_internal`, a cote de l'executable.
    internal = app_root() / INTERNAL_DIRNAME
    return internal if internal.is_dir() else app_root()


def data_dir() -> Path:
    """`data/` : etat, sauvegarde, journaux de lancement. Ecrit par l'application."""
    return app_root() / DATA_DIRNAME


def resources_dir() -> Path:
    """`resources/` : les feuilles `.qss` (des templates, jamais des couleurs brutes)."""
    return bundle_root() / RESOURCES_DIRNAME


def assets_dir() -> Path:
    """`assets/` : icone de la fenetre et drapeaux de langue."""
    return bundle_root() / ASSETS_DIRNAME
