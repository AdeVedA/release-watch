"""Pieces partagees par les tests : attente de l'event loop, scenarios d'etat, recherche par role.

Aucun test ne touche un attribut d'un widget de l'application : on passe par les roles
de tests/contract.py et par les scenarios de ui_state(). Un renommage de widget ne se
corrige donc qu'a un seul endroit.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from app.i18n import Language, set_language
from app.i18n import language as active_language
from app.models import Repo
from app.widgets.main_window import MainWindow
from app.widgets.repo_banner import RepoBanner
from tests.contract import BANNER_ROLES

# Largeur de travail commune : assez large pour poser les deux lignes de reglages sur une rangee.
WINDOW_SIZE: tuple[int, int] = (1180, 900)


def app_of(widget: QWidget) -> QApplication:
    """Le QApplication de la session, a partir de n'importe quel widget."""
    app = QApplication.instance()
    assert isinstance(app, QApplication), "aucun QApplication : la fixture qapp manque"
    return app


def settle(widget: QWidget, rounds: int = 3) -> None:
    """Donne a Qt le temps de poser la geometrie.

    processEvents() seul ne traite pas DeferredDelete : sans ce vidage, les lignes de
    version remplacees comptent encore dans les controles.
    """
    app = app_of(widget)
    for _ in range(rounds):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def banner_of(window: MainWindow, repo: Repo) -> RepoBanner:
    """Un seul endroit atteint le conteneur prive des bandeaux."""
    banner = window._banners.get(repo.id)
    assert isinstance(banner, RepoBanner), f"aucun bandeau pour le repo {repo.id}"
    return banner


def banners_of(window: MainWindow) -> list[RepoBanner]:
    return [banner_of(window, repo) for repo in window.state.repos]


def find_role(root: QWidget, roles: Mapping[str, str], role: str) -> QWidget | None:
    """Retrouve un widget par son role (objectName du contrat), jamais par un attribut Python."""
    wanted = roles[role]
    for widget in (root, *root.findChildren(QWidget)):
        if widget.objectName() == wanted:
            return widget
    return None


def must_find(root: QWidget, roles: Mapping[str, str], role: str) -> QWidget:
    widget = find_role(root, roles, role)
    assert widget is not None, f"role {role!r} (objectName {roles[role]!r}) absent de {type(root).__name__}"
    return widget


def role_of[V: QWidget](root: QWidget, roles: Mapping[str, str], role: str, kind: type[V]) -> V:
    """Le role du contrat, dans le type attendu : le test n'a plus a trier les QWidget a la main."""
    widget = must_find(root, roles, role)
    assert isinstance(widget, kind), f"le role {role!r} est un {type(widget).__name__}, attendu {kind.__name__}"
    return widget


def click_role(root: QWidget, roles: Mapping[str, str], role: str) -> None:
    """Clique le widget du contrat : le scenario passe donc par le vrai chemin de l'application."""
    role_of(root, roles, role, QAbstractButton).click()


def _apply_flags(
    window: MainWindow,
    *,
    collapsed: bool | None,
    assets: bool | None,
    hidden_column: str | None,
) -> list[tuple[Repo, str]]:
    """Pose les drapeaux en cliquant les vrais boutons. Retourne ce qui a ete clique, pour deleguer."""
    clicked: list[tuple[Repo, str]] = []
    for repo in window.state.repos:
        banner = banner_of(window, repo)
        if collapsed is not None and repo.collapsed is not collapsed:
            click_role(banner, BANNER_ROLES, "chevron")
            clicked.append((repo, "chevron"))
        if assets is not None and repo.assets_enabled is not assets:
            click_role(banner, BANNER_ROLES, "case_assets")
            clicked.append((repo, "case_assets"))
        if hidden_column in ("left", "right"):
            role = "colonne_retenues" if hidden_column == "left" else "colonne_rejetees"
            flag = repo.column_left_collapsed if hidden_column == "left" else repo.column_right_collapsed
            if not flag:
                click_role(banner, BANNER_ROLES, role)
                clicked.append((repo, role))
    return clicked


@contextmanager
def ui_state(
    window: MainWindow,
    *,
    width: int | None = None,
    dock: bool | None = None,
    collapsed: bool | None = None,
    assets: bool | None = None,
    hidden_column: str | None = None,
    language: Language | None = None,
) -> Generator[MainWindow]:
    """Scenario reutilisable : largeur, dock, repli, recueil des assets, colonne masquee, langue.

    L'etat d'origine est retabli a la sortie, y compris quand le test leve au milieu.
    C'est lui qui remplace les window.resize() / setVisible() / processEvents() qui
    etaient recables a la main dans chaque controle.
    """
    start_size = window.size()
    start_dock = window.notes.isVisible()
    start_language = active_language()
    if width is not None:
        window.resize(width, WINDOW_SIZE[1])
    if dock is not None:
        window.notes.setVisible(dock)
    clicked = _apply_flags(window, collapsed=collapsed, assets=assets, hidden_column=hidden_column)
    if language is not None and active_language() != language:
        set_language(language)
        window.retranslate()
    settle(window)
    try:
        yield window
    finally:
        for repo, role in reversed(clicked):
            banner = banner_of(window, repo)
            widget = must_find(banner, BANNER_ROLES, role)
            if not widget.isEnabled():
                continue
            click_role(banner, BANNER_ROLES, role)
        if active_language() != start_language:
            set_language(start_language)
            window.retranslate()
        window.resize(start_size)
        window.notes.setVisible(start_dock)
        settle(window)
