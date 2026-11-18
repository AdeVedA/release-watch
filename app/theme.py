"""Chargement, rendu et rechargement à chaud du thème QSS.

La feuille sur disque (`resources/<theme>.qss`) est un TEMPLATE : chaque valeur de
couleur ou de dimension y est un token `$nom` résolu depuis `app/palette.py`.
Aucune couleur brute n'est autorisée dans le `.qss`.

La substitution est vérifiée AVANT d'être appliquée : un token inconnu lève
`ThemeTokenError` au lieu de rendre silencieusement une couleur par défaut.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from string import Template

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QStyle, QWidget

from app import palette
from app.i18n import t
from app.models import STATUS_TOKEN, Status
from app.paths import resources_dir

RESOURCES_DIR: Path = resources_dir()
ACTIVE_THEME: str = "dark"
DUMP_NAME: str = "theme_dump.qss"


class ThemeTokenError(RuntimeError):
    """Token référencé dans un `.qss` mais absent de la palette."""


def qss_path(theme_name: str = ACTIVE_THEME) -> Path:
    return RESOURCES_DIR / f"{theme_name}.qss"


def token_table() -> dict[str, str]:
    return dict(palette.TOKENS)


def unused_tokens(rendered_source: str) -> list[str]:
    used = set(Template(rendered_source).get_identifiers())
    return sorted(name for name in token_table() if name not in used)


def render(theme_name: str = ACTIVE_THEME) -> str:
    path = qss_path(theme_name)
    if not path.is_file():
        raise ThemeTokenError(t("Feuille de style introuvable : {path}").format(path=path))
    source = path.read_text(encoding="utf-8")
    table = token_table()
    used = set(Template(source).get_identifiers())
    missing = sorted(token for token in used if token not in table)
    if missing:
        raise ThemeTokenError(
            t("Tokens de palette absents pour {file} : {missing} (éditer {module}.py)").format(
                file=path.name, missing=", ".join(missing), module=palette.__name__
            )
        )
    return Template(source).substitute(table)


def dump(text: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / DUMP_NAME
    target.write_text(text, encoding="utf-8")
    return target


def apply_theme(app: QApplication, dump_folder: Path | None = None) -> str:
    text = render()
    app.setStyleSheet(text)
    if dump_folder is not None:
        dump(text, dump_folder)
    return text


def reload_theme(app: QApplication, dump_folder: Path | None = None) -> str:
    """Recharge `app/palette.py` ET le `.qss` depuis le disque, puis les réapplique."""
    importlib.reload(palette)
    return apply_theme(app, dump_folder)


def repolish(widget: QWidget) -> None:
    """Force Qt à relire les sélecteurs de propriété QSS de ce widget."""
    style: QStyle = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def repolish_tree(widget: QWidget) -> None:
    """Re-polit le widget puis ses enfants : nécessaire pour les sélecteurs enfants."""
    repolish(widget)
    for child in widget.findChildren(QWidget):
        repolish(child)


def notify_style_change(widget: QWidget) -> None:
    """Signale à ce widget que sa feuille vient d'être posée, pour qu'il se remesure.

    Un widget construit APRES la pose de la feuille globale ne reçoit jamais l'événement
    `StyleChange` que `setStyleSheet` envoie aux widgets déjà vivants. Son layout interne
    ignore alors une partie du modèle de boîte QSS : la barre d'actions restait à 43 px
    au lieu de 53 px (son `padding: $pad_sm $pad_md` n'était honoré qu'au premier
    rechargement du thème). `repolish()` et `layout().invalidate() + activate()` ne
    déclenchent pas ce recalcul : seul l'événement le déclenche (vérifié par sonde).
    """
    QCoreApplication.sendEvent(widget, QEvent(QEvent.Type.StyleChange))


def set_property(widget: QWidget, name: str, value: str) -> None:
    """Pose une propriété dynamique puis re-polit, uniquement si la valeur change.

    Les sélecteurs de propriété QSS ne suivent pas les changements : sans
    unpolish/polish, la couleur resterait figée à la valeur de pose de la feuille.
    """
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    repolish(widget)


def set_role(widget: QWidget, role: str) -> None:
    set_property(widget, "role", role)


def set_kind(widget: QWidget, kind: str) -> None:
    """Catégorie d'une ligne de version : la couleur vient du QSS `[kind=...]`."""
    set_property(widget, "kind", kind)


def set_status(widget: QWidget, status: Status) -> None:
    set_property(widget, "status", STATUS_TOKEN[status])


def font_size_steps(prefix: str = "fs_notes_") -> tuple[int, ...]:
    """Crans de taille demandés par le `.qss`, du plus petit au plus grand.

    Les bornes du clampage ne sont pas écrites en Python : elles sont dans la palette.
    """
    steps: list[int] = []
    for name, value in token_table().items():
        if not name.startswith(prefix):
            continue
        digits = "".join(char for char in name[len(prefix) :] if char.isdigit())
        if digits and value.rstrip("px").strip().isdigit():
            steps.append(int(digits))
    if not steps:
        raise ThemeTokenError(t("Aucun token de taille {prefix}N dans la palette").format(prefix=prefix))
    return tuple(sorted(steps))


def token_px(name: str) -> int:
    """Lit un token de dimension de la palette comme une valeur en pixels."""
    table = token_table()
    if name not in table:
        raise ThemeTokenError(t("Token de dimension absent de la palette : {name}").format(name=name))
    raw = table[name]
    if not raw.rstrip().endswith("px"):
        raise ThemeTokenError(t("Token non exprimé en pixels : {name}={value}").format(name=name, value=repr(raw)))
    try:
        return int(raw.rstrip().removesuffix("px").strip())
    except ValueError as exc:
        raise ThemeTokenError(
            t("Token de dimension invalide : {name}={value}").format(name=name, value=repr(raw))
        ) from exc


def snap_font_size(value: int, prefix: str = "fs_notes_") -> int:
    """Ramène la taille demandée sur le cran le plus proche de l'échelle."""
    steps = font_size_steps(prefix)
    return min(steps, key=lambda step: (abs(step - value), step))
