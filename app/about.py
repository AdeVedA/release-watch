"""Identité de l'application : nom, titre de fenêtre, icône. Un seul endroit à changer.

Module feuille : stdlib + PySide6 + `app/i18n.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

from app.i18n import Language, t
from app.paths import assets_dir

APP_NAME = "ReleaseWatch"
# Identifiant Windows : sans lui, la barre des tâches groupe la fenêtre sous
# python.exe et affiche l'icône de Python à la place de la nôtre.
APP_ID_WINDOWS = "adeveda.releasewatch"
# Version affichée à l'écran : sans elle, un rapport de bug ne dit pas quel code a été exécuté.
# La suite de tests la compare à la version de `pyproject.toml` : plus de divergence silencieuse.
APP_VERSION: str = "0.1.0"

ASSETS: Path = assets_dir()
ICON_PATH = ASSETS / "release_watch.png"
LANGUAGE_ICONS: dict[Language, Path] = {"fr": ASSETS / "fr.svg", "en": ASSETS / "en.svg"}


def window_title() -> str:
    """Titre de la fenêtre. `APP_NAME` et le numéro de version ne sont jamais traduits."""
    return f"{APP_NAME} {APP_VERSION} — {t('moniteur de releases GitHub')}"


def window_icon() -> QIcon:
    """Icône de la fenêtre et de la barre des tâches. Nulle si le fichier manque."""
    return QIcon(str(ICON_PATH)) if ICON_PATH.is_file() else QIcon()


def language_icon(language: Language) -> QIcon:
    """Drapeau affiché par le sélecteur de langue. Nulle si le fichier manque."""
    path = LANGUAGE_ICONS[language]
    return QIcon(str(path)) if path.is_file() else QIcon()


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID_WINDOWS)


def set_console_title() -> None:
    """Nomme l'onglet de Windows Terminal : il reprend le titre de la console.

    Aucun texte n'est écrit sur stdout (rien ne pollue la sortie, et le lancement
    sans console reste sans effet). Sans console attachée, `SetConsoleTitleW` échoue
    silencieusement : c'est le comportement attendu, pas une erreur.
    """
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.SetConsoleTitleW(APP_NAME)
