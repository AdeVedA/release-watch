"""QLabel qui tronque son texte avec `...` au lieu de pousser le layout.

Sans ceci, un titre ou un tag long rejette les boutons d'action hors du bandeau
quand la fenêtre est étroite : le QLabel n'a aucune tolérance de réduction.

Deux pièges, mesurés sur ce projet :
- `sizeHint` doit rester la largeur du texte COMPLET, sinon l'élision réduit la
  largeur réclamée au layout, qui élide davantage, et la boucle ne converge plus
  (stack overflow dans le layout) ;
- `setText` dans `resizeEvent` relance le layout : le drapeau `_applying` coupe la
  réentrée, et le texte n'est écrit que s'il change vraiment.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self._auto_tip = False
        self._applying = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    # ------------------------------------------------------------------ tailles

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetrics(self.font())
        width = metrics.horizontalAdvance(self._full)
        if self.maximumWidth() < 16777215:
            width = min(width, self.maximumWidth())
        return QSize(width, super().minimumSizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Un QLabel non replié revendique la largeur de tout son texte : il rejetterait
        # les boutons hors du bandeau. L'élision rend cette largeur facultative.
        return QSize(0, super().minimumSizeHint().height())

    # ------------------------------------------------------------------ texte

    def setToolTip(self, text: str) -> None:  # noqa: N802
        super().setToolTip(text)
        self._auto_tip = False

    def set_full_text(self, text: str) -> None:
        if text == self._full:
            self._apply_elision()
            return
        self._full = text
        self.updateGeometry()
        self._apply_elision_guarded()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elision_guarded()

    def _apply_elision_guarded(self) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            self._apply_elision()
        finally:
            self._applying = False

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        room = self.width()
        elided = self._full
        if room > 0 and metrics.horizontalAdvance(self._full) > room:
            elided = metrics.elidedText(self._full, Qt.TextElideMode.ElideRight, max(1, room - 2))
        if elided != self.text():
            self.setText(elided)
        if elided == self._full:
            if self._auto_tip:
                super().setToolTip("")
                self._auto_tip = False
            return
        if not self.toolTip() or self._auto_tip:
            super().setToolTip(self._full)
            self._auto_tip = True
