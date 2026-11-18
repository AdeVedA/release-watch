"""Panneau latéral affichant la description d'une release en Markdown.

Les notes de release sont du texte contrôlé par l'auteur du repo : les liens sont
filtrés (HTTPS uniquement) et n'ouvrent jamais un fichier local ni un lien en clair.

Les faits de tête (date, source, nombre d'assets, pre-release) sont des widgets
alignés sur la ligne du titre, pas des lignes de texte. Les listes d'assets et de
contributeurs sont des sections dépliables ; la taille de police se règle à la
molette avec Ctrl, par crans définis dans la palette.

Le contenu traduit est l'enveloppe du panneau (titre, chips, sections, infobulles).
Le corps des notes vient du réseau : il n'est jamais traduit.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QFont, QWheelEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import format_date, size_units, t
from app.models import ReleaseInfo
from app.notes_parse import NotesParts, split_notes
from app.theme import font_size_steps, set_property, snap_font_size, token_px
from app.widgets.elided_label import ElidedLabel

COLLAPSED_GLYPH = "▸"
EXPANDED_GLYPH = "▾"
SECTION_MAX_HEIGHT = 200
SIZE_STEPS: tuple[int, ...] = (1024, 1024 * 1024, 1024 * 1024 * 1024)

# Titres des sections : littéraux traduits, jamais des variables de module évaluées
# à l'import (elles ne suivraient pas un changement de langue à chaud).


def human_size(raw: int) -> str:
    if raw <= 0:
        return t("taille inconnue")
    if raw < SIZE_STEPS[0]:
        return t("{n} octet").format(n=raw) if raw == 1 else t("{n} octets").format(n=raw)
    value = float(raw)
    unit = t("octets")
    steps = size_units()
    # Comparaison sur la valeur brute : comparer la valeur déjà divisée faisait monter
    # l'unité d'un cran trop tôt (900 Ko affichés « 0.9 Mo ») et l'échelonne au-delà de 10 Go.
    for factor, name in zip(SIZE_STEPS, steps, strict=False):
        if raw < factor:
            break
        value = raw / factor
        unit = name
    return f"{value:.1f} {unit}"


def _section(object_name: str, title: str, tip: str) -> tuple[QPushButton, QTextBrowser]:
    """Une section dépliable : chevron + corps Markdown jamais interactif ailleurs."""
    # QPushButton et non QToolButton : le QToolButton centre son texte et ignore
    # text-align (vérifié : premier pixel de texte à x=401 sur une boîte de 580 px, aussi
    # bien avec text-align: left qu'avec text-align: right), et sa politique horizontale
    # Fixed ne prend pas toute la largeur (52 px). Le libellé est donc aligné à gauche par
    # le QSS, et la boîte fermée couvre toute la largeur du panneau.
    toggle = QPushButton()
    toggle.setObjectName(object_name)
    toggle.setText(f"{COLLAPSED_GLYPH} {title}")
    toggle.setCheckable(True)
    toggle.setToolTip(tip)
    toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    body = QTextBrowser()
    body.setObjectName("txtNotesSection")
    body.setOpenLinks(False)
    body.setOpenExternalLinks(False)
    body.setVisible(False)
    body.setMaximumHeight(SECTION_MAX_HEIGHT)
    return toggle, body


class NotesDock(QDockWidget):
    link_accepted = Signal(str)
    link_refused = Signal(str)
    font_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(t("Notes de release"), parent)
        self.setObjectName("dockNotes")
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setMinimumWidth(token_px("w_dock_notes_min"))
        self.setMaximumWidth(token_px("w_dock_notes_max"))
        self._release: ReleaseInfo | None = None
        self._repo_title: str = ""
        self._parts: NotesParts = NotesParts()
        self._font_size = 0

        host = QWidget(self)
        host.setObjectName("notesHost")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        self.browser = QTextBrowser(host)
        self.browser.setObjectName("txtNotes")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser, 1)

        self.sec_assets_toggle, self.sec_assets_body = _section(
            "secAssetsToggle",
            t("Assets"),
            t("Liste des assets conservés pour cette version (ceux passés par le filtre du bandeau)."),
        )
        self.sec_contrib_toggle, self.sec_contrib_body = _section(
            "secContribToggle",
            t("Contributeurs"),
            t("Sections de contribution récupérées dans les notes GitHub. Aucune requête supplémentaire."),
        )
        for toggle, body in (
            (self.sec_assets_toggle, self.sec_assets_body),
            (self.sec_contrib_toggle, self.sec_contrib_body),
        ):
            layout.addWidget(toggle)
            layout.addWidget(body)

        self.setWidget(host)
        self.setTitleBarWidget(self._build_title_bar())

        self.browser.anchorClicked.connect(self._on_anchor)
        self.sec_assets_body.anchorClicked.connect(self._on_anchor)
        self.sec_contrib_body.anchorClicked.connect(self._on_anchor)
        self.sec_assets_toggle.toggled.connect(self._on_assets_toggle)
        self.sec_contrib_toggle.toggled.connect(self._on_contrib_toggle)
        for body in (self.browser, self.sec_assets_body, self.sec_contrib_body):
            body.installEventFilter(self)
            body.viewport().installEventFilter(self)

    # ------------------------------------------------------------------ textes

    def retranslate(self) -> None:
        """Réécrit les libellés du panneau sans toucher au contenu des notes."""
        self.setWindowTitle(t("Notes de release"))
        self.title_label.setText(t("Notes de release"))
        self.title_label.setToolTip(t("Panneau de description de la release sélectionnée"))
        self.btn_float.setToolTip(t("Détacher ou rattacher le panneau"))
        self.btn_close.setToolTip(t("Fermer le panneau de description"))
        self.chip_date.setToolTip(t("Date de publication de la release"))
        self.chip_assets.setToolTip(t("Nombre d'assets conservés pour cette version"))
        self.chip_source.setToolTip(t("Provenance des données : release GitHub ou simple tag"))
        self.chip_pre.setToolTip(t("Cette version est signalée pre-release par GitHub"))
        self._sync_toggle_label(self.sec_assets_toggle, t("Assets"), self._assets_count())
        self._sync_toggle_label(self.sec_contrib_toggle, t("Contributeurs"), self._contrib_count())
        if self._release is None:
            self.title.set_full_text(t("Aucune version sélectionnée"))
            self.title.setToolTip(t("Description lue depuis la release GitHub, affichée ici en Markdown"))
            return
        self.show_release(self._repo_title, self._release)

    def _assets_count(self) -> int:
        return 0 if self._release is None else len(self._release.assets)

    def _contrib_count(self) -> int:
        return len(self._contrib_blocks())

    def _contrib_blocks(self) -> list[str]:
        return [text for _label, text in self._parts.contributors]

    # ------------------------------------------------------------------ tête

    def _build_header(self) -> QWidget:
        header = QWidget(self)
        header.setObjectName("notesHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title = ElidedLabel(t("Aucune version sélectionnée"))
        self.title.setObjectName("lblNotesTitle")
        self.title.setToolTip(t("Description lue depuis la release GitHub, affichée ici en Markdown"))

        self.chip_date = QLabel("")
        self.chip_date.setObjectName("chipNotes")
        self.chip_date.setToolTip(t("Date de publication de la release"))

        self.chip_assets = QLabel("")
        self.chip_assets.setObjectName("chipNotes")
        self.chip_assets.setToolTip(t("Nombre d'assets conservés pour cette version"))

        self.chip_source = QLabel("")
        self.chip_source.setObjectName("chipNotesSource")
        self.chip_source.setToolTip(t("Provenance des données : release GitHub ou simple tag"))

        self.chip_pre = QLabel("")
        self.chip_pre.setObjectName("chipNotesPre")
        self.chip_pre.setToolTip(t("Cette version est signalée pre-release par GitHub"))

        layout.addWidget(self.chip_date, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.chip_assets, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.title, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.chip_source, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.chip_pre, alignment=Qt.AlignmentFlag.AlignRight)
        # Aucune release affichée au démarrage : aucune chip. Sans ce repli, les chips
        # vides gardent leur espace et leur bordure, et le bandeau de tête semble bricolé.
        self._set_chips_visible(False)
        self.header = header
        return header

    def _chips(self) -> tuple[QLabel, ...]:
        return (self.chip_date, self.chip_assets, self.chip_source, self.chip_pre)

    def _set_chips_visible(self, visible: bool) -> None:
        for chip in self._chips():
            chip.setVisible(visible)
            chip.updateGeometry()

    def _build_title_bar(self) -> QWidget:
        title_bar = QWidget(self)
        title_bar.setObjectName("notesTitleBar")
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title_label = QLabel(t("Notes de release"))
        self.title_label.setObjectName("notesTitleLabel")
        self.title_label.setToolTip(t("Panneau de description de la release sélectionnée"))

        self.btn_float = QToolButton(title_bar)
        self.btn_float.setObjectName("btnDockNotesFloat")
        self.btn_float.setText("▢")
        self.btn_float.setToolTip(t("Détacher ou rattacher le panneau"))
        self.btn_float.clicked.connect(self._on_float_toggle)

        self.btn_close = QToolButton(title_bar)
        self.btn_close.setObjectName("btnDockNotesClose")
        self.btn_close.setText("×")
        self.btn_close.setToolTip(t("Fermer le panneau de description"))
        self.btn_close.clicked.connect(self._on_close)

        layout.addWidget(self.title_label, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.btn_float)
        layout.addWidget(self.btn_close)
        return title_bar

    def _on_float_toggle(self) -> None:
        self.setFloating(not self.isFloating())

    def _on_close(self) -> None:
        self.close()

    # ------------------------------------------------------------------ contenu

    def show_release(self, repo_title: str, release: ReleaseInfo) -> None:
        self._repo_title = repo_title
        self._release = release
        self._parts = split_notes(release.notes_md)
        self.title.set_full_text(f"{repo_title} · {release.label}")
        self.title.setToolTip(f"{repo_title} — {release.label}")
        self._sync_chips(release)
        self.browser.setMarkdown(self._markdown(release))
        self._sync_sections()

    def _sync_chips(self, release: ReleaseInfo) -> None:
        if release.published_at:
            self.chip_date.setText(format_date(release.published_at))
            self.chip_date.setToolTip(t("Publiée le {date}").format(date=release.published_at[:10]))
            self.chip_date.setVisible(True)
        else:
            self.chip_date.setText("")
            self.chip_date.setVisible(False)

        count = len(release.assets)
        self.chip_assets.setText(t("{n} asset").format(n=count) if count <= 1 else t("{n} assets").format(n=count))
        self.chip_assets.setVisible(True)

        self.chip_source.setText(t("tag sans release") if release.source == "tags" else t("release GitHub"))
        self.chip_source.setVisible(True)

        self.chip_pre.setText(t("pre-release") if release.prerelease else "")
        self.chip_pre.setVisible(release.prerelease)

    def _markdown(self, release: ReleaseInfo) -> str:
        notes = self._parts.body.strip()
        if notes:
            return notes
        return t("> Aucune description associée à ce tag.")

    def _sync_sections(self) -> None:
        release = self._release
        if release is None:
            return
        if release.assets:
            lines = [f"- `{asset.name}` · {human_size(asset.size)}" for asset in release.assets]
            self.sec_assets_body.setMarkdown("\n".join(lines))
        else:
            self.sec_assets_body.setMarkdown(t("Aucun asset conservé : recueil désactivé ou tout a été filtré."))
        self._sync_toggle_label(self.sec_assets_toggle, t("Assets"), len(release.assets))

        blocks = self._contrib_blocks()
        if blocks:
            self.sec_contrib_body.setMarkdown("\n\n".join(blocks))
        self.sec_contrib_toggle.setEnabled(bool(blocks))
        if not blocks and self.sec_contrib_toggle.isChecked():
            self.sec_contrib_toggle.setChecked(False)
        self._sync_toggle_label(self.sec_contrib_toggle, t("Contributeurs"), len(blocks))
        self.sec_contrib_body.setVisible(self.sec_contrib_toggle.isChecked() and bool(blocks))

    @staticmethod
    def _sync_toggle_label(toggle: QPushButton, title: str, count: int) -> None:
        glyph = EXPANDED_GLYPH if toggle.isChecked() else COLLAPSED_GLYPH
        toggle.setText(f"{glyph} {title} · {count}")

    def _on_assets_toggle(self, checked: bool) -> None:
        self.sec_assets_body.setVisible(checked)
        self._sync_toggle_label(self.sec_assets_toggle, t("Assets"), self._assets_count())

    def _on_contrib_toggle(self, checked: bool) -> None:
        blocks = self._contrib_blocks()
        self.sec_contrib_body.setVisible(checked and bool(blocks))
        self._sync_toggle_label(self.sec_contrib_toggle, t("Contributeurs"), len(blocks))

    # ------------------------------------------------------------------ liens

    def _on_anchor(self, url: QUrl) -> None:
        target = url.toString()
        if url.scheme().lower() == "https":
            self.link_accepted.emit(target)
            return
        self.link_refused.emit(target or t("(lien sans protocole)"))

    # ------------------------------------------------------------------ taille de police

    def apply_font_size(self, value: int) -> int:
        """Pose la taille de police sur les crans de la palette, puis re-polit le QSS."""
        size = snap_font_size(value)
        self._font_size = size
        for widget in (self.browser, self.sec_assets_body, self.sec_contrib_body):
            set_property(widget, "fsize", str(size))
            font = QFont(widget.font())
            font.setPixelSize(size)
            widget.setFont(font)
            widget.document().setDefaultFont(font)
        return size

    def font_size(self) -> int:
        return self._font_size

    def _bump_font_size(self, delta: int) -> None:
        steps = font_size_steps()
        current = self._font_size or steps[0]
        wanted = snap_font_size(current + delta)
        if wanted == current:
            return
        self.apply_font_size(wanted)
        self.font_size_changed.emit(wanted)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() is QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.angleDelta().y() != 0:
                self._bump_font_size(1 if event.angleDelta().y() > 0 else -1)
                event.accept()
                return True
        return super().eventFilter(watched, event)
