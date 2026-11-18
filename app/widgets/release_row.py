"""Une ligne du panneau de versions d'un bandeau.

La ligne entière est interactive : clic = description dans le panneau latéral,
flèches haut/bas = navigation entre les versions. Le rôle de la ligne (nouvelle,
locale, obsolète, hors motif) est porté par la propriété QSS `kind`, plus par un
badge texte.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QFrame, QMenu, QPushButton, QSizePolicy, QToolButton, QWidget

from app.i18n import format_date, t
from app.models import (
    KIND_LATEST,
    KIND_LATEST_LOCAL,
    KIND_LOCAL,
    KIND_OTHER,
    KIND_PLAIN,
    KIND_STALE,
    Asset,
    ReleaseInfo,
)
from app.theme import set_kind, set_property, set_role, token_px
from app.widgets.elided_label import ElidedLabel
from app.widgets.flow_layout import FlowLayout

ROW_SPACING = 4


def kind_tips() -> dict[str, str]:
    """Infobulles du rôle de la ligne.

    Fonction et non dictionnaire de module : évalué à l'import, il resterait figé
    dans la langue du démarrage après un changement de langue.
    """
    return {
        KIND_LATEST: t("Dernière version autorisée par le filtre du bandeau"),
        KIND_LATEST_LOCAL: t("Dernière version autorisée, et version désignée comme installée"),
        KIND_LOCAL: t("Version désignée comme installée, pas la dernière autorisée"),
        KIND_STALE: t("Autorisée par le filtre mais au-delà du cap de versions affichées"),
        KIND_OTHER: t("Refusée par le motif ou l'exclusion : jamais comparée à ta version locale"),
        KIND_PLAIN: t("Version autorisée par le filtre, intermédiaire"),
    }


class ReleaseRow(QFrame):
    validate_requested = Signal(str)
    download_requested = Signal(object, object)
    folder_requested = Signal(str)
    selected = Signal(object)
    nav_requested = Signal(int)

    def __init__(
        self,
        release: ReleaseInfo,
        kind: str,
        default_asset_name: str,
        matches_pattern: bool = True,
        show_asset_button: bool = True,
        downloads: Mapping[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("releaseRow")
        self._release = release
        self._kind = kind
        self._default_asset_name = default_asset_name
        self._matches_pattern = matches_pattern
        self._show_asset_button = show_asset_button
        # Nom d'asset -> chemin écrit, dans l'ordre d'écriture : le 📂 n'apparait que si cette
        # version a déjà laissé un fichier sur le disque.
        self._downloads: dict[str, str] = dict(downloads or {})
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if not matches_pattern:
            # Propriete lue par le QSS (#releaseRow[matches="0"]) : bouton télécharger en pointilles.
            set_property(self, "matches", "0")
        if release.prerelease:
            # Pre-release : l'italique remplace le mention texte 'pre-rel.'.
            set_property(self, "pre", "1")
        set_kind(self, kind)

        layout = FlowLayout(self, ROW_SPACING)
        layout.setContentsMargins(0, 0, 0, 0)
        self._min_row_height = token_px("row_h_release")
        self.setMinimumHeight(self._min_row_height)

        self.version = ElidedLabel(release.label)
        self.version.setObjectName("rowVersion")
        self.version.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        self.meta = ElidedLabel(self._meta_text())
        self.meta.setObjectName("rowMeta")
        self.meta.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        self.btn_asset = QPushButton("⤓")
        self.btn_asset.setObjectName("btnAsset")

        self.btn_folder = QPushButton("📂")
        self.btn_folder.setObjectName("btnOpenFolder")

        self.btn_validate = QToolButton()
        self.btn_validate.setObjectName("btnValidate")
        self.btn_validate.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        layout.addWidget(self.version)
        layout.addWidget(self.meta)
        layout.addWidget(self.btn_asset)
        layout.addWidget(self.btn_folder)
        layout.addWidget(self.btn_validate)

        self.retranslate()

        self.btn_validate.clicked.connect(lambda: self.validate_requested.emit(release.tag))
        self.btn_asset.clicked.connect(self._on_asset_clicked)
        self.btn_folder.clicked.connect(self._on_folder_clicked)

    # ------------------------------------------------------------------ textes

    def retranslate(self) -> None:
        """Re-écrit tous les textes de la ligne dans la langue active."""
        self.meta.set_full_text(self._meta_text())
        self.setToolTip(self._row_tip(self._kind))
        self._apply_validate_button(self._kind)
        self._apply_asset_button()
        self._apply_folder_button()

    def natural_widths(self) -> tuple[int, int]:
        return (
            self.version.fontMetrics().horizontalAdvance(self.version.full_text()),
            self.meta.fontMetrics().horizontalAdvance(self.meta.full_text()),
        )

    def set_text_widths(self, version_width: int, meta_width: int) -> None:
        self.version.setFixedWidth(version_width)
        self.meta.setFixedWidth(meta_width)
        self.version.updateGeometry()
        self.meta.updateGeometry()
        self._apply_release_height()
        self.updateGeometry()

    def _meta_text(self) -> str:
        return format_date(self._release.published_at)

    def _row_tip(self, kind: str) -> str:
        lines: list[str] = [
            kind_tips().get(kind, ""),
            t("Clic : description dans le panneau latéral."),
            t("Flèches haut/bas : naviguer entre les versions."),
        ]
        if self._release.prerelease:
            lines.append(t("pre-release (nom en italique)"))
        if self._release.source == "tags":
            lines.append(t("Source : tag GitHub, pas une release avec notes."))
        if not self._matches_pattern:
            notes_part = t("ses notes et ses assets") if self._show_asset_button else t("ses notes")
            lines.append(
                t(
                    "Ce tag ne suit pas le filtre de tag du bandeau : il reste affiché,\n"
                    "{notes} restent accessibles, mais il n'est jamais\n"
                    "comparé à ta version locale (sauf si tu le désignes comme version locale)."
                ).format(notes=notes_part)
            )
        return "\n".join(line for line in lines if line)

    # ------------------------------------------------------------------ boutons

    def _apply_validate_button(self, kind: str) -> None:
        """Le bouton « locale » est visible partout : la version locale peut être désignée sur n'importe quelle ligne."""
        is_local = kind in {KIND_LOCAL, KIND_LATEST_LOCAL}
        self.btn_validate.setText(t("✓ locale") if is_local else t("locale"))
        set_role(self.btn_validate, "accent" if is_local else "ghost")
        if is_local:
            self.btn_validate.setToolTip(t("Cette version est déjà désignée comme installée localement"))
            return
        self.btn_validate.setToolTip(t("Désigner cette version comme installée localement"))

    def _apply_asset_button(self) -> None:
        self.btn_asset.setVisible(self._show_asset_button)
        if not self._show_asset_button:
            self.btn_asset.setEnabled(False)
            self.btn_asset.setToolTip(t("Recueil des assets désactivé"))
            return
        assets = self._release.assets
        if not assets:
            self.btn_asset.setEnabled(False)
            self.btn_asset.setToolTip(t("Aucun asset pour cette version"))
            return
        self.btn_asset.setEnabled(True)
        if self._default_asset_name and self._default_asset_name in [a.name for a in assets]:
            self.btn_asset.setToolTip(t("Télécharger {name}").format(name=self._default_asset_name))
        elif len(assets) == 1:
            self.btn_asset.setToolTip(t("Télécharger {name}").format(name=assets[0].name))
        else:
            names = ", ".join(asset.name for asset in assets)
            self.btn_asset.setToolTip(t("Choisir un asset : {names}").format(names=names))

    def _apply_folder_button(self) -> None:
        """Le 📂 n'existe que si cette version a déjà écrit un fichier : sinon rien à ouvrir."""
        self.btn_folder.setVisible(bool(self._downloads))
        if not self._downloads:
            self.btn_folder.setToolTip(t("Aucun fichier encore écrit pour cette version"))
            return
        last_name, last_path = next(reversed(self._downloads.items()))
        lines = [t("Fichiers déjà écrits pour cette version :")]
        lines += [f"{name}\n    {path}" for name, path in self._downloads.items()]
        lines.append(t("Clique : ouvre le dossier de « {name} ».").format(name=last_name))
        self.btn_folder.setToolTip("\n".join(lines))

    def _on_folder_clicked(self) -> None:
        if not self._downloads:
            return
        self.folder_requested.emit(str(Path(next(reversed(self._downloads.values()))).parent))

    def _on_asset_clicked(self) -> None:
        chosen = self.pick_asset()
        if chosen is not None:
            self.download_requested.emit(self._release, chosen)

    def pick_asset(self) -> Asset | None:
        assets = self._release.assets
        if not assets:
            return None
        if len(assets) == 1:
            return assets[0]
        default = next(
            (asset for asset in assets if asset.name == self._default_asset_name),
            None,
        )
        if default is not None:
            return default
        menu = QMenu(self)
        for asset in assets:
            action = menu.addAction(asset.name)
            action.setData(asset.name)
        picked = menu.exec(self.btn_asset.mapToGlobal(self.btn_asset.rect().bottomLeft()))
        if picked is None:
            return None
        name = str(picked.data())
        return next((asset for asset in assets if asset.name == name), None)

    # ------------------------------------------------------------------ interactions

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_release_height()

    def _apply_release_height(self) -> None:
        """Hauteur minimale de la ligne entière, sans jamais rogner une ligne repliée."""
        if self.width() <= 0:
            return
        layout = self.layout()
        wanted = self._min_row_height
        if isinstance(layout, FlowLayout):
            wanted = max(wanted, layout.heightForWidth(self.width()))
        if self.minimumHeight() != wanted:
            self.setMinimumHeight(wanted)

    def describe(self) -> None:
        """Demande la description de cette version dans le panneau lateral."""
        self.selected.emit(self._release)

    def take_focus(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.take_focus()
            self.describe()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Up:
            self.nav_requested.emit(-1)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            self.nav_requested.emit(1)
            event.accept()
            return
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.describe()
            event.accept()
            return
        super().keyPressEvent(event)
