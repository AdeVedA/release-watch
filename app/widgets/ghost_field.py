"""QLineEdit dont le texte indicatif (placeholder) s'affiché en italique.

Un placeholder doit se distinguer d'une valeur saisie. Le QSS ne sait pas styler le
placeholder seul : la seule autre solution (règle font-style sur le QLineEdit)
italiserait aussi la saisie, et le QSS gagne sur setFont().

Le placeholder n'existe que champ vide : rendre la police italique quand le texte est
vide donne l'italique du placeholder et jamais celui d'une valeur.

Piege : tout re-polish de la feuille (apply_theme, reload_theme, repolish_tree,
set_property) reecrit la police du widget depuis la règle globale QWidget. L'italique
est donc repose a chaque FontChange, sinon elle disparait en silence au deuxieme
chargement du theme.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QLineEdit, QWidget


class GhostLineEdit(QLineEdit):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._syncing_font = False
        self.textChanged.connect(self._apply_ghost_font)
        self._apply_ghost_font()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() is QEvent.Type.FontChange:
            self._apply_ghost_font()

    def _apply_ghost_font(self) -> None:
        """Italique si le champ est vide : c'est exactement le regime du placeholder."""
        if self._syncing_font:
            return
        self._syncing_font = True
        try:
            font = self.font()
            font.setItalic(not self.text())
            self.setFont(font)
        finally:
            self._syncing_font = False
