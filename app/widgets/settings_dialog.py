"""Réglages globaux : nombre de versions par défaut et dossier de téléchargement."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.i18n import t
from app.models import MAX_VERSIONS_CHOICES, MAX_VISIBLE_VERSIONS, Settings, snap_versions_choice
from app.widgets.ghost_field import GhostLineEdit


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsDialog")

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("dlgTitle")
        root.addWidget(self.title_label)

        form = QFormLayout()
        form.setSpacing(8)

        self.cmb_versions = QComboBox()
        self.cmb_versions.setObjectName("cmbDefaultMaxVersions")
        for choice in MAX_VERSIONS_CHOICES:
            self.cmb_versions.addItem(str(choice), choice)
        self.cmb_versions.setCurrentIndex(self.cmb_versions.findData(snap_versions_choice(settings.max_versions)))
        self.versions_caption = QLabel()
        form.addRow(self.versions_caption, self.cmb_versions)

        self.edit_download = GhostLineEdit(settings.download_dir)
        self.edit_download.setObjectName("editDownloadDir")
        self.browse = QPushButton()
        self.browse.setObjectName("btnBrowseDownloadDir")
        theme.set_role(self.browse, "ghost")
        self.browse.clicked.connect(self._browse)
        folder_holder = QHBoxLayout()
        folder_holder.setContentsMargins(0, 0, 0, 0)
        folder_holder.addWidget(self.edit_download)
        folder_holder.addWidget(self.browse)
        folder_widget = QWidget(self)
        folder_widget.setLayout(folder_holder)
        self.folder_caption = QLabel()
        form.addRow(self.folder_caption, folder_widget)
        root.addLayout(form)

        self.hint = QLabel()
        self.hint.setObjectName("dlgHint")
        root.addWidget(self.hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel = QPushButton()
        self.cancel.setObjectName("btnCancel")
        theme.set_role(self.cancel, "ghost")
        self.cancel.clicked.connect(self.reject)
        self.ok = QPushButton()
        self.ok.setObjectName("btnOk")
        self.ok.clicked.connect(self._accept)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.ok)
        root.addLayout(buttons)

        self.retranslate()

        self.settings_result: Settings = settings

    # ------------------------------------------------------------------ textes

    def retranslate(self) -> None:
        """Réécrit tous les textes du dialogue dans la langue active."""
        self.setWindowTitle(t("Réglages"))
        self.title_label.setText(t("Réglages globaux"))
        self.cmb_versions.setToolTip(
            t(
                "Nombre de versions conservées par défaut pour un nouveau bandeau, "
                "dans la colonne retenue comme dans la colonne rejetée (crans {steps}).\n"
                "Un bandeau déjà présent garde son propre réglage.\n"
                "Stockage : les deux colonnes ensemble, plafonné à {cap} lignes."
            ).format(
                steps=", ".join(str(choice) for choice in MAX_VERSIONS_CHOICES),
                cap=MAX_VISIBLE_VERSIONS,
            )
        )
        self.versions_caption.setText(t("Versions récupérées par défaut"))
        self.edit_download.setPlaceholderText(t("Dossier proposé à chaque téléchargement"))
        self.edit_download.setToolTip(
            t(
                "Dossier proposé par le dialogue de téléchargement.\n"
                "Le dialogue s'affiche à chaque fois : rien n'est écrit sans validation.\n"
                "Vide : l'explorateur s'ouvre sur son dossier habituel."
            )
        )
        self.browse.setText(t("Parcourir"))
        self.browse.setToolTip(
            t("Sélecteur de dossier local. Aucune connexion, aucune écriture :\nmodifie seulement le champ à côté.")
        )
        self.folder_caption.setText(t("Dossier de téléchargement par défaut"))
        self.hint.setText(t("Chaque bandeau peut écraser ces deux valeurs."))
        self.cancel.setText(t("Annuler"))
        self.cancel.setToolTip(t("Ferme sans enregistrer."))
        self.ok.setText(t("Enregistrer"))
        self.ok.setToolTip(
            t(
                "Enregistre les réglages globaux dans data/state.json.\n"
                "Ne relance aucun fetch : les bandeaux gardent ce qu'ils ont déjà."
            )
        )

    # ------------------------------------------------------------------ actions

    def _browse(self) -> None:
        start = self.edit_download.text().strip()
        folder = QFileDialog.getExistingDirectory(self, t("Dossier de téléchargement"), start)
        if folder:
            self.edit_download.setText(folder)

    def _accept(self) -> None:
        self.settings_result = replace(
            self.settings_result,
            max_versions=int(self.cmb_versions.currentData()),
            download_dir=self.edit_download.text().strip(),
        )
        self.accept()

    @property
    def result_settings(self) -> Settings:
        return self.settings_result
