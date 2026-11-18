"""Bandeau d'un repo GitHub : titre, version locale, état, filtres, actions, versions.

Déplié, le bandeau prend trois lignes de réglages sous la ligne de tête :
les filtres de tag et le nombre de versions, les filtres d'assets, puis les
informations (dernier fetch, dossier de téléchargement). Replié, il ne garde que
la ligne de tête, avec tous ses boutons : le titre est élidé pour que les boutons
ne soient jamais chassés vers la droite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from PySide6.QtCore import QEvent, QMimeData, QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QFont, QFontMetrics, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import filters
from app.i18n import t
from app.models import (
    MAX_REJECTED_VERSIONS_CHOICES,
    MAX_VERSIONS_CHOICES,
    TAG_PATTERN_EXAMPLE,
    VERSIONS_SOURCE_RELEASES,
    VERSIONS_SOURCE_TAGS,
    ReleaseInfo,
    Repo,
    Status,
    status_label,
)
from app.scripts import IS_WINDOWS, ScriptError, plan_for
from app.theme import set_property, set_role, set_status, token_px
from app.widgets.elided_label import ElidedLabel
from app.widgets.flow_layout import FlowLayout, apply_flow_height
from app.widgets.ghost_field import GhostLineEdit
from app.widgets.input_dialog import text_input
from app.widgets.release_row import ReleaseRow
from app.widgets.segmented import SegmentedControl, segmented

SPACING = 8
# Poids des items élastiques qui encadrent le groupe central d'une ligne de réglages.
# Volontairement grand : les champs et combos Expanding de la même ligne ne doivent
# pas déplacer le centre en accaparant le surplus de largeur.
CENTER_STRETCH = 60
# Plancher du libellé « version locale -> dernière version » : en dessous, il ne
# reste que l'ellipse, ce qui ne sert plus à rien mais garde la place du titre.
LOCAL_LABEL_MIN = 40
STATUS_GLYPH = "●"
EXCLUDE_GLYPH = "⊘"
COLLAPSED_GLYPH = "▸"
EXPANDED_GLYPH = "▾"
# Cran de taille du titre, du plus grand au plus petit : avant de couper le nom du repo,
# on l'écrit plus petit. La règle QSS correspondante porte la propriété fsize ; les
# tailles viennent de la palette (token_px), jamais d'un chiffre ici.
TITLE_FIT_STEPS: tuple[tuple[str, str], ...] = (("", "fs_xl"), ("lg", "fs_title_lg"), ("md", "fs_title_md"))
# Au-dessous de cette largeur, les deux colonnes de versions s'empilent : deux
# colonnes côte à côte ne peuvent plus aligner les boutons de leurs lignes.
TWO_COLUMNS_MIN = 480

# Widgets dont le double-clic ne doit jamais plier le bandeau. `SegmentedControl` est là pour le
# joint entre deux boutons collees : l'enfant designe par `childAt()` est deja un bouton, mais le
# joint lui appartient au conteneur.
TOGGLE_BLOCKERS: tuple[type, ...] = (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QLineEdit,
    SegmentedControl,
)

# Infobulles des champs de filtrage : fonctions et non constantes de module, parce
# qu'une constante évaluée à l'import ne suivrait pas un changement de langue à chaud.


def asset_combo_tip() -> str:
    """Infobulle du combo « par défaut » : la deuxième ligne porte le nom courant, parce
    que la boîte fermée est plafonnée en largeur (`$w_asset_combo_max`) et peut donc couper le nom."""
    return t("Asset téléchargé automatiquement pour les prochaines versions")


def asset_filter_tip() -> str:
    return t(
        "Liste de motifs séparés par point-virgule.\n"
        "Glob : '*.whl' (suffixe), 'PySide6-*' (préfixe), '*py3.13*' (chaîne).\n"
        "Les caractères - _ . , sont normaux. Un motif 're:...' est une regex.\n"
        "Rien n'est conservé en base si un asset ne passe pas le filtre : re-fetch après modification."
    )


def tag_exclude_tip() -> str:
    return t(
        "Tags à rejeter, mêmes motifs que le motif retenu (point-virgule, glob ou 're:').\n"
        "Un tag rejeté passe dans la colonne de droite : il n'est jamais comparé à ta version locale.\n"
        "Exemple : *-rc*;*-beta*"
    )


def tag_pattern_tip() -> str:
    return t(
        "Forme des tags comparés à ta version locale (glob : * et ?).\n"
        "Exemples : {example}, v0.*, release-??\n"
        "Vide = tous les tags. Plusieurs motifs séparés par point-virgule, un motif\n"
        "'re:...' est une regex. Un tag qui ne correspond pas reste affiché à droite,\n"
        "pour information, mais n'est jamais comparé à ta version locale."
    ).format(example=TAG_PATTERN_EXAMPLE)


def drag_tip() -> str:
    return t(
        "Glisse cette poignée sur un autre bandeau pour changer l'ordre des repos.\n"
        "La zone d'ancrage est gardée : le drop n'agit que sur un autre bandeau."
    )


def assets_switch_tip() -> str:
    """Infobulle de la case `assets` : elle dit ce qui est jeté, pas ce qui est filtré à la source."""
    return t(
        "Case décochée : les assets ne sont pas conservés, ni en base ni dans les lignes.\n"
        "La requête GitHub reste la même (les assets arrivent avec la release) : ils sont\n"
        "jetés à la réception. Re-fetch après modification.\n"
        "Case décochée : les réglages à garder / sauf / par défaut et la ligne d'infos\n"
        "disparaissent ; le fetch et les scripts remontent à côté de la case."
    )


ASSET_COMBO_MARGIN = 4 * SPACING + 4
REPO_ORDER_MIME = "application/x-releasewatch-repo"
DRAG_GLYPH = "≡"


def repo_order_mime_data(repo_id: str) -> QMimeData:
    mime = QMimeData()
    mime.setData(REPO_ORDER_MIME, repo_id.encode("utf-8"))
    return mime


def repo_order_source_id(mime: QMimeData) -> str | None:
    if not mime.hasFormat(REPO_ORDER_MIME):
        return None
    return mime.data(REPO_ORDER_MIME).toStdString()


class _FilterLine(NamedTuple):
    """Mesures d'une ligne de réglages, utilisées pour aligner les colonnes de filtres."""

    holder: QWidget
    spacer: QSpacerItem
    group_x: int  # abscisse du groupe quand l'espaceur est à 0
    group: int  # largeur du groupe « à garder / sauf »
    suffix: int  # largeur de ce qui suit le groupe, collée au bord droit
    free: int  # place que l'espaceur peut encore prendre sans replier la ligne
    gaps: int  # nombre d'écarts du layout entre la fin du groupe et le début du suffixe
    spacing: int  # écart du layout de cette ligne
    width: int  # largeur utile de la ligne


def _tool(object_name: str, text: str, tip: str) -> QToolButton:
    """QToolButton n'accepte pas de texte au constructeur en PySide6."""
    button = QToolButton()
    button.setObjectName(object_name)
    button.setText(text)
    button.setToolTip(tip)
    return button


def _field(object_name: str, placeholder: str, tip: str) -> GhostLineEdit:
    """Champ de filtre : l'espace-placeholder est en italique, la saisie ne l'est jamais.

    Largeur fixe en Python (Fixed) et plafonnée par le `.qss` (`$w_filter_field`) : un champ
    Expanding recevrait quelques pixels de surplus sur une ligne et pas sur l'autre, et les
    boîtes des deux lignes de réglages cesseraient de se superposer (voir `_sync_filter_columns`).
    """
    edit = GhostLineEdit()
    edit.setObjectName(object_name)
    edit.setPlaceholderText(placeholder)
    edit.setToolTip(tip)
    edit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    return edit


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("bannerCaption")
    return label


def _column_toggle(object_name: str, side: str, text: str) -> QToolButton:
    """Bouton de repli d'une colonne : enfoncé (coché) = colonne affichée, grise = colonne masquée."""
    button = QToolButton()
    button.setObjectName(object_name)
    button.setText(text)
    button.setCheckable(True)
    button.setChecked(True)
    # Propriété lue par le QSS ([side="left"] / [side="right"]) : le côté se voit sans texte.
    set_property(button, "side", side)
    return button


class RepoBanner(QFrame):
    message = Signal(str, object)
    fetch_requested = Signal(str)
    notes_requested = Signal(str, object)
    download_requested = Signal(str, object, object)
    folder_requested = Signal(str)
    script_requested = Signal(str, int)
    scripts_requested = Signal(str)
    remove_requested = Signal(str)
    open_url_requested = Signal(str)
    download_dir_requested = Signal(str)

    def __init__(self, repo: Repo, save: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("repoBanner")
        self._repo = repo
        self._save = save
        self._busy = False
        self._rows: list[ReleaseRow] = []
        self._drag_candidate = False
        self._drag_origin = QPointF(0, 0)

        root = QVBoxLayout(self)
        # Le padding du bandeau vient du QSS (tokens pad_banner_v / pad_banner_h) :
        # des margins ici s'ajouteraient au QSS et reinfleraient le bandeau.
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        root.addWidget(self._build_head_row())
        root.addWidget(self._build_info_row())
        root.addWidget(self._build_assets_row())
        root.addWidget(self._build_filters_row())
        root.addWidget(self._build_versions_panel())

        self._watch_toggle()
        self.connect_actions()
        self.refresh()

    # ------------------------------------------------------------------ construction

    def _build_head_row(self) -> QWidget:
        """Une ligne, tout le temps : c'est ce qui reste quand le bandeau est replié."""
        holder = QWidget(self)
        holder.setObjectName("bannerHead")
        layout = FlowLayout(holder, SPACING)
        layout.setContentsMargins(0, 0, 0, 0)

        self.toggle = _tool("bannerToggle", EXPANDED_GLYPH, t("Replier / déployer les versions"))

        self.status_label = QLabel()
        self.status_label.setObjectName("bannerStatus")

        self.title_label = ElidedLabel(self._repo.title)
        self.title_label.setObjectName("bannerTitle")
        # Le nom du repo est ce qui doit rester lisible quand la fenêtre rétrécit :
        # il ne se réduit pas, c'est le libellé des versions qui s'élide.
        self.title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # Cran de taille courant du titre (voir TITLE_FIT_STEPS) : "" = taille du QSS.
        self._title_fit_step: str | None = None

        self.local_label = ElidedLabel()
        self.local_label.setObjectName("lblLocalVersion")
        # Seul ce label est Expanding : lui seul absorbe le manque de place.
        self.local_label.setMinimumWidth(LOCAL_LABEL_MIN)

        self.btn_fetch = QPushButton(t("Fetch"))
        self.btn_fetch.setObjectName("btnFetch")
        self.btn_fetch.setToolTip(t("Interroge GitHub pour ce repo uniquement (5 à 25 dernières versions)."))

        self.btn_exclude = _tool(
            "btnExcludeCheckAll",
            EXCLUDE_GLYPH,
            t("Inclus dans 'Vérifier tous les repos'. Clique pour l'en exclure."),
        )
        self.btn_exclude.setCheckable(True)

        self.btn_launch = QPushButton(t("Script ⤶"))
        self.btn_launch.setObjectName("btnLaunch")

        self.btn_scripts = _tool("btnPickScript", "🛠", t("Choisir les scripts liés à ce repo"))

        self.btn_github = QPushButton("🌐")
        self.btn_github.setObjectName("btnOpenGithub")
        self.btn_github.setToolTip(t("Ouvre {url} dans le navigateur").format(url=self._repo.versions_url))

        self.drag_handle = _tool("btnDragOrder", DRAG_GLYPH, drag_tip())
        self.drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.btn_more = _tool("btnMore", "⋯", t("Renommer, version manuelle, source des versions, dossier, supprimer"))

        # Fetch et ⊘ d'une part, Script et 🛠 d'autre part : deux paires d'actions solidaires, chaque
        # paire sous une seule bordure. Les `objectName` des boutons ne bougent pas : le contrat de
        # tests et les regles QSS les retrouvent dans le sous-arbre du conteneur.
        self.grp_fetch = segmented("grpFetch", self.btn_fetch, self.btn_exclude)
        self.grp_script = segmented("grpScript", self.btn_launch, self.btn_scripts)

        layout.addWidget(self.toggle)
        layout.addWidget(self.drag_handle)
        layout.addWidget(self.status_label)
        # Pas de stretch au milieu : le titre absorbe l'espace restant de sa ligne et s'élide.
        # Les champs trop larges passent à la ligne au lieu de chasser les boutons.
        layout.addWidget(self.title_label)
        layout.addWidget(self.local_label)
        layout.addWidget(self.grp_fetch)
        layout.addWidget(self.grp_script)
        layout.addWidget(self.btn_github)
        layout.addWidget(self.btn_more)
        self.head_row = holder
        return holder

    def _build_filters_row(self) -> QWidget:
        """Toggles des deux colonnes, caps et motifs de tags : cachée quand le bandeau est replié."""
        holder = QWidget(self)
        holder.setObjectName("bannerFilters")
        layout = FlowLayout(holder, SPACING)
        # Marge seulement au-dessus des éléments : le bas de la ligne est pris par le trait
        # (border-bottom du holder) où les deux boutons de colonne sont collés.
        layout.setContentsMargins(0, token_px("row_pad_v"), 0, 0)

        self.cmb_versions = QComboBox()
        self.cmb_versions.setObjectName("cmbMaxVersions")
        for choice in MAX_VERSIONS_CHOICES:
            self.cmb_versions.addItem(str(choice))
        self.cmb_versions.setFixedWidth(38)
        self.cmb_versions.setToolTip(t("Nombre de versions retenues à gauche (colonne comparée)"))

        self.cmb_max_rejected = QComboBox()
        self.cmb_max_rejected.setObjectName("cmbMaxRejectedVersions")
        for choice in MAX_REJECTED_VERSIONS_CHOICES:
            self.cmb_max_rejected.addItem(str(choice))
        self.cmb_max_rejected.setFixedWidth(38)
        self.cmb_max_rejected.setToolTip(t("Nombre de versions rejetées ou obsolètes affichées à droite"))

        self.edit_pattern = _field("editTagPattern", TAG_PATTERN_EXAMPLE, tag_pattern_tip())
        self.edit_exclude = _field("editTagExclude", "*-rc*;*-beta*", tag_exclude_tip())

        # Mots courts : un QToolButton prend ~110px de marges Qt, et « versions retenues »
        # imposerait 239px à la ligne, donc au bandeau tout entier. Le libellé complet et
        # toutes les explications de la colonne tiennent dans l'infobulle du bouton.
        self.btn_col_left = _column_toggle("btnColLeft", "left", t("↓↑ retenues"))
        self.btn_col_right = _column_toggle("btnColRight", "right", t("rejetées ↓↑"))

        # Même intitulé que la ligne d'assets : les deux groupes ont exactement la même
        # largeur, ce qui rend l'alignement possible (voir `_sync_filter_columns`).
        self.cap_tag_keep = _caption(t("à garder"))
        self.cap_tag_except = _caption(t("sauf"))

        # Les réglages de colonnes restent aux deux extrémités de la ligne. Le groupe
        # « à garder / sauf » n'est plus centré par deux stretchs : un espaceur fixe devant
        # le pose à l'abscisse commune aux deux lignes, et le stretch derrière lui laisse
        # juste assez de place pour coller le suffixe au bord droit.
        layout.addWidget(self.btn_col_left)
        layout.addWidget(self.cmb_versions)
        self.filters_spacer = layout.add_fixed_spacer()
        layout.addWidget(self.cap_tag_keep)
        layout.addWidget(self.edit_pattern)
        layout.addWidget(self.cap_tag_except)
        layout.addWidget(self.edit_exclude)
        layout.add_stretch(CENTER_STRETCH)
        layout.addWidget(self.cmb_max_rejected)
        layout.addWidget(self.btn_col_right)
        # Le trait du bas est dessiné par le holder (`#bannerFilters` border-bottom) : les deux
        # boutons de colonne sont collés dessus, les autres champs restent en retrait de la
        # réserve de palette. Un `padding`/`margin` dans le `.qss` ne déplacerait rien du tout.
        layout.set_line_valign(Qt.AlignmentFlag.AlignBottom, token_px("filters_gap_v"))
        for toggle in (self.btn_col_left, self.btn_col_right):
            layout.set_valign(toggle, Qt.AlignmentFlag.AlignBottom)
        self.filters_row = holder
        return holder

    def _build_assets_row(self) -> QWidget:
        """Recueil et filtrage des assets, plus l'asset par défaut."""
        holder = QWidget(self)
        holder.setObjectName("bannerAssets")
        layout = FlowLayout(holder, SPACING)
        # Marge seulement au-dessus des éléments : l'espace sous la ligne est déjà rendu par
        # l'espacement du layout du bandeau (4px) avant le trait du haut de `bannerFilters`.
        layout.setContentsMargins(0, token_px("row_pad_v"), 0, 0)

        self.chk_assets = QCheckBox(t("assets"))
        self.chk_assets.setObjectName("chkAssets")
        self.chk_assets.setToolTip(assets_switch_tip())

        self.edit_asset_include = _field("editAssetInclude", "*.whl;*setup.exe", asset_filter_tip())
        self.edit_asset_exclude = _field("editAssetExclude", "*.tar.*;*.deb", asset_filter_tip())

        self.cmb_asset = QComboBox()
        self.cmb_asset.setObjectName("cmbDefaultAsset")
        # La boîte se dimensionne sur son contenu (item le plus large), pas sur la place
        # restante de la ligne : Preferred + AdjustToContents, plafonnée par `$w_asset_combo_max`
        # dans le QSS. MinimumExpanding/Expanding ne font que la gonfler.
        self.cmb_asset.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.cmb_asset.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_asset.setToolTip(asset_combo_tip())

        self.asset_info_label = ElidedLabel()
        self.asset_info_label.setObjectName("lblAssetInfo")
        self.asset_info_label.setToolTip(
            t("Recueil des assets désactivé : fetch, scripts et exclusion restent visibles.")
        )

        self.cap_asset_keep = _caption(t("à garder"))
        self.cap_asset_except = _caption(t("sauf"))
        self.cap_asset_default = _caption(t("par défaut"))
        self._asset_controls: tuple[QWidget, ...] = (
            self.cap_asset_keep,
            self.edit_asset_include,
            self.cap_asset_except,
            self.edit_asset_exclude,
            self.cap_asset_default,
            self.cmb_asset,
        )

        # Le combo « par défaut » n'est plus Expanding : il prend sa largeur de contenu, et le
        # stretch avale le reliquat. Le groupe « à garder / sauf » reçoit la même abscisse que
        # celui de la ligne de filtres (voir `_sync_filter_columns`) : les deux colonnes de
        # boîtes se superposent au pixel.
        layout.addWidget(self.chk_assets)
        layout.addWidget(self.asset_info_label)
        self.assets_spacer = layout.add_fixed_spacer()
        layout.addWidget(self.cap_asset_keep)
        layout.addWidget(self.edit_asset_include)
        layout.addWidget(self.cap_asset_except)
        layout.addWidget(self.edit_asset_exclude)
        layout.add_stretch(CENTER_STRETCH)
        layout.addWidget(self.cap_asset_default)
        layout.addWidget(self.cmb_asset)
        self.assets_row = holder
        return holder

    def _build_info_row(self) -> QWidget:
        """Informations : dernier fetch, scripts, dossier de téléchargement."""
        holder = QWidget(self)
        holder.setObjectName("bannerInfo")
        layout = FlowLayout(holder, SPACING)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hint_label = ElidedLabel()
        self.hint_label.setObjectName("lblHint")

        self.btn_download_dir = _tool(
            "btnDownloadDir",
            "⤓",
            t("Dossier où les assets sont téléchargés pour ce repo. Clique pour le changer."),
        )

        layout.addWidget(self.hint_label)
        layout.addWidget(self.btn_download_dir)
        self.info_row = holder
        return holder

    def _build_versions_panel(self) -> QWidget:
        """Deux colonnes : à gauche les tags autorisés par le filtre, à droite les rejetés ou obsolètes."""
        self.versions_panel = QWidget(self)
        self.versions_panel.setObjectName("versionsPanel")
        holder = QHBoxLayout(self.versions_panel)
        holder.setContentsMargins(0, 0, 0, 0)
        holder.setSpacing(0)

        self._col_body: dict[str, QWidget] = {}
        self._col_layout: dict[str, QVBoxLayout] = {}
        self._col_widget: dict[str, QWidget] = {}
        self._columns_box = holder
        self._two_columns = True

        left = self._build_column("left")
        right = self._build_column("right")
        holder.addWidget(left, 1)
        holder.addWidget(right, 1)
        return self.versions_panel

    def _build_column(self, side: str) -> QWidget:
        """Aucune tête de colonne : les toggles et les ⓘ vivent dans la ligne de filtres."""
        column = QWidget(self.versions_panel)
        column.setObjectName("versionColumn")
        # Propriété lue par le QSS (`#versionColumn[side="right"]`) : colonne de droite en retrait.
        set_property(column, "side", side)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        body = QWidget(column)
        body.setObjectName("colBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        layout.addWidget(body, 1)

        self._col_body[side] = body
        self._col_layout[side] = body_layout
        self._col_widget[side] = column
        return column

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Pose l'espaceur de colonne AVANT la passe de layout : le calcul ne lit aucune
        # géométrie, donc la ligne n'a jamais à se replier puis se déplier pour se recalage.
        self._sync_filter_columns()
        for holder in (self.head_row, self.filters_row, self.assets_row, self.info_row):
            apply_flow_height(holder)
        # Le changement d'orientation et le re-polish ne peuvent pas se faire pendant
        # la passe de layout qui déclenche l'événement : Qt le paierait en crash.
        QTimer.singleShot(0, self._apply_columns_layout)
        QTimer.singleShot(0, self._fit_title_font)

    def _sync_filter_columns(self) -> None:
        """Aligne les boîtes « à garder » / « sauf » des deux lignes de réglages.

        Les deux groupes portent les mêmes intitulés et des champs de largeur identique
        (`$w_filter_field` du `.qss`) : ils se superposent dès qu'on leur donne la même abscisse de
        départ. Cette abscisse est fixée à la fin du préfixe le plus large : aucune ligne ne peut
        la franchir vers la gauche, et elle ne dépend pas de la largeur de la ligne. Le groupe ne
        bouge donc jamais quand la fenêtre est redimensionnée : seul le jeu entre le groupe et les
        réglages de droite change.

        Tout est mesuré sur les largeurs naturelles des items, avant la passe de layout : aucun
        aller-retour n'est visible pendant le redimensionnement. Si le jeu ne suffit pas sur une
        ligne (l'espaceur la ferait plier, ou écraserait les réglages de droite), on renonce sur
        les deux lignes : un alignement à moitié saute aux yeux, pas un alignement absent.
        """
        rows = (
            (self.filters_row, self.filters_spacer, self.cap_tag_keep, self.edit_exclude, self.cmb_max_rejected),
            (
                self.assets_row,
                self.assets_spacer,
                self.cap_asset_keep,
                self.edit_asset_exclude,
                self.cap_asset_default,
            ),
        )
        measured: list[_FilterLine] = []
        for holder, spacer, group_first, group_last, suffix_head in rows:
            row_layout = holder.layout()
            if not isinstance(row_layout, FlowLayout):
                continue
            parts = row_layout.natural_line(holder.width(), spacer, group_first, group_last, suffix_head)
            if parts is None or parts[3] < 0:
                self._set_filter_spacer(holder, spacer, 0)
                continue
            prefix, group, suffix, free, gaps = parts
            measured.append(
                _FilterLine(
                    holder=holder,
                    spacer=spacer,
                    group_x=prefix,
                    group=group,
                    suffix=suffix,
                    free=free,
                    gaps=gaps,
                    spacing=row_layout.spacing(),
                    width=holder.width(),
                )
            )
        if len(measured) < 2:
            return
        group = max(line.group for line in measured)
        chosen_x = max(line.group_x for line in measured)
        for line in measured:
            if chosen_x + line.group + line.gaps * line.spacing + line.suffix > line.width:
                chosen_x = line.group_x
                break
        for line in measured:
            pad = chosen_x - line.group_x
            if pad > line.free:
                chosen_x = min(other.group_x for other in measured)
                break
        for line in measured:
            self._set_filter_spacer(line.holder, line.spacer, max(0, chosen_x - line.group_x))

    def _set_filter_spacer(self, holder: QWidget, spacer: QSpacerItem, width: int) -> None:
        """Pose la largeur d'un espaceur de réglages, sans relancer de passe de layout.

        Cet appel a lieu pendant `resizeEvent` : la passe de layout est déjà en cours. Demander
        ici une invalidation ou un minimum de hauteur relancerait la passe qui vient de déclencher
        l'événement, et la fenêtre comme le panneau latéral cesseraient de suivre la souris.
        """
        layout = holder.layout()
        wanted = max(0, width)
        if not isinstance(layout, FlowLayout) or spacer.sizeHint().width() == wanted:
            return
        layout.set_fixed_spacer_width(spacer, wanted)
        holder.updateGeometry()

    def _apply_filter_columns(self) -> None:
        """Recalcul demandé hors passe de layout (thème, case assets, contenu du combo).

        Là, rien n'est en cours : l'espaceur posé doit être réclamé au layout, et la hauteur de
        ligne doit suivre une largeur utile qui a changé.
        """
        self._sync_filter_columns()
        for holder in (self.filters_row, self.assets_row):
            layout = holder.layout()
            if isinstance(layout, FlowLayout):
                layout.invalidate()
                layout.activate()
            apply_flow_height(holder)

    def _apply_columns_layout(self) -> None:
        """Étroit : les deux colonnes s'empilent, chaque ligne de version garde ses boutons."""
        two_columns = self.width() >= TWO_COLUMNS_MIN
        if two_columns == self._two_columns:
            return
        self._two_columns = two_columns
        self._columns_box.setDirection(
            QBoxLayout.Direction.LeftToRight if two_columns else QBoxLayout.Direction.TopToBottom
        )
        # La propriété doit être réévaluée par le style : `set_property` fait le polish.
        set_property(self.versions_panel, "stacked", "" if two_columns else "1")
        for side in ("left", "right"):
            set_property(self._col_widget[side], "stacked", "" if two_columns else "1")

    def columns_stacked(self) -> bool:
        return not self._two_columns

    def title_fit_step(self) -> str:
        """Cran de taille actuellement appliqué au titre (`""` = taille normale du QSS)."""
        return self._title_fit_step or ""

    def _fit_title_font(self) -> None:
        """Le nom du repo doit rester entier : on l'écrit plus petit avant de le couper.

        La largeur de la ligne de tête est la place maximale où le titre peut tenir, fût-ce
        tout seul sur sa ligne. On prend le plus grand cran dont le texte tient, mesuré avec
        les tailles de la palette (le QSS garde la source unique des tailles).
        """
        room = self.head_row.width()
        if room <= 0:
            return
        chosen = TITLE_FIT_STEPS[-1]
        base = self.title_label.font()
        full = self.title_label.full_text()
        for step, token in TITLE_FIT_STEPS:
            candidate = QFont(base)
            candidate.setPixelSize(token_px(token))
            if QFontMetrics(candidate).horizontalAdvance(full) <= room:
                chosen = (step, token)
                break
        if chosen[0] == (self._title_fit_step or ""):
            return
        self._title_fit_step = chosen[0]
        # La propriete porte le cran ; la taille vient de la règle QSS correspondante.
        set_property(self.title_label, "fsize", chosen[0])

    def _watch_toggle(self) -> None:
        """Le double-clic n'importe où sur le bandeau (sauf boutons et lignes) plie/déplie."""
        watched: list[QWidget] = [self, self.head_row, self.filters_row, self.assets_row, self.info_row]
        for side in ("left", "right"):
            watched.append(self._col_body[side].parentWidget() or self._col_body[side])
            watched.append(self._col_body[side])
        for widget in watched:
            widget.installEventFilter(self)
        self.drag_handle.installEventFilter(self)

    def detail_rows(self) -> list[QWidget]:
        """Les lignes cachées quand le bandeau est replié."""
        return [self.filters_row, self.assets_row, self.info_row]

    def rows_by_side(self) -> dict[str, list[ReleaseRow]]:
        """Lignes de version affichées, par colonne. Sert aussi aux contrôles hors écran."""
        result: dict[str, list[ReleaseRow]] = {}
        for side, layout in self._col_layout.items():
            rows: list[ReleaseRow] = []
            for position in range(layout.count()):
                item = layout.itemAt(position)
                widget = item.widget() if item is not None else None
                if isinstance(widget, ReleaseRow):
                    rows.append(widget)
            result[side] = rows
        return result

    def column_bodies(self) -> dict[str, QWidget]:
        return dict(self._col_body)

    def column_toggles(self) -> dict[str, QToolButton]:
        """Boutons de repli : ils vivent dans la ligne de filtres, plus au-dessus des colonnes."""
        return {"left": self.btn_col_left, "right": self.btn_col_right}

    def relayout_release_rows(self) -> None:
        """Recalcule les largeurs alignées et les hauteurs après un changement de style."""
        # `AdjustToContents` ne se déclenche que sur un changement de modèle : après un
        # rechargement de thème (police différente), reposer la même politique vide le cache
        # de largeur du combo et prévient le layout (pas d'API publique pour ce recalcul).
        self.cmb_asset.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._apply_asset_combo_width()
        self._align_rows_text_widths()
        for row in self._rows:
            row_layout = row.layout()
            if row_layout is not None:
                row_layout.invalidate()
            row._apply_release_height()
            row.updateGeometry()
        for side in ("left", "right"):
            self._col_layout[side].invalidate()
            self._col_layout[side].activate()
        self._col_body["left"].updateGeometry()
        self._col_body["right"].updateGeometry()
        self.versions_panel.updateGeometry()
        self._apply_columns_layout()
        apply_flow_height(self)
        self._fit_title_font()
        # Police et largeurs changent après un rechargement de thème : l'abscisse commune
        # des deux lignes de réglages est recalculée sur ces nouvelles largeurs naturelles.
        self._apply_filter_columns()

    # ------------------------------------------------------------------ rafraichissement

    def refresh(self) -> None:
        status = self._repo.status
        set_status(self, status)
        set_status(self.status_label, status)
        set_status(self.local_label, status)
        self.title_label.set_full_text(self._repo.title)
        self.status_label.setText(STATUS_GLYPH)
        self.status_label.setToolTip(self._status_tip(status))
        self.local_label.set_full_text(self._local_text())
        self.local_label.setToolTip(self._local_tip())
        self.hint_label.set_full_text(self._hint_text())
        self.hint_label.setToolTip(self._hint_tip())
        self.toggle.setText(COLLAPSED_GLYPH if self._repo.collapsed else EXPANDED_GLYPH)
        self._sync_versions_combo()
        self._sync_pattern(self.edit_pattern, self._repo.tag_pattern)
        self._sync_pattern(self.edit_exclude, self._repo.tag_exclude)
        self._sync_pattern(self.edit_asset_include, self._repo.asset_include)
        self._sync_pattern(self.edit_asset_exclude, self._repo.asset_exclude)
        self._sync_exclude()
        self._sync_assets_switch()
        self._sync_asset_combo()
        self._rebuild_rows()
        self._sync_launch()
        self._apply_collapsed()
        # Le titre peut avoir changé (renommage, version locale) : le cran de taille suit.
        QTimer.singleShot(0, self._fit_title_font)

    def retranslate(self) -> None:
        """Réécrit les textes fixes du bandeau dans la langue active.

        Les textes dépendant de l'état (état, version locale, infos, colonnes, scripts, assets)
        sont réécrits par `refresh()`, qui passe par les mêmes fonctions `t()` : un seul chemin
        de traduction, pas de seconde liste de libellés à entretenir.
        """
        self.toggle.setToolTip(t("Replier / déployer les versions"))
        self.btn_fetch.setText(t("Fetch…") if self._busy else t("Fetch"))
        self.btn_launch.setText(t("Script ⤶"))
        self.btn_scripts.setToolTip(t("Choisir les scripts liés à ce repo"))
        self.btn_github.setToolTip(t("Ouvre {url} dans le navigateur").format(url=self._repo.versions_url))
        self.btn_more.setToolTip(t("Renommer, version manuelle, source des versions, dossier, supprimer"))
        self.drag_handle.setToolTip(drag_tip())
        self.btn_download_dir.setToolTip(
            t("Dossier où les assets sont téléchargés pour ce repo. Clique pour le changer.")
        )
        self.cmb_versions.setToolTip(t("Nombre de versions retenues à gauche (colonne comparée)"))
        self.cmb_max_rejected.setToolTip(t("Nombre de versions rejetées ou obsolètes affichées à droite"))
        self.edit_pattern.setToolTip(tag_pattern_tip())
        self.edit_exclude.setToolTip(tag_exclude_tip())
        self.edit_asset_include.setToolTip(asset_filter_tip())
        self.edit_asset_exclude.setToolTip(asset_filter_tip())
        self.cmb_asset.setToolTip(asset_combo_tip())
        self.asset_info_label.setToolTip(
            t("Recueil des assets désactivé : fetch, scripts et exclusion restent visibles.")
        )
        self.chk_assets.setText(t("assets"))
        self.chk_assets.setToolTip(assets_switch_tip())
        self.cap_tag_keep.setText(t("à garder"))
        self.cap_tag_except.setText(t("sauf"))
        self.cap_asset_keep.setText(t("à garder"))
        self.cap_asset_except.setText(t("sauf"))
        self.cap_asset_default.setText(t("par défaut"))
        self.btn_col_left.setText(t("↓↑ retenues"))
        self.btn_col_right.setText(t("rejetées ↓↑"))
        for row in self._rows:
            row.retranslate()
        self.refresh()
        # Les intitulés changent de largeur selon la langue : l'abscisse commune des deux
        # lignes de réglages est recalculée sur les nouvelles largeurs naturelles.
        self._apply_filter_columns()

    def _status_tip(self, status: Status) -> str:
        """Le libellé d'état ne s'affiche pas : seule la couleur porte l'information."""
        lines: list[str] = [status_label(status), f"{self._repo.owner}/{self._repo.name}"]
        latest = self._repo.latest
        if latest is not None:
            lines.append(t("dernière : {tag}").format(tag=latest.tag))
        if self._repo.tag_pattern.strip():
            lines.append(t("motif des tags à garder : {pattern}").format(pattern=self._repo.tag_pattern.strip()))
            lines.append(
                t("{kept} tag(s) retenu(s) sur {total}").format(
                    kept=len(self._repo.matching_releases), total=len(self._repo.releases)
                )
            )
        if self._repo.tag_exclude.strip():
            lines.append(t("tags exclus : {exclude}").format(exclude=self._repo.tag_exclude.strip()))
        if self._repo.local_version:
            lines.append(t("version locale : {version}").format(version=self._repo.local_version))
        else:
            lines.append(t("aucune version locale définie"))
        if self._repo.last_fetch_at:
            lines.append(t("dernier fetch : {when}").format(when=self._repo.last_fetch_at.replace("T", " ")[:16]))
        if self._repo.last_fetch_error:
            lines.append(t("erreur fetch : {error}").format(error=self._repo.last_fetch_error))
        return "\n".join(lines)

    def _local_text(self) -> str:
        """Le libellé qui cede la place quand le bandeau retrecit : le plus court possible."""
        local = self._repo.local_version
        latest = self._repo.latest
        if not local:
            return t("vers. locale ?")
        if latest is not None and latest.tag != local:
            return f"{local} -> {latest.tag}"
        return local

    def _local_tip(self) -> str:
        lines: list[str] = [
            t("Version que tu as désignée comme installée localement."),
            t("Le programme n'interroge jamais l'installation locale."),
        ]
        origin = (
            t("désignée sur une release") if self._repo.local_version_source == "release" else t("saisie à la main")
        )
        lines.append(t("Source : {origin}.").format(origin=origin))
        pattern = self._repo.tag_pattern.strip()
        if pattern:
            lines.append(t("Comparée au tag pattern : {pattern}").format(pattern=pattern))
        else:
            lines.append(t("Comparée à tous les tags récupérés."))
        if self._repo.tag_exclude.strip():
            lines.append(t("Sauf ceux exclus par : {exclude}").format(exclude=self._repo.tag_exclude.strip()))
        lines.append(t("La flèche montre l'écart avec la dernière version retenue."))
        lines.append(t("Tu peux désigner la version locale sur n'importe quelle ligne, y compris à droite."))
        return "\n".join(lines)

    def _hint_text(self) -> str:
        parts: list[str] = []
        if self._repo.last_fetch_at:
            parts.append(t("fetch {when}").format(when=self._repo.last_fetch_at.replace("T", " ")[:16]))
        else:
            parts.append(t("jamais fetché"))
        if self._repo.excluded_check_all:
            parts.append(t("exclu"))
        parts.append(t("source : {source}").format(source=self._source_word()))
        if self._repo.scripts:
            nbr_scripts = len(self._repo.scripts)
            parts.append(
                t("{n} scripts").format(n=nbr_scripts) if nbr_scripts > 1 else t("{n} script").format(n=nbr_scripts)
            )
        parts.append(
            t("⤓ {folder}").format(folder=self._repo.download_dir or t("(dossier demandé à chaque téléchargement)"))
        )
        return "  ·  ".join(parts)

    def _hint_tip(self) -> str:
        lines: list[str] = [
            t("Dernière récupération, scripts raccourcis et dossier d'écriture des assets."),
            t("Le dossier n'est pas interrogé : l'application ne vérifie pas ce qui est installé."),
        ]
        if self._repo.last_fetch_error:
            lines.append(t("Erreur du dernier fetch : {error}").format(error=self._repo.last_fetch_error))
        return "\n".join(lines)

    def _sync_versions_combo(self) -> None:
        index = self.cmb_versions.findData(str(self._repo.max_versions))
        if index < 0:
            self.cmb_versions.setCurrentText(str(self._repo.max_versions))
        else:
            self.cmb_versions.setCurrentIndex(index)
        rejected_index = self.cmb_max_rejected.findData(str(self._repo.max_rejected_versions))
        if rejected_index < 0:
            self.cmb_max_rejected.setCurrentText(str(self._repo.max_rejected_versions))
        else:
            self.cmb_max_rejected.setCurrentIndex(rejected_index)

    def _sync_pattern(self, edit: QLineEdit, wanted: str) -> None:
        """Ne pas écraser une saisie en cours : le `refresh` peut arriver pendant la frappe."""
        if edit.text() == wanted:
            return
        edit.blockSignals(True)
        edit.setText(wanted)
        edit.blockSignals(False)

    def _sync_exclude(self) -> None:
        excluded = self._repo.excluded_check_all
        self.btn_exclude.setChecked(excluded)
        if excluded:
            self.btn_exclude.setToolTip(
                t(
                    "EXCLU de 'Vérifier tous les repos'.\n"
                    "Le bouton Fetch de ce bandeau fonctionne toujours. Clique pour réinclure."
                )
            )
        else:
            self.btn_exclude.setToolTip(
                t("Inclus dans 'Vérifier tous les repos'.\nClique pour exclure ce repo du contrôle global.")
            )
        self.btn_exclude.setText(EXCLUDE_GLYPH)

    def _sync_assets_switch(self) -> None:
        enabled = self._repo.assets_enabled
        if self.chk_assets.isChecked() != enabled:
            self.chk_assets.blockSignals(True)
            self.chk_assets.setChecked(enabled)
            self.chk_assets.blockSignals(False)
        for widget in (self.edit_asset_include, self.edit_asset_exclude, self.cmb_asset):
            widget.setEnabled(enabled)
        self.asset_info_label.set_full_text(self._asset_info_text())
        self._apply_asset_visibility()

    def _apply_asset_visibility(self) -> None:
        """Case décochée : on masque les réglages d'assets et la ligne d'infos, pas la case `assets`."""
        expanded = not self._repo.collapsed
        enabled = self._repo.assets_enabled
        self.chk_assets.setVisible(expanded)
        self.asset_info_label.setVisible(expanded and not enabled)
        self.asset_info_label.updateGeometry()
        for widget in self._asset_controls:
            widget.setVisible(expanded and enabled)
            widget.updateGeometry()
        self.info_row.setVisible(expanded and enabled)
        self.info_row.updateGeometry()
        # Les champs masqués laissent toute la place à la ligne : les espaceurs doivent
        # retomber à 0, sinon ils poussent le résumé non-asset vers la droite.
        self._apply_filter_columns()

    def _asset_info_text(self) -> str:
        parts: list[str] = []
        if self._repo.last_fetch_at:
            parts.append(t("fetch {when}").format(when=self._repo.last_fetch_at.replace("T", " ")[:16]))
        else:
            parts.append(t("jamais fetché"))
        parts.append(t("source : {source}").format(source=self._source_word()))
        if self._repo.scripts:
            nbr_scripts = len(self._repo.scripts)
            parts.append(
                t("{n} scripts").format(n=nbr_scripts) if nbr_scripts > 1 else t("{n} script").format(n=nbr_scripts)
            )
        if self._repo.excluded_check_all:
            parts.append(t("exclu de 'Vérifier tous les repos'"))
        return "  ·  ".join(parts)

    def _apply_asset_combo_width(self) -> None:
        widest = 0
        metrics = self.cmb_asset.fontMetrics()
        for index in range(self.cmb_asset.count()):
            widest = max(widest, metrics.horizontalAdvance(self.cmb_asset.itemText(index)))
        view = self.cmb_asset.view()
        if view is not None and widest > 0:
            view.setMinimumWidth(widest + ASSET_COMBO_MARGIN)

    def _sync_asset_tooltip(self) -> None:
        """Le nom courant est rappelé dans l'infobulle : la boîte fermée est plafonnée en largeur."""
        name = self.cmb_asset.currentText() or t("(choisir à chaque fois)")
        self.cmb_asset.setToolTip(f"{asset_combo_tip()}\n{t('Choisi : {name}').format(name=name)}")

    def _sync_asset_combo(self) -> None:
        self.cmb_asset.blockSignals(True)
        self.cmb_asset.clear()
        names: list[str] = []
        for release in self._repo.releases:
            for asset in release.assets:
                if asset.name not in names:
                    names.append(asset.name)
        self.cmb_asset.addItem(t("(choisir à chaque fois)"))
        for name in names:
            self.cmb_asset.addItem(name)
        position = self.cmb_asset.findText(self._repo.default_asset_name)
        self.cmb_asset.setCurrentIndex(position if position >= 0 else 0)
        self.cmb_asset.blockSignals(False)
        self._apply_asset_combo_width()
        # Signaux bloqués pendant le remplissage : `currentTextChanged` n'est pas émis ici.
        self._sync_asset_tooltip()
        # La largeur de contenu du combo change la place prise par la fin de la ligne :
        # l'abscisse commune des deux lignes de réglages doit être recalculée.
        self.cmb_asset.updateGeometry()
        self._apply_filter_columns()

    # ------------------------------------------------------------------ lignes de versions

    def _clear_rows(self) -> None:
        for side in ("left", "right"):
            layout = self._col_layout[side]
            while layout.count():
                item = layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._rows = []

    def _rebuild_rows(self) -> None:
        self._clear_rows()
        if not self._repo.releases:
            self._add_placeholder("left", t("Aucune version récupérée. Bouton Fetch."))
            self._add_placeholder("right", "-")
            self._sync_column_toggles()
            return
        left = self._repo.matching_releases
        right = self._repo.rejected_releases
        if not left:
            self._add_placeholder(
                "left",
                t(
                    "Aucun tag ne passe le filtre : rien n'est comparé à ta version locale. "
                    "Corrige le motif ou vide-le."
                ),
            )
        for release in left:
            self._add_row(release, side="left")
        if not right:
            self._add_placeholder("right", t("Aucun tag rejeté ni obsolète."))
        for release in right:
            self._add_row(release, side="right")
        QTimer.singleShot(0, self._align_rows_text_widths)
        self._sync_column_toggles()

    def _add_placeholder(self, side: str, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("rowMeta")
        label.setWordWrap(True)
        self._col_layout[side].addWidget(label)

    def _add_row(self, release: ReleaseInfo, side: str) -> None:
        row = ReleaseRow(
            release=release,
            kind=self._repo.release_kind(release, side),
            default_asset_name=self._repo.default_asset_name,
            matches_pattern=self._repo.tag_is_allowed(release.tag),
            show_asset_button=self._repo.assets_enabled,
            downloads=self._repo.downloads_for(release.tag),
            parent=self._col_body[side],
        )
        row.validate_requested.connect(self._on_validate_tag)
        row.download_requested.connect(self._on_row_download)
        row.folder_requested.connect(self._on_row_folder)
        row.selected.connect(self._on_row_selected)
        row.nav_requested.connect(lambda delta, source=row: self._on_row_nav(delta, source))
        self._col_layout[side].addWidget(row)
        self._rows.append(row)

    def _align_rows_text_widths(self) -> None:
        """Serre les colonnes de texte au contenu réel, sans effacer l'alignement des boutons."""
        version_cap = token_px("row_w_version")
        meta_cap = token_px("row_w_meta")
        for rows in self.rows_by_side().values():
            if not rows:
                continue
            natural = [row.natural_widths() for row in rows]
            version_width = min(version_cap, max(width for width, _meta in natural) + 8)
            meta_width = min(meta_cap, max(meta for _version, meta in natural) + 8)
            for row in rows:
                row.set_text_widths(version_width, meta_width)

    def _sync_column_toggles(self) -> None:
        """Bascule et détail de chaque colonne : tout tient dans l'infobulle du bouton."""
        left_count = len(self._repo.matching_releases)
        right_count = len(self._repo.rejected_releases)
        hidden = max(0, len(self._repo.releases) - left_count - right_count)
        pattern = self._repo.tag_pattern.strip() or t("(tous les tags)")
        excluded = self._repo.tag_exclude.strip() or t("(aucun)")

        self.btn_col_left.setChecked(not self._repo.column_left_collapsed)
        self.btn_col_right.setChecked(not self._repo.column_right_collapsed)
        # Le QSS ne réagit pas à `:checked` sur un `QToolButton` (sonde : palette inchangée).
        # L'état visible est porté par la propriété dynamique `on`, posée par `set_property()`
        # qui re-poli le bouton : sans elle, bouton actif et bouton inactif se confondent.
        set_property(self.btn_col_left, "on", "1" if not self._repo.column_left_collapsed else "0")
        set_property(self.btn_col_right, "on", "1" if not self._repo.column_right_collapsed else "0")
        self.btn_col_left.setToolTip(
            self._column_toggle_tip(t("gauche"), t("versions retenues"), self._repo.column_left_collapsed)
            + "\n"
            + t(
                "Détail : comparées à ta version locale.\n"
                "Motif retenu : {pattern}\n"
                "Exclus : {excluded}\n"
                "Cap affiché : {cap} versions.\n"
                "{kept} tag(s) retenu(s) sur {total} récupéré(s)."
            ).format(
                pattern=pattern,
                excluded=excluded,
                cap=self._repo.max_versions,
                kept=left_count,
                total=len(self._repo.releases),
            )
        )
        hidden_note = t(" · {n} non affiché(s) au-delà du cap").format(n=hidden) if hidden else ""
        self.btn_col_right.setToolTip(
            self._column_toggle_tip(t("droite"), t("versions rejetées ou obsolètes"), self._repo.column_right_collapsed)
            + "\n"
            + t(
                "Détail : tags refusés par le motif ou l'exclusion, et tags autorisés mais\n"
                "au-delà du cap de {cap} versions retenues à gauche.\n"
                "Cap affiché à droite : {rejected_cap} versions rejetées ou obsolètes.\n"
                "{shown} affiché(s){hidden_note}.\n"
                "Jamais comparés à ta version locale, mais leurs notes et leurs assets restent accessibles, "
                "et tu peux y désigner la version locale."
            ).format(
                cap=self._repo.max_versions,
                rejected_cap=self._repo.max_rejected_versions,
                shown=right_count,
                hidden_note=hidden_note,
            )
        )

    @staticmethod
    def _column_toggle_tip(side: str, title: str, collapsed: bool) -> str:
        return t("Colonne {side} — {title} : {state}.\nClique {action}.").format(
            side=side,
            title=title,
            state=t("masquée") if collapsed else t("affichée"),
            action=t("pour la faire réapparaître") if collapsed else t("pour la masquer"),
        )

    def _on_row_selected(self, release: ReleaseInfo) -> None:
        self.notes_requested.emit(self._repo.id, release)

    def _on_row_nav(self, delta: int, source: ReleaseRow) -> None:
        """Flèches haut/bas : le déplacement saute les lignes d'une colonne repliée."""
        try:
            index = self._rows.index(source)
        except ValueError:
            return
        position = index + delta
        while 0 <= position < len(self._rows):
            row = self._rows[position]
            if row.isVisible():
                row.take_focus()
                row.describe()
                return
            position += delta

    # ------------------------------------------------------------------ état visible

    def _sync_launch(self) -> None:
        has_scripts = self._repo.has_scripts
        self.btn_launch.setEnabled(has_scripts and not self._busy)
        set_role(self.btn_launch, "accent" if has_scripts else "ghost")
        if not has_scripts:
            self.btn_launch.setToolTip(t("Aucun script choisi : bouton 🛠 pour en désigner un"))
            return
        lines: list[str] = []
        for script in self._repo.scripts:
            try:
                lines.append(f"{script.display}  ->  {plan_for(script).cwd}")
            except ScriptError as exc:
                lines.append(t("{script}  ->  refusé : {error}").format(script=script.display, error=exc))
        header = (
            t(
                "Chaque script est lancé depuis son propre dossier, sans l'environnement\n"
                "de l'application (ni son venv) :"
            )
            if IS_WINDOWS
            else t(
                "Chaque script est lancé depuis son propre dossier, sans l'environnement\n"
                "de l'application (ni son venv), dans un terminal ou un journal de data/launches/ :"
            )
        )
        self.btn_launch.setToolTip(header + "\n" + "\n".join(lines))

    def _apply_collapsed(self) -> None:
        """Replié : seule la ligne de tête reste visible, avec tous ses boutons."""
        for widget in self.detail_rows():
            widget.setVisible(not self._repo.collapsed)
        self.toggle.setToolTip(t("Déployer les versions") if self._repo.collapsed else t("Replier les versions"))
        self._apply_asset_visibility()
        # En dernier : c'est lui qui pose la visibilité du panneau selon les deux toggles.
        self._apply_column_collapse()

    def _apply_column_collapse(self) -> None:
        """Les deux toggles masquent leur colonne : la voisine récupère toute la place."""
        left_collapsed = self._repo.column_left_collapsed
        right_collapsed = self._repo.column_right_collapsed
        states = (("left", left_collapsed), ("right", right_collapsed))

        for side, collapsed in states:
            self._col_body[side].setVisible(not collapsed)
            self._col_widget[side].setVisible(not collapsed)
            self._col_widget[side].updateGeometry()
            # La propriété doit être réévaluée par le style : `set_property` fait le polish.
            set_property(self._col_widget[side], "collapsed", "1" if collapsed else "")

        layout = self._columns_box
        for side, collapsed in states:
            index = layout.indexOf(self._col_widget[side])
            if index >= 0:
                layout.setStretch(index, 0 if collapsed else 1)

        # Les deux colonnes masquées : le panneau n'aurait plus rien d'affichable.
        self.versions_panel.setVisible(not self._repo.collapsed and not (left_collapsed and right_collapsed))
        layout.activate()
        self.versions_panel.updateGeometry()
        self.updateGeometry()
        self._sync_column_toggles()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.btn_fetch.setEnabled(not busy)
        self.btn_fetch.setText(t("Fetch…") if busy else t("Fetch"))
        self._sync_launch()

    def set_fetch_tip(self, detail: str) -> None:
        base = t("Interroge GitHub pour ce repo uniquement (5 à 25 dernières versions).")
        self.btn_fetch.setToolTip(f"{base}\n{detail}" if detail else base)

    # ------------------------------------------------------------------ actions

    def set_download_dir(self, folder: str) -> None:
        self._repo.download_dir = folder
        self._save()
        self.refresh()
        self.message.emit(t("Dossier de téléchargement : {folder}").format(folder=folder), Status.UNKNOWN)

    def _on_validate_tag(self, tag: str) -> None:
        self._repo.local_version = tag
        self._repo.local_version_source = "release"
        self._save()
        self.refresh()
        self.message.emit(
            t("{title} : version locale = {tag}").format(title=self._repo.title, tag=tag),
            Status.UP_TO_DATE,
        )

    def _on_manual_version(self) -> None:
        value, accepted = text_input(
            self,
            t("Version locale"),
            t("Version installée localement pour {title} :").format(title=self._repo.title),
            self._repo.local_version,
        )
        if not accepted:
            return
        cleaned = value.strip()
        self._repo.local_version = cleaned
        self._repo.local_version_source = "manual"
        self._save()
        self.refresh()
        target = Status.UP_TO_DATE if cleaned else Status.UNKNOWN
        self.message.emit(
            t("{title} : version locale = {version}").format(title=self._repo.title, version=cleaned or t("(effacée)")),
            target,
        )

    def _on_rename(self) -> None:
        value, accepted = text_input(self, t("Titre du bandeau"), t("Titre affiché :"), self._repo.title)
        if not accepted:
            return
        cleaned = value.strip()
        if not cleaned:
            self.message.emit(t("Titre vide ignoré."), Status.ERROR)
            return
        self._repo.title = cleaned
        self._save()
        self.refresh()

    def _on_row_download(self, release: ReleaseInfo, asset: object) -> None:
        self.download_requested.emit(self._repo.id, release, asset)

    def _on_row_folder(self, folder: str) -> None:
        """Le chemin vient d'un fichier déjà écrit : seule la fenêtre sait l'ouvrir."""
        self.folder_requested.emit(folder)

    def _on_more(self) -> None:
        menu = QMenu(self)
        menu.addAction(t("Renommer le titre"), self._on_rename)
        menu.addAction(t("Définir une version locale manuelle"), self._on_manual_version)
        menu.addSeparator()
        self._add_source_actions(menu)
        menu.addAction(t("Ouvrir la page du repo"), lambda: self.open_url_requested.emit(self._repo.github_url))
        menu.addAction(
            t("Ouvrir le dossier de téléchargement"),
            lambda: self.download_dir_requested.emit(self._repo.id),
        )
        menu.addSeparator()
        remove = menu.addAction(t("Supprimer ce repo"))
        remove.setProperty("role", "danger")
        remove.triggered.connect(lambda: self.remove_requested.emit(self._repo.id))
        menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))

    def _add_source_actions(self, menu: QMenu) -> None:
        """Choix de la liste interrogée : les tags ou les releases GitHub.

        Le choix n'émet aucune requête : il change seulement la source lue au prochain
        « ⟳ Vérifier », et la page qu'ouvre le bouton « 🌐 ».
        """
        source = menu.addMenu(t("Source des versions"))
        tags = source.addAction(t("Tags du dépôt"))
        tags.setCheckable(True)
        tags.setChecked(self._repo.uses_tags())
        tags.setToolTip(
            t(
                "Derniers tags, enrichis par la release du même nom quand elle existe.\n"
                "Choix par défaut : un repo peut taguer sans publier de release."
            )
        )
        tags.triggered.connect(lambda: self._on_source_changed(VERSIONS_SOURCE_TAGS))
        releases = source.addAction(t("Releases GitHub"))
        releases.setCheckable(True)
        releases.setChecked(not self._repo.uses_tags())
        releases.setToolTip(
            t(
                "Seulement les versions publiées en release : dates et notes sont là,\n"
                "mais les tags sans release disparaissent de la liste."
            )
        )
        releases.triggered.connect(lambda: self._on_source_changed(VERSIONS_SOURCE_RELEASES))

    def _on_source_changed(self, source: str) -> None:
        if self._repo.versions_source == source:
            return
        self._repo.versions_source = source
        self.refresh()
        self.message.emit(
            t("Source de {title} : {source}. Lance « ⟳ Vérifier » pour récupérer cette liste.").format(
                title=self._repo.title, source=self._source_word()
            ),
            Status.UNKNOWN,
        )

    def _source_word(self) -> str:
        return t("releases") if self._repo.versions_source == VERSIONS_SOURCE_RELEASES else t("tags")

    # ------------------------------------------------------------------ branchements

    def connect_actions(self) -> None:
        self.toggle.clicked.connect(self._on_toggle)
        self.btn_fetch.clicked.connect(lambda: self.fetch_requested.emit(self._repo.id))
        self.btn_github.clicked.connect(lambda: self.open_url_requested.emit(self._repo.versions_url))
        self.btn_scripts.clicked.connect(lambda: self.scripts_requested.emit(self._repo.id))
        self.btn_more.clicked.connect(self._on_more)
        self.btn_launch.clicked.connect(self._on_launch)
        self.btn_download_dir.clicked.connect(lambda: self.download_dir_requested.emit(self._repo.id))
        self.cmb_versions.currentTextChanged.connect(self._on_max_versions)
        self.cmb_max_rejected.currentTextChanged.connect(self._on_max_rejected_versions)
        self.cmb_asset.currentTextChanged.connect(self._on_default_asset)
        self.edit_pattern.editingFinished.connect(self._on_pattern_edited)
        self.edit_exclude.editingFinished.connect(self._on_tag_exclude_edited)
        self.edit_asset_include.editingFinished.connect(self._on_asset_include_edited)
        self.edit_asset_exclude.editingFinished.connect(self._on_asset_exclude_edited)
        self.chk_assets.toggled.connect(self._on_assets_toggled)
        self.btn_exclude.clicked.connect(self._on_exclude_toggle)
        self.btn_col_left.clicked.connect(lambda: self._on_column_toggle("left"))
        self.btn_col_right.clicked.connect(lambda: self._on_column_toggle("right"))

    def _on_toggle(self) -> None:
        self._repo.collapsed = not self._repo.collapsed
        self._save()
        self.refresh()

    def _on_column_toggle(self, side: str) -> None:
        """Les lignes ne sont pas recréées : la colonne est seulement masquée ou réaffichée."""
        if side == "left":
            self._repo.column_left_collapsed = not self._repo.column_left_collapsed
        else:
            self._repo.column_right_collapsed = not self._repo.column_right_collapsed
        self._save()
        self._apply_column_collapse()
        # La colonne garde ou rend toute la place : les lignes changent de largeur.
        QTimer.singleShot(0, self._align_rows_text_widths)
        if self._repo.column_left_collapsed and self._repo.column_right_collapsed:
            self.message.emit(
                t(
                    "Les deux colonnes de versions sont masquées. "
                    "Clique sur le bouton 'retenues' ou 'rejetées' pour les faire réapparaître."
                ),
                Status.UNKNOWN,
            )

    def _on_max_versions(self, text: str) -> None:
        try:
            value = int(text)
        except ValueError:
            return
        self._repo.max_versions = value
        self._save()
        self.refresh()
        self.message.emit(
            t("{title} : {n} versions comparées à gauche").format(title=self._repo.title, n=value),
            Status.UNKNOWN,
        )

    def _on_max_rejected_versions(self, text: str) -> None:
        try:
            value = int(text)
        except ValueError:
            return
        self._repo.max_rejected_versions = value
        self._save()
        self.refresh()
        self.message.emit(
            t("{title} : {n} versions rejetées à droite").format(title=self._repo.title, n=value),
            Status.UNKNOWN,
        )

    def _on_exclude_toggle(self) -> None:
        self._repo.excluded_check_all = bool(self.btn_exclude.isChecked())
        self._save()
        self.refresh()
        state = t("exclu de") if self._repo.excluded_check_all else t("inclus dans")
        self.message.emit(
            t("{title} : {state} 'Vérifier tous les repos'").format(title=self._repo.title, state=state),
            Status.UNKNOWN,
        )

    def _accepted_rule(self, edit: QLineEdit, label: str) -> str | None:
        """Une règle refusée ne va pas dans une exception : message dans le bandeau, valeur non enregistrée."""
        value = edit.text().strip()
        error = filters.rules_error(value)
        if error:
            self.message.emit(
                t("{title} : {label} refusé · {error}").format(title=self._repo.title, label=label, error=error),
                Status.ERROR,
            )
            return None
        return value

    def _on_pattern_edited(self) -> None:
        value = self._accepted_rule(self.edit_pattern, t("motif retenu"))
        if value is None:
            self._sync_pattern(self.edit_pattern, self._repo.tag_pattern)
            return
        if value == self._repo.tag_pattern.strip():
            return
        self._repo.tag_pattern = value
        self._save()
        self.refresh()
        self.message.emit(
            t("{title} : motif '{pattern}' · {n} tag(s) comparé(s)").format(
                title=self._repo.title,
                pattern=value or t("tous les tags"),
                n=len(self._repo.matching_releases),
            ),
            Status.UNKNOWN,
        )

    def _on_tag_exclude_edited(self) -> None:
        value = self._accepted_rule(self.edit_exclude, t("tags exclus"))
        if value is None:
            self._sync_pattern(self.edit_exclude, self._repo.tag_exclude)
            return
        if value == self._repo.tag_exclude.strip():
            return
        self._repo.tag_exclude = value
        self._save()
        self.refresh()
        self.message.emit(
            t("{title} : exclus '{pattern}' · {n} tag(s) déplacé(s) à droite").format(
                title=self._repo.title,
                pattern=value or t("aucun"),
                n=len(self._repo.other_releases),
            ),
            Status.UNKNOWN,
        )

    def _on_asset_include_edited(self) -> None:
        value = self._accepted_rule(self.edit_asset_include, t("assets inclure"))
        if value is None:
            self._sync_pattern(self.edit_asset_include, self._repo.asset_include)
            return
        if value == self._repo.asset_include.strip():
            return
        self._repo.asset_include = value
        self._apply_asset_rules()

    def _on_asset_exclude_edited(self) -> None:
        value = self._accepted_rule(self.edit_asset_exclude, t("assets exclure"))
        if value is None:
            self._sync_pattern(self.edit_asset_exclude, self._repo.asset_exclude)
            return
        if value == self._repo.asset_exclude.strip():
            return
        self._repo.asset_exclude = value
        self._apply_asset_rules()

    def _on_assets_toggled(self, checked: bool) -> None:
        """Case décochée : les assets déjà en base sont jetés tout de suite."""
        self._repo.assets_enabled = bool(checked)
        self.message.emit(
            t("{title} : assets · recueil {state}").format(
                title=self._repo.title, state=t("activé") if checked else t("désactivé")
            ),
            Status.UNKNOWN,
        )
        self._apply_asset_rules()

    def _apply_asset_rules(self) -> None:
        """Seuls les assets autorisés restent en base : l'écriture `state.json` est le miroir du filtre."""
        kept, dropped = self._repo.apply_asset_filters()
        self._save()
        self.refresh()
        note = "" if self._repo.prune_asset_choice() else t(" · asset par défaut hors liste, à rechoisir")
        self.message.emit(
            t("{title} : {kept} asset(s) conservé(s), {dropped} jeté(s){note}").format(
                title=self._repo.title, kept=kept, dropped=dropped, note=note
            ),
            Status.UNKNOWN,
        )

    def _on_default_asset(self, text: str) -> None:
        if self.cmb_asset.currentIndex() == 0:
            self._repo.default_asset_name = ""
        else:
            self._repo.default_asset_name = text
        self._save()
        self._sync_asset_tooltip()
        self.message.emit(t("Asset par défaut : {name}").format(name=text), Status.UNKNOWN)

    def _on_launch(self) -> None:
        scripts = self._repo.scripts
        if not scripts:
            return
        if len(scripts) == 1:
            self.script_requested.emit(self._repo.id, 0)
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for index, script in enumerate(self._repo.scripts):
            action = menu.addAction(f"{index + 1}. {script.display}")
            action.setData(index)
            try:
                plan = plan_for(script)
            except ScriptError as exc:
                action.setEnabled(False)
                action.setToolTip(t("Refusé : {error}").format(error=exc))
                continue
            action.setToolTip(
                t("Lancé depuis : {cwd}\nCommande : {command}").format(cwd=plan.cwd, command=" ".join(plan.command))
            )
        picked = menu.exec(self.btn_launch.mapToGlobal(self.btn_launch.rect().bottomLeft()))
        if picked is None:
            return
        self.script_requested.emit(self._repo.id, int(picked.data()))

    # ------------------------------------------------------------------ double-clic

    # ------------------------------------------------------------------ ordre par glisser-deposer

    def _handle_drag_mouse(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget) or not isinstance(event, QMouseEvent):
            return False
        if event.type() is QEvent.Type.MouseButtonPress and event.button() is Qt.MouseButton.LeftButton:
            self._drag_candidate = True
            self._drag_origin = event.position()
            return False
        if event.type() is QEvent.Type.MouseButtonRelease and event.button() is Qt.MouseButton.LeftButton:
            self._drag_candidate = False
            return False
        if event.type() is QEvent.Type.MouseMove and self._drag_candidate:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self._drag_candidate = False
                return False
            if (event.position() - self._drag_origin).manhattanLength() >= QApplication.startDragDistance():
                self._drag_candidate = False
                self._start_repo_drag()
                return True
        return False

    def _start_repo_drag(self) -> None:
        drag = QDrag(self)
        drag.setMimeData(repo_order_mime_data(self._repo.id))
        drag.setPixmap(self.grab())
        drag.setHotSpot(self.drag_handle.rect().center())
        set_property(self, "dragging", "1")
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            set_property(self, "dragging", "")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.drag_handle and self._handle_drag_mouse(watched, event):
            return True
        if event.type() is QEvent.Type.MouseButtonDblClick and not self._blocks_toggle(watched, event):
            self._on_toggle()
            return True
        return super().eventFilter(watched, event)

    def _blocks_toggle(self, watched: QObject, event: QEvent) -> bool:
        """Vrai si le double-clic touche un bouton, un champ de saisie ou une ligne de version."""
        if not isinstance(watched, QWidget) or not isinstance(event, QMouseEvent):
            return True
        target = watched.childAt(event.position().toPoint())
        if target is None:
            return False
        while target is not None and target is not self:
            if isinstance(target, ReleaseRow) or isinstance(target, TOGGLE_BLOCKERS):
                return True
            target = target.parentWidget()
        return False
