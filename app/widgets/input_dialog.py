"""Petit dialogue de saisie texte dont les boutons suivent la langue de l'interface.

`QInputDialog` garde ses boutons `OK` / `Cancel` dans la langue de Qt, quelle que soit
la langue applicative : ce module reprend seulement le strict nécessaire pour garder
les libellés dans `app/translations/en.py`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import theme
from app.i18n import t
from app.widgets.ghost_field import GhostLineEdit


class TextInputDialog(QDialog):
    def __init__(self, title: str, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.caption = QLabel()
        self.caption.setObjectName("dlgFieldLabel")
        self.caption.setText(label)
        root.addWidget(self.caption)

        self.edit = GhostLineEdit(value)
        self.edit.setObjectName("editInputValue")
        self.caption.setBuddy(self.edit)
        self.edit.selectAll()
        root.addWidget(self.edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel = QPushButton()
        self.cancel.setObjectName("btnCancel")
        theme.set_role(self.cancel, "ghost")
        self.cancel.setText(t("Annuler"))
        self.cancel.setToolTip(t("Ferme sans modifier."))
        self.cancel.clicked.connect(self.reject)

        self.ok = QPushButton()
        self.ok.setObjectName("btnOk")
        self.ok.setText(t("Valider"))
        self.ok.setToolTip(t("Valide la saisie."))
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)

        buttons.addWidget(self.cancel)
        buttons.addWidget(self.ok)
        root.addLayout(buttons)

        self.edit.returnPressed.connect(self.accept)

    def value_text(self) -> str:
        return self.edit.text().strip()


def text_input(
    parent: QWidget,
    title: str,
    label: str,
    value: str = "",
) -> tuple[str, bool]:
    """Ouvre le dialogue et renvoie `(valeur, accepté)` comme le faisait `QInputDialog`."""
    dialog = TextInputDialog(title, label, value, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.value_text(), accepted
