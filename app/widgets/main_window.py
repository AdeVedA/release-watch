"""Fenêtre principale : barre d'actions, pile de bandeaux, dock notes, barre d'état."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDropEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.about import ICON_PATH, language_icon, window_icon, window_title
from app.github import FetchResult, GitHubClient, safe_asset_name
from app.i18n import LANGUAGE_NAMES, Language, language, set_language, size_units, t
from app.jobs import NO_RATE, DatingBudget, DownloadJob, FetchJob, JobPool, catchup_plan
from app.models import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    LISTING_REQUESTS_PER_REPO,
    MAX_MATCHING_PREFIXES_PER_PASS,
    MAX_NOTES_DOCK_WIDTH,
    MAX_REQUESTS_PER_PASS,
    MIN_NOTES_DOCK_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    Asset,
    ReleaseInfo,
    Repo,
    Status,
    now_iso,
    snap_versions_choice,
)
from app.scripts import ScriptError, launch, plan_for
from app.store import StateError, StateStore
from app.widgets.add_repo_dialog import AddRepoDialog
from app.widgets.elided_label import ElidedLabel
from app.widgets.notes_dock import NotesDock
from app.widgets.repo_banner import RepoBanner, repo_order_source_id
from app.widgets.scripts_dialog import ScriptsDialog
from app.widgets.settings_dialog import SettingsDialog

MAX_HTTP_THREADS = 2
CLEAR_STATUS_GLYPH = "✕"


def with_asset_extension(chosen: str, asset_name: str) -> str:
    """Le nom saisi a perdu son extension ? on recolle toute celle de l'asset (`tool.tar.gz` → `.tar.gz`).

    Un `.zip` sans extension ne s'ouvre plus et un `.tar.gz` raccourci en `.gz` ne se décompresse
    plus : c'est le seul cas où l'on complète ce que l'utilisateur a écrit. Un nom qui porte déjà un
    point est laissé tel quel, il a été tapé exprès.
    """
    head, dot, tail = asset_name.partition(".")
    if not head or not dot or not tail:
        return chosen
    if "." in chosen:
        return chosen
    return f"{chosen}.{tail}"


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication, store: StateStore) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(window_title())
        self.setWindowIcon(window_icon())
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self._app = app
        self._store = store
        self.state = store.load()
        self._pool = JobPool(MAX_HTTP_THREADS)
        self._client_factory = GitHubClient
        self._banners: dict[str, RepoBanner] = {}
        self._fetch_jobs: list[FetchJob] = []
        self._dating: DatingBudget | None = None
        self._pass_shares: dict[str, list[int]] = {}
        self._download_jobs: list[DownloadJob] = []
        # clé du job -> (id du bandeau, tag, nom de l'asset) : le `finished` doit savoir sur quelle
        # ligne allumer le 📂, et une clé composée ne se découpe pas proprement.
        self._download_targets: dict[str, tuple[str, str, str]] = {}
        self._running: set[str] = set()
        self._queue_left = 0
        self._queue_total = 0
        # Manche de rattrapage en cours et bandeaux designes par le controle global : un fetch lance
        # a la main sur un bandeau n'appartient jamais a la liste, donc ne relance rien.
        self._last_rate = NO_RATE
        self._catchup_round = 0
        self._catchup_ids: list[str] = []
        self._pending_notes_width: int | None = None

        self._build_shell()
        self._build_shortcuts()
        self._rebuild_banners()
        # Aucun parcours de re-polis ici : la feuille de l'application est posée avant la
        # première fenêtre (main.py), donc chaque widget créé ensuite est polit contre elle
        # à sa création, et `theme.set_role()` / `set_status()` re-polissent le widget dont
        # la propriété change. Le QSS ne contient aucune règle descendante : un parent ne
        # conditionne jamais le style d'un enfant.
        self._restore_window_geometry()
        self._say(
            t("{n} repo(s) chargé(s) · {path}").format(n=len(self.state.repos), path=self._store.path),
            Status.UNKNOWN,
        )

    # ------------------------------------------------------------------ shell

    def _build_shell(self) -> None:
        toolbar = QToolBar("Actions")
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self.btn_add = self._tool_button("btnAddRepo", t("+ Ajouter un repo"), t("Ajouter un repo GitHub"))
        self.btn_check_all = self._tool_button(
            "btnCheckAll",
            t("⟳ Vérifier les repos"),
            t("Fetch de tous les bandeaux, sauf ceux marqués ⊘ (exclus du contrôle global)"),
        )
        self.btn_check_excluded = self._tool_button(
            "btnCheckExcluded",
            t("⊘ Vérifier les exclus"),
            t(
                "Fetch des seuls bandeaux marqués ⊘.\n"
                "« ⟳ Vérifier les repos » les saute : c'est ici qu'on les rattrape à la main."
            ),
        )

        self.counter = QLabel("")
        self.counter.setObjectName("lblRepoCount")

        self.btn_settings = self._tool_button("btnSettings", t("⚙ Réglages"), t("Réglages globaux"))
        self.btn_language = QToolButton()
        self.btn_language.setObjectName("btnLanguage")
        self.btn_language.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_language.clicked.connect(self._toggle_language)
        self.btn_theme = self._tool_button(
            "btnReloadTheme", t("🎨Thème⟳"), t("Ctrl+Maj+P : relit palette.py et dark.qss")
        )

        # Le role accent se pose avant toute mesure : `QToolBar` se mesure sur les
        # sizeHint() des boutons, et la hauteur du logo est prise sur celle des boutons.
        # Posee trop tard, la barre est mesuree sans les marges du theme puis grandit d'un
        # cran au premier rechargement (Ctrl+Maj+P / bouton Theme).
        theme.set_role(self.btn_add, "accent")
        theme.set_role(self.btn_check_all, "accent")
        theme.set_role(self.btn_check_excluded, "accent")

        # Deux espaceurs de même poids encadrent le logo : il se retrouve centré dans
        # l'espace libre de la barre, sans que la barre ne grandisse. Le logo est construit
        # après les boutons : sa hauteur est calculée à partir de la leur.
        self.gap_left = self._tool_gap()
        self.gap_right = self._tool_gap()
        self.logo = self._build_logo()

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_check_all)
        toolbar.addWidget(self.btn_check_excluded)
        toolbar.addWidget(self.counter)
        toolbar.addWidget(self.gap_left)
        toolbar.addWidget(self.logo)
        toolbar.addWidget(self.gap_right)
        toolbar.addWidget(self.btn_settings)
        toolbar.addWidget(self.btn_language)
        toolbar.addWidget(self.btn_theme)

        # La barre est construite apres la pose de la feuille globale : elle ne recoit donc
        # jamais l'evenement StyleChange, et son `padding` QSS n'est honore qu'au premier
        # rechargement du theme (43 px au lieu de 53 px : la barre grandit sous les doigts).
        # L'evenement doit partir une fois la fenetre visible, voir showEvent().
        self._toolbar = toolbar
        self._toolbar_notice_sent = False
        self._sync_toolbar_logo()

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("centralScroll")
        self.scroll_area.setWidgetResizable(True)
        # Pas de défilement horizontal : les lignes du bandeau se replient, le contenu
        # tient toujours dans la largeur. Sans ce verrou, la barre verticale volait
        # 44px et le contenu rebondissait d'une largeur à l'autre.
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        host = QWidget(self.scroll_area)
        host.setObjectName("bannersHost")
        self._host_layout = QVBoxLayout(host)
        self._host_layout.setContentsMargins(14, 4, 14, 4)
        self._host_layout.setSpacing(6)
        self._host_layout.addStretch(1)
        self._host = host
        self._host.setAcceptDrops(True)
        self._host.installEventFilter(self)
        self._drop_indicator = QWidget(host)
        self._drop_indicator.setObjectName("dragInsertBar")
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._drop_indicator.hide()
        self.scroll_area.setWidget(host)
        self.setCentralWidget(self.scroll_area)

        self.notes = NotesDock(self)
        self.notes.link_accepted.connect(self._confirm_open_url)
        self.notes.link_refused.connect(self._refuse_link)
        self.notes.font_size_changed.connect(self._on_notes_font_size)
        self.notes.apply_font_size(self.state.settings.notes_font_size)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.notes)

        self.bar = QStatusBar()
        self.bar.setObjectName("statusBar")
        self.setStatusBar(self.bar)
        # `ElidedLabel`, et surtout pas `QStatusBar.showMessage()` : l'étiquette temporaire de Qt
        # impose sa largeur à la fenêtre et une erreur longue empêchait de rétrécir la fenêtre.
        self.status_label = ElidedLabel("")
        self.status_label.setObjectName("statusLabel")
        self.bar.addWidget(self.status_label, 1)
        self.btn_clear_status = QToolButton()
        self.btn_clear_status.setObjectName("btnClearStatus")
        self.btn_clear_status.setText(CLEAR_STATUS_GLYPH)
        self.btn_clear_status.setToolTip(t("Effacer le message affiché dans la barre d'état."))
        self.btn_clear_status.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setObjectName("progressAll")
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.bar.addPermanentWidget(self.btn_clear_status)
        self.bar.addPermanentWidget(self.progress)

        self.btn_add.clicked.connect(self._add_repo)
        self.btn_check_all.clicked.connect(self._check_all)
        self.btn_check_excluded.clicked.connect(self._check_excluded)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_theme.clicked.connect(self._reload_theme)
        self.btn_clear_status.clicked.connect(self._clear_status)
        self._sync_language_button()

    def _tool_button(self, name: str, text: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setToolTip(tip)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return button

    def _tool_gap(self) -> QWidget:
        """Espace élastique de la barre d'actions : même poids à gauche et à droite du logo."""
        gap = QWidget()
        gap.setObjectName("toolGap")
        gap.setMinimumWidth(theme.token_px("pad_lg"))
        gap.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        return gap

    def _build_logo(self) -> QLabel:
        logo = QLabel()
        logo.setObjectName("toolLogo")
        logo.setToolTip(window_title())
        logo.setPixmap(self._logo_pixmap())
        return logo

    def _toolbar_button_height(self) -> int:
        buttons = (
            self.btn_add,
            self.btn_check_all,
            self.btn_check_excluded,
            self.btn_settings,
            self.btn_language,
            self.btn_theme,
        )
        return max((button.sizeHint().height() for button in buttons), default=0)

    def _logo_pixmap(self) -> QPixmap:
        """Le logo prend la hauteur des boutons : la toolbar ne grandit pas d'un cran."""
        height = self._toolbar_button_height()
        if height <= 0 or not ICON_PATH.is_file():
            return QPixmap(1, 1)
        source = QPixmap(str(ICON_PATH))
        if source.isNull():
            return QPixmap(1, 1)
        return source.scaled(
            height,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _sync_toolbar_logo(self) -> None:
        """Apres un rechargement de theme, les boutons peuvent changer de hauteur."""
        self.gap_left.setMinimumWidth(theme.token_px("pad_lg"))
        self.gap_right.setMinimumWidth(theme.token_px("pad_lg"))
        self.logo.setPixmap(self._logo_pixmap())

    def _build_shortcuts(self) -> None:
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self._reload_theme)

    # ------------------------------------------------------------------ langue

    def _sync_language_button(self) -> None:
        """Le bouton porte le drapeau de la langue active et annonce celle du clic suivant."""
        current = language()
        other: Language = "en" if current == "fr" else "fr"
        self.btn_language.setIcon(language_icon(current))
        self.btn_language.setToolTip(
            t(
                "Interface en {name}.\nClique pour tout basculer en {other}.\nChoix enregistré dans data/state.json."
            ).format(name=LANGUAGE_NAMES[current], other=LANGUAGE_NAMES[other])
        )

    def _toggle_language(self) -> None:
        """Bascule la langue à chaud, par le même chemin de traduction qu'au démarrage."""
        target: Language = "en" if language() == "fr" else "fr"
        set_language(target)
        self.state.settings.language = target
        self._save()
        self.retranslate()
        self._sync_toolbar_logo()
        self.relayout_release_rows()
        self._say(t("Interface en anglais.") if target == "en" else t("Interface en français."), Status.UNKNOWN)

    def retranslate(self) -> None:
        """Réécrit la fenêtre, le dock notes et chaque bandeau dans la langue active.

        Le message déjà affiché dans la barre d'état n'est pas re-traduit : il raconte un
        événement passé, dans la langue où il a été écrit.
        """
        self.setWindowTitle(window_title())
        self.btn_add.setText(t("+ Ajouter un repo"))
        self.btn_add.setToolTip(t("Ajouter un repo GitHub"))
        self.btn_check_all.setText(t("⟳ Vérifier les repos"))
        self.btn_check_all.setToolTip(t("Fetch de tous les bandeaux, sauf ceux marqués ⊘ (exclus du contrôle global)"))
        self.btn_check_excluded.setText(t("⊘ Vérifier les exclus"))
        self.btn_check_excluded.setToolTip(
            t(
                "Fetch des seuls bandeaux marqués ⊘.\n"
                "« ⟳ Vérifier les repos » les saute : c'est ici qu'on les rattrape à la main."
            )
        )
        self.btn_settings.setText(t("⚙ Réglages"))
        self.btn_settings.setToolTip(t("Réglages globaux"))
        self.btn_theme.setText(t("🎨Thème⟳"))
        self.btn_theme.setToolTip(t("Ctrl+Maj+P : relit palette.py et dark.qss"))
        self.btn_clear_status.setToolTip(t("Effacer le message affiché dans la barre d'état."))
        self.logo.setToolTip(window_title())
        self.counter.setText(t("{n} repo(s)").format(n=len(self.state.repos)))
        self.notes.retranslate()
        for banner in self._banners.values():
            banner.retranslate()
        self._sync_language_button()

    # ------------------------------------------------------------------ bandeaux

    def _rebuild_banners(self) -> None:
        while self._host_layout.count() > 1:
            item = self._host_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._banners.clear()
        for repo in self.state.repos:
            self._add_banner(repo)
        self.counter.setText(t("{n} repo(s)").format(n=len(self.state.repos)))

    def _add_banner(self, repo: Repo) -> RepoBanner:
        banner = RepoBanner(repo, self._save, self._host)
        banner.message.connect(self._say)
        banner.fetch_requested.connect(self._start_fetch)
        banner.notes_requested.connect(self._show_notes)
        banner.download_requested.connect(self._start_download)
        banner.script_requested.connect(self._run_script)
        banner.scripts_requested.connect(self._edit_scripts)
        banner.remove_requested.connect(self._confirm_remove)
        banner.open_url_requested.connect(self._open_url)
        banner.download_dir_requested.connect(self._pick_download_dir)
        banner.folder_requested.connect(self._open_folder)
        position = self._host_layout.count() - 1
        self._host_layout.insertWidget(position, banner)
        self._banners[repo.id] = banner
        return banner

    def relayout_release_rows(self) -> None:
        """Recalcule l'alignement des lignes après une application définitive du thème."""
        for banner in self._banners.values():
            banner.relayout_release_rows()

    def _banner_of(self, repo_id: str) -> RepoBanner | None:
        return self._banners.get(repo_id)

    def _repo_of(self, repo_id: str) -> Repo | None:
        return self.state.repo_by_id(repo_id)

    def _save(self) -> None:
        try:
            self._store.save(self.state)
        except StateError as exc:
            self._say(t("Persistance impossible : {error}").format(error=exc), Status.ERROR)

    # ------------------------------------------------------------------ messages

    def _say(self, text: str, status: Status) -> None:
        """Message permanent dans l'étiquette de la barre : le texte complet tient dans l'infobulle."""
        self.status_label.set_full_text(text)
        self.status_label.setToolTip(text)
        theme.set_status(self.status_label, status)
        self.btn_clear_status.setVisible(bool(text))

    def _clear_status(self) -> None:
        self.status_label.set_full_text("")
        self.status_label.setToolTip("")
        self.btn_clear_status.setVisible(False)

    # ------------------------------------------------------------------ fetch

    def _allocate_pass(self, targets: list[Repo]) -> None:
        """Réserve unique de la passe : listing d'abord, découverte ensuite, dates enfin.

        Le plafond est global (50 requêtes) et non seulement datation : sinon le premier dépôt
        profond consommait tout le quota en datation et les bandeaux suivants n'avaient plus de
        listing. Les parts sont posées avant de lancer les jobs, sinon deux threads se disputent
        la totalité du budget au démarrage de la passe.
        """
        self._dating = DatingBudget(MAX_REQUESTS_PER_PASS)
        self._pass_shares = {}
        plans = {repo.id: repo.dating_plan() for repo in targets}
        left = MAX_REQUESTS_PER_PASS
        for repo in targets:
            listing = min(LISTING_REQUESTS_PER_REPO, max(0, left))
            self._pass_shares[repo.id] = [listing, 0, 0]
            left -= listing

        matching = [repo.id for repo in targets if repo.uses_tags()]
        if matching and left > 0:
            wanted = {
                repo_id: min(MAX_MATCHING_PREFIXES_PER_PASS, max(1, len(plans[repo_id].prefixes)))
                for repo_id in matching
            }
            progressed = True
            while left > 0 and progressed:
                progressed = False
                for repo_id in matching:
                    if left <= 0 or self._pass_shares[repo_id][1] >= wanted[repo_id]:
                        continue
                    self._pass_shares[repo_id][1] += 1
                    left -= 1
                    progressed = True

        # La datation suit la file utile : d'abord les bandeaux qui ont des tags au-dessus de leur
        # derniere ancre datee (les builds llama.cpp posterieurs a la derniere release), puis les
        # orphelins de la fenetre. Entre deux besoins identiques, la part tourne pour qu'un seul
        # bandeau ne mange pas la réserve.
        for above_first in (True, False):
            queue = [
                repo.id for repo in targets if plans[repo.id].queued and (len(plans[repo.id].above) > 0) == above_first
            ]
            left_to_date = {repo_id: plans[repo_id].queued for repo_id in queue}
            while left > 0 and any(count > 0 for count in left_to_date.values()):
                for repo_id in queue:
                    if left <= 0 or left_to_date[repo_id] <= 0:
                        continue
                    self._pass_shares[repo_id][2] += 1
                    left_to_date[repo_id] -= 1
                    left -= 1
                    if left <= 0:
                        break

        # Un repo `tags` fraichement peuple n'a parfois aucun plan avant le fetch : la decouverte
        # par matching-refs ne peut alors etre datee que si la reserve lui laisse une part.
        fallback = [repo_id for repo_id in matching if plans[repo_id].queued == 0 and self._pass_shares[repo_id][1] > 0]
        if fallback and left > 0:
            by_id = {repo.id: repo for repo in targets}
            limits = {repo_id: by_id[repo_id].storage_cap() for repo_id in fallback}
            progressed = True
            while left > 0 and progressed:
                progressed = False
                for repo_id in fallback:
                    if left <= 0 or self._pass_shares[repo_id][2] >= limits[repo_id]:
                        continue
                    self._pass_shares[repo_id][2] += 1
                    left -= 1
                    progressed = True

    def _fetch_shares(self, repo_id: str) -> list[int]:
        return self._pass_shares.pop(
            repo_id, [LISTING_REQUESTS_PER_REPO, MAX_MATCHING_PREFIXES_PER_PASS, MAX_REQUESTS_PER_PASS]
        )

    def _update_fetch_tip(self, repo: Repo, plan: object, remaining: int) -> None:
        banner = self._banner_of(repo.id)
        if banner is None:
            return
        parts = [
            t("{n} tag(s) recensé(s)").format(n=int(getattr(plan, "known", 0))),
            t("{n} date(s) payée(s)").format(n=int(getattr(plan, "dated", 0))),
            t("{n} en attente dans la fenêtre").format(n=int(getattr(plan, "queued", 0))),
        ]
        outside = int(getattr(plan, "outside", 0))
        if outside:
            parts.append(t("{n} hors fenêtre (non daté(s))").format(n=outside))
        if remaining != NO_RATE:
            parts.append(t("quota restant {n}").format(n=remaining))
        banner.set_fetch_tip(" · ".join(parts))

    def _start_fetch(self, repo_id: str) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        if repo_id in self._running:
            self._say(t("{title} : fetch déjà en cours").format(title=repo.title), Status.UNKNOWN)
            return
        # Le motif de tag ne filtre qu'après récupération : on demande le maximum que les deux
        # colonnes peuvent réclamer (`storage_cap` côté modèle), jamais le réglage affiché. Baisser
        # un réglage ne doit pas faire perdre de lignes, et les remonter ne doit pas exiger un re-fetch.
        wanted = repo.storage_cap()
        plan = repo.dating_plan()
        listing, matching, dating = self._fetch_shares(repo_id)
        job = FetchJob(
            self._client_factory,
            repo.id,
            repo.owner,
            repo.name,
            wanted,
            source=repo.versions_source,
            etags={"tags": repo.etag_tags, "releases": repo.etag_releases},
            previous=repo.releases,
            budget=self._dating,
            listing_share=listing,
            match_share=matching,
            dating_share=dating,
            tag_pattern=repo.tag_pattern,
            tag_exclude=repo.tag_exclude,
            plan=plan,
            tag_index=repo.tag_index,
            tag_dates=repo.tag_dates,
            tag_prefixes=repo.tags_prefixes,
            dating_window=repo.storage_cap(),
        )
        job.signals.finished.connect(self._on_fetched)
        job.signals.failed.connect(self._on_fetch_failed)
        self._fetch_jobs.append(job)
        self._running.add(repo_id)
        banner = self._banner_of(repo_id)
        if banner is not None:
            banner.set_busy(True)
        self._pool.start(job)

    def _on_fetched(self, repo_id: str, payload: object, remaining: int) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        if remaining != NO_RATE:
            # Le quota restant vient d'une reponse GitHub : c'est lui qui decide si un rattrapage
            # des dates vaut encore le coup d'etre lance.
            self._last_rate = remaining
        result = payload if isinstance(payload, FetchResult) else FetchResult(releases=[])
        candidates = [item for item in result.releases if isinstance(item, ReleaseInfo)]
        # Le cap de stockage ne doit pas ecarter ce que le motif retient : la selection des
        # lignes gardees connait le motif, pas la recuperation reseau.
        repo.remember_tags(result.tag_index)
        repo.remember_dates(result.dates)
        repo.remember_prefixes(result.prefixes_done)
        repo.releases = repo.pick_candidates(candidates, cap=repo.storage_cap())
        repo.etag_tags = str(result.etags.get("tags", repo.etag_tags))
        repo.etag_releases = str(result.etags.get("releases", repo.etag_releases))
        kept_assets, dropped_assets = repo.apply_asset_filters()
        repo.last_fetch_ok = True
        repo.last_fetch_error = ""
        repo.last_fetch_at = now_iso()
        self._forget_job(repo_id)
        self._save()
        banner = self._banner_of(repo_id)
        if banner is not None:
            banner.set_busy(False)
            banner.refresh()
        plan = repo.dating_plan()
        self._update_fetch_tip(repo, plan, remaining)
        tail = t(" · quota restant {n}").format(n=remaining) if remaining != NO_RATE else ""
        if result.not_modified:
            tail += t(" · rien de changé depuis le dernier fetch")
        if result.dated:
            tail += t(" · {n} tag(s) daté(s)").format(n=result.dated)
        if plan.queued:
            tail += t(" · {n} en attente dans la fenêtre").format(n=plan.queued)
        if plan.outside:
            tail += t(" · {n} hors fenêtre (non daté(s))").format(n=plan.outside)
        self._say(
            t(
                "{title} : {n} version(s) récupérée(s) · {kept} asset(s) conservé(s), {dropped} jeté(s) par le filtre{tail}"
            ).format(
                title=repo.title,
                n=len(repo.releases),
                kept=kept_assets,
                dropped=dropped_assets,
                tail=tail,
            ),
            Status.UP_TO_DATE,
        )

    def _on_fetch_failed(self, repo_id: str, message: str) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        repo.last_fetch_ok = False
        repo.last_fetch_error = message
        repo.last_fetch_at = now_iso()
        self._forget_job(repo_id)
        self._save()
        banner = self._banner_of(repo_id)
        if banner is not None:
            banner.set_busy(False)
            banner.refresh()
        self._say(f"{repo.title} : {message}", Status.ERROR)

    def _forget_job(self, repo_id: str) -> None:
        self._running.discard(repo_id)
        self._fetch_jobs = [job for job in self._fetch_jobs if job.repo_id != repo_id]
        if not self._running:
            # Passe terminee : la prochaine repartira avec une reserve pleine.
            self._dating = None
            self._pass_shares.clear()
            # Le rattrapage est differe : lance ici, il demarrerait un second fetch du meme bandeau
            # avant la fin du signal en cours, et `banner.set_busy(False)` effacerait l'indicateur
            # d'attente juste apres sa repose.
            QTimer.singleShot(0, self._chase_undated_dates)
        if self._queue_left > 0:
            self._queue_left -= 1
            if self._queue_left <= 0:
                self.progress.setVisible(False)
            else:
                total = max(1, self._queue_total)
                self.progress.setValue(int(100 * (total - self._queue_left) / total))

    def _check_targets(self, only_excluded: bool = False) -> list[Repo]:
        """Bandeaux de la passe : exclus (⊘) ou non selon le passe, et jamais déjà en cours."""
        return [
            repo
            for repo in self.state.repos
            if repo.excluded_check_all is only_excluded and repo.id not in self._running
        ]

    def _run_pass(self, targets: list[Repo], notice: str) -> None:
        """Une passe : reserve unique, progression, puis un fetch par bandeau cible."""
        self._queue_left = len(targets)
        self._queue_total = len(targets)
        self._allocate_pass(targets)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._say(notice, Status.UNKNOWN)
        for repo in targets:
            self._start_fetch(repo.id)

    def _check_all(self) -> None:
        """Le contrôle global ignore les bandeaux marqués ⊘ ; leur bouton Fetch reste actif."""
        excluded = sum(1 for repo in self.state.repos if repo.excluded_check_all)
        targets = self._check_targets()
        if not targets:
            reason = t("{n} repo(s) exclu(s)").format(n=excluded) if excluded else t("liste vide ou déjà en cours")
            self._say(t("Rien à vérifier ({reason})").format(reason=reason), Status.UNKNOWN)
            return
        # La passe est lancée avec les cibles mémorisées : le rattrapage des dates ne suivra que
        # ces bandeaux-là, jamais un fetch lancé à la main pendant le contrôle.
        self._catchup_round = 0
        self._catchup_ids = [repo.id for repo in targets]
        tail = t(" · {n} exclu(s)").format(n=excluded) if excluded else ""
        self._run_pass(targets, t("Fetch de {n} repo(s){tail}…").format(n=len(targets), tail=tail))

    def _check_excluded(self) -> None:
        """Passe réservée aux bandeaux marqués ⊘ : mêmes règles de passe, cible inversée.

        Le bouton « ⟳ Vérifier les repos » les saute volontairement ; sans cette passe, un repo
        exclu ne pourrait plus être rattrapé qu'un bandeau par un bandeau.
        """
        targets = self._check_targets(only_excluded=True)
        if not targets:
            self._say(t("Aucun repo exclu du contrôle global"), Status.UNKNOWN)
            return
        self._catchup_round = 0
        self._catchup_ids = [repo.id for repo in targets]
        self._run_pass(targets, t("Fetch des {n} repo(s) exclu(s)…").format(n=len(targets)))

    def _chase_undated_dates(self) -> None:
        """Rattrapage automatique des dates qu'une passe globale n'a pas pu payer.

        Le plan de datation se calcule AVANT le fetch, sur les caches locaux : un bandeau
        fraichement peuple n'a encore aucun tag recense et recoit donc une part de datation nulle,
        alors meme que la liste, elle, rapporte des tags pendant la passe. Ces tags restent sans
        date jusqu'au clic suivant. Cette manche relance les seuls bandeaux qui ont encore des tags
        en attente, avec une reserve neuve, et s'arrete d'elle-meme quand une manche ne date rien.
        """
        if self._running or not self._catchup_ids:
            return
        chosen = set(self._catchup_ids)
        repos = [repo for repo in self.state.repos if repo.id in chosen]
        if not repos:
            self._catchup_ids = []
            return
        needs = [(repo.id, repo.dating_plan().queued) for repo in repos]
        round_index = self._catchup_round
        self._catchup_round = round_index + 1
        proceed, targets = catchup_plan(needs, round_index, self._last_rate)
        if not proceed:
            self._catchup_ids = []
            return
        queued_by_id = dict(needs)
        wanted = [repo for repo in repos if repo.id in set(targets)]
        waiting = sum(queued_by_id[repo.id] for repo in wanted)
        self._run_pass(
            wanted,
            t("Rattrapage des dates : {n} repo(s), {m} tag(s) en attente…").format(n=len(wanted), m=waiting),
        )

    # ------------------------------------------------------------------ notes

    def _show_notes(self, repo_id: str, release: object) -> None:
        repo = self._repo_of(repo_id)
        if repo is None or not isinstance(release, ReleaseInfo):
            return
        self.notes.show_release(repo.title, release)
        self.notes.setVisible(True)

    # ------------------------------------------------------------------ téléchargements

    def _ask_download_target(self, repo: Repo, asset: Asset) -> tuple[Path, str] | None:
        """Dialogue « Enregistrer sous » : le nom de l'asset est pré-rempli et éditable.

        `getExistingDirectory` ne montrait que des dossiers : rien de ce que contient le dossier
        exploré, et aucun moyen de renommer. Le filtre « Tous les fichiers » laisse apparaître les
        fichiers, et le champ du bas de l'explorateur porte le nom pré-rempli de l'asset.
        """
        start = repo.download_dir or self.state.settings.download_dir
        wanted = safe_asset_name(asset.name, fallback="asset")
        suggested = str(Path(start) / wanted) if start else wanted
        chosen, _filtre = QFileDialog.getSaveFileName(
            self, t("Enregistrer l'asset sous"), suggested, t("Tous les fichiers (*)")
        )
        if not chosen:
            return None
        target = Path(chosen)
        return target.parent, with_asset_extension(target.name, asset.name)

    def _ask_download_dir(self, repo: Repo) -> str:
        """Le réglage « dossier du bandeau » reste un choix de dossier, pas de fichier."""
        start = repo.download_dir or self.state.settings.download_dir
        return QFileDialog.getExistingDirectory(self, t("Dossier de téléchargement"), start)

    def _pick_download_dir(self, repo_id: str) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        folder = self._ask_download_dir(repo)
        if folder:
            banner = self._banner_of(repo_id)
            if banner is not None:
                banner.set_download_dir(folder)

    def _start_download(self, repo_id: str, release: object, asset: object) -> None:
        repo = self._repo_of(repo_id)
        if repo is None or not isinstance(release, ReleaseInfo) or not isinstance(asset, Asset):
            return
        target = self._ask_download_target(repo, asset)
        if target is None:
            self._say(t("Téléchargement annulé"), Status.UNKNOWN)
            return
        folder, filename = target
        repo.download_dir = str(folder)
        self._save()
        # La clé porte la version : deux versions d'un même repo portent souvent le même asset, et
        # le `finished` doit savoir sur quelle ligne allumer le 📂.
        key = f"{repo.id}|{release.tag}|{asset.name}"
        self._download_targets[key] = (repo.id, release.tag, asset.name)
        job = DownloadJob(self._client_factory, key, asset, folder, filename)
        job.signals.progress.connect(self._on_download_progress)
        job.signals.finished.connect(self._on_download_finished)
        job.signals.failed.connect(self._on_download_failed)
        self._download_jobs.append(job)
        self._pool.start(job)
        self._say(t("Téléchargement : {name} → {folder}").format(name=filename, folder=folder), Status.UNKNOWN)

    def _on_download_progress(self, key: str, done: int, total: int) -> None:
        name = key.rsplit("|", 1)[-1]
        unit = size_units()[0]
        if total > 0:
            percent = int(100 * done / total)
            self._say(
                t("{name} : {percent}% ({done} {unit} / {total} {unit})").format(
                    name=name, percent=percent, done=done // 1024, total=total // 1024, unit=unit
                ),
                Status.UNKNOWN,
            )
        else:
            self._say(
                t("{name} : {done} {unit} reçus").format(name=name, done=done // 1024, unit=unit),
                Status.UNKNOWN,
            )

    def _on_download_finished(self, key: str, path: str) -> None:
        self._download_jobs = [job for job in self._download_jobs if job.key != key]
        target = self._download_targets.pop(key, None)
        if target is not None:
            repo_id, tag, asset_name = target
            repo = self._repo_of(repo_id)
            if repo is not None:
                # Le chemin est garde sur le bandeau : c'est lui qui allume le 📂 de la ligne, et un
                # fetch suivant ne l'efface pas (les assets, eux, sont recrees depuis GitHub).
                repo.remember_download(tag, asset_name, path)
                self._save()
                banner = self._banner_of(repo_id)
                if banner is not None:
                    banner.refresh()
        self._say(t("Téléchargé : {path}").format(path=path), Status.UP_TO_DATE)

    def _on_download_failed(self, key: str, message: str) -> None:
        self._download_jobs = [job for job in self._download_jobs if job.key != key]
        self._download_targets.pop(key, None)
        self._say(t("Échec téléchargement : {error}").format(error=message), Status.ERROR)

    def _open_folder(self, folder: str) -> None:
        """Ouvre le dossier d'un asset déjà écrit. Jamais par `_open_url()` : un chemin local n'est
        pas un lien HTTPS, et un chemin qui n'existe plus doit être tracé comme un refus.
        """
        target = Path(folder) if folder else None
        if target is None or not target.is_dir():
            self._say(t("Dossier introuvable : {folder}").format(folder=folder or t("(vide)")), Status.ERROR)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            self._say(t("Impossible d'ouvrir le dossier : {folder}").format(folder=folder), Status.ERROR)

    # ------------------------------------------------------------------ scripts

    def _run_script(self, repo_id: str, index: int) -> None:
        repo = self._repo_of(repo_id)
        if repo is None or index >= len(repo.scripts):
            return
        spec = repo.scripts[index]
        try:
            plan = plan_for(spec)
            result = launch(spec)
        except ScriptError as exc:
            self._say(str(exc), Status.ERROR)
            return
        if result.console:
            self._say(t("Console lancée : {summary}").format(summary=plan.summary), Status.UP_TO_DATE)
        else:
            self._say(t("Script lancé sans fenêtre : sortie dans {log}").format(log=result.log), Status.UP_TO_DATE)

    def _edit_scripts(self, repo_id: str) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        dialog = ScriptsDialog(repo, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        repo.scripts = dialog.specs_result
        self._save()
        banner = self._banner_of(repo_id)
        if banner is not None:
            banner.refresh()
        self._say(t("{title} : {n} script(s)").format(title=repo.title, n=len(repo.scripts)), Status.UP_TO_DATE)

    # ------------------------------------------------------------------ ajout / ordre / suppression

    def _add_repo(self) -> None:
        existing = {repo.id for repo in self.state.repos}
        dialog = AddRepoDialog(
            self._pool,
            self._client_factory,
            existing,
            snap_versions_choice(self.state.settings.max_versions),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        repo = dialog.build_repo()
        self.state.repos.append(repo)
        self._save()
        self._add_banner(repo)
        self.counter.setText(t("{n} repo(s)").format(n=len(self.state.repos)))
        self._say(
            t("Ajouté : {title}. Bouton Fetch pour récupérer les versions.").format(title=repo.title),
            Status.UP_TO_DATE,
        )

    def _visible_banners(self) -> list[RepoBanner]:
        banners: list[RepoBanner] = []
        for repo in self.state.repos:
            banner = self._banners.get(repo.id)
            if banner is not None and not banner.isHidden():
                banners.append(banner)
        return banners

    def _drop_y_for_event(self, event: QDropEvent) -> int:
        # La feuille de style PySide6 annonce des événements de drag plus modernes,
        # mais `QDragEnterEvent` ne porte pas `globalPosition()` ici. Comme l'événement
        # est reçu par `bannersHost`, sa position locale est déjà la bonne.
        return event.position().toPoint().y()

    def _insertion_index_for_y(self, y: int) -> int:
        """Point d'insertion logique : avant le premier bandeau dont le centre est sous y."""
        banners = self._visible_banners()
        for index, banner in enumerate(banners):
            if y < banner.geometry().center().y():
                return index
        return len(self.state.repos)

    def _final_index_for_insertion(self, source_id: str, insertion_index: int) -> int:
        source_index = self.state.index_of(source_id)
        if source_index < 0:
            return source_index
        final_index = insertion_index
        if source_index < final_index:
            final_index -= 1
        return max(0, min(final_index, len(self.state.repos) - 1))

    def _show_drop_indicator(self, insertion_index: int) -> None:
        banners = self._visible_banners()
        if not banners:
            self._hide_drop_indicator()
            return
        indicator_h = theme.token_px("pad_sm")
        side = theme.token_px("pad_banner_h")
        if insertion_index <= 0:
            y = banners[0].geometry().top() - indicator_h
        elif insertion_index >= len(banners):
            y = banners[-1].geometry().bottom() + 1 + indicator_h // 2
        else:
            previous = banners[insertion_index - 1].geometry()
            following = banners[insertion_index].geometry()
            y = (previous.bottom() + 1 + following.top()) // 2 - indicator_h // 2
        y = max(0, min(y, self._host.height() - indicator_h))
        self._drop_indicator.setGeometry(side, y, max(0, self._host.width() - 2 * side), indicator_h)
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _hide_drop_indicator(self) -> None:
        self._drop_indicator.hide()

    def _reorder_repo(self, repo_id: str, target_index: int) -> None:
        index = self.state.index_of(repo_id)
        banner = self._banners.get(repo_id)
        if index < 0 or banner is None:
            return
        target_index = max(0, min(target_index, len(self.state.repos) - 1))
        if index == target_index:
            return
        repo = self.state.repos.pop(index)
        self.state.repos.insert(target_index, repo)
        self._host_layout.removeWidget(banner)
        self._host_layout.insertWidget(target_index, banner)
        banner.updateGeometry()
        self._save()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._host:
            if event.type() is QEvent.Type.DragLeave:
                self._hide_drop_indicator()
                return True
            if isinstance(event, QDropEvent):
                source_id = repo_order_source_id(event.mimeData())
                if source_id is not None:
                    if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                        self._show_drop_indicator(self._insertion_index_for_y(self._drop_y_for_event(event)))
                        event.acceptProposedAction()
                        return True
                    if event.type() is QEvent.Type.Drop:
                        insertion_index = self._insertion_index_for_y(self._drop_y_for_event(event))
                        self._reorder_repo(source_id, self._final_index_for_insertion(source_id, insertion_index))
                        self._hide_drop_indicator()
                        event.setDropAction(Qt.DropAction.MoveAction)
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def _confirm_remove(self, repo_id: str) -> None:
        repo = self._repo_of(repo_id)
        if repo is None:
            return
        # Boutons posés à la main : `QMessageBox.question` laisse Yes/No en anglais quelle
        # que soit la langue de l'interface (aucun catalogue de traduction Qt n'est chargé).
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("Supprimer le bandeau"))
        box.setText(
            t(
                "Retirer {title} de la liste ?\n"
                "Les versions mémorisées et les scripts liés seront perdus (aucun fichier supprimé)."
            ).format(title=repo.title)
        )
        keep = box.addButton(t("Conserver"), QMessageBox.ButtonRole.RejectRole)
        drop = box.addButton(t("Supprimer"), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep)
        box.exec()
        if box.clickedButton() is not drop:
            return
        self.state.repos.remove(repo)
        self._save()
        self._rebuild_banners()
        self._say(t("Supprimé : {title}").format(title=repo.title), Status.UNKNOWN)

    def _confirm_open_url(self, url: str) -> None:
        """Un lien des notes est du texte d'auteur : on demande confirmation avant d'ouvrir le navigateur."""
        parsed = QUrl(url)
        if parsed.scheme().lower() != "https":
            self._refuse_link(url)
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("Ouvrir ce lien ?"))
        box.setText(
            t(
                "Le lien cliqué provient de la description écrite par l'auteur du repo.\n"
                "Rien n'a encore été ouvert.\n\n"
                "{url}"
            ).format(url=url)
        )
        refuse = box.addButton(t("Annuler"), QMessageBox.ButtonRole.RejectRole)
        accept = box.addButton(t("Ouvrir le lien"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(refuse)
        box.exec()
        if box.clickedButton() is not accept:
            self._say(t("Ouverture du lien annulée"), Status.UNKNOWN)
            return
        self._open_url(url)

    def _open_url(self, url: str) -> None:
        parsed = QUrl(url)
        if parsed.scheme().lower() != "https":
            self._refuse_link(url)
            return
        if not QDesktopServices.openUrl(parsed):
            self._say(t("Impossible d'ouvrir : {url}").format(url=url), Status.ERROR)

    def _refuse_link(self, url: str) -> None:
        self._say(t("Lien non HTTPS refusé, rien n'a été ouvert : {url}").format(url=url), Status.ERROR)

    def _on_notes_font_size(self, size: int) -> None:
        self.state.settings.notes_font_size = size
        self._save()
        self._say(t("Panneau de description : police {size}px").format(size=size), Status.UNKNOWN)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.state.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.state.settings = dialog.result_settings
        self._save()
        self._say(
            t("Réglages : {n} versions · dl {folder}").format(
                n=self.state.settings.max_versions,
                folder=self.state.settings.download_dir or t("(à chaque fois)"),
            ),
            Status.UP_TO_DATE,
        )

    # ------------------------------------------------------------------ thème

    def _reload_theme(self) -> None:
        try:
            theme.reload_theme(self._app, self._store.folder)
            theme.repolish_tree(self)
            # Les boutons peuvent changer de hauteur : le logo et les espaceurs suivent.
            self._sync_toolbar_logo()
            self.relayout_release_rows()
        except theme.ThemeTokenError as exc:
            self._say(t("Thème non rechargé : {error}").format(error=exc), Status.ERROR)
            return
        self._say(t("Thème rechargé : app/palette.py + resources/dark.qss"), Status.UP_TO_DATE)

    # ------------------------------------------------------------------ géométrie persistée

    def _restore_window_geometry(self) -> None:
        settings = self.state.settings
        screens = [screen.availableGeometry() for screen in QApplication.screens()]
        width = max(MIN_WINDOW_WIDTH, settings.window_width or DEFAULT_WINDOW_WIDTH)
        height = max(MIN_WINDOW_HEIGHT, settings.window_height or DEFAULT_WINDOW_HEIGHT)
        if screens:
            width = min(width, max(screen.width() for screen in screens))
            height = min(height, max(screen.height() for screen in screens))

        if settings.window_x is not None and settings.window_y is not None:
            x = int(settings.window_x)
            y = int(settings.window_y)
            if self._position_visible(x, y, screens):
                self.setGeometry(x, y, width, height)
            else:
                self._center_window(width, height)
        else:
            self.resize(width, height)
        self._restore_notes_width()

    def _position_visible(self, x: int, y: int, screens: list[QRect]) -> bool:
        """La position est gardée seulement si le bandeau de titre reste sur un écran."""
        for screen in screens:
            if screen.left() <= x <= screen.right() - 64 and screen.top() <= y <= screen.bottom() - 32:
                return True
        return False

    def _center_window(self, width: int, height: int) -> None:
        primary = QApplication.primaryScreen()
        screen = primary.availableGeometry() if primary is not None else QRect(0, 0, width, height)
        width = min(width, max(MIN_WINDOW_WIDTH, screen.width()))
        height = min(height, max(MIN_WINDOW_HEIGHT, screen.height()))
        x = screen.x() + max(0, (screen.width() - width) // 2)
        y = screen.y() + max(0, (screen.height() - height) // 2)
        self.setGeometry(x, y, width, height)

    def _restore_notes_width(self) -> None:
        notes_min, notes_max = self._notes_width_bounds()
        desired = max(notes_min, min(notes_max, self.state.settings.notes_dock_width))
        self._pending_notes_width = desired
        self.notes.setMinimumWidth(notes_min)
        self.notes.setMaximumWidth(notes_max)
        self._apply_notes_width(desired)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """La largeur du dock ne se pose efficacement qu'une fois la fenêtre visible."""
        super().showEvent(event)
        if not self._toolbar_notice_sent:
            # Le `padding` QSS de la barre d'actions n'est compte par `QToolBarLayout` que
            # si la barre recoit l'evenement pendant une passe de layout : envoye a la
            # construction, le resultat est ecrase par la passe d'affichage suivante.
            self._toolbar_notice_sent = True
            theme.notify_style_change(self._toolbar)
            self._sync_toolbar_logo()
        # Première passe de layout : les lignes de version ne sont correctes qu'après
        # la feuille de style et la géométrie réelle de la fenêtre.
        QTimer.singleShot(0, self.relayout_release_rows)
        if self._pending_notes_width is not None:
            desired = self._pending_notes_width
            self._pending_notes_width = None
            QTimer.singleShot(0, lambda: self._apply_notes_width(desired))

    def _apply_notes_width(self, desired: int) -> None:
        notes_min, notes_max = self._notes_width_bounds()
        width = max(notes_min, min(notes_max, desired))
        self.notes.setMinimumWidth(width)
        self.notes.setMaximumWidth(width)
        self.resizeDocks([self.notes], [width], Qt.Orientation.Horizontal)

        def unlock() -> None:
            self.notes.setMinimumWidth(notes_min)
            self.notes.setMaximumWidth(notes_max)
            self.resizeDocks([self.notes], [width], Qt.Orientation.Horizontal)

        QTimer.singleShot(0, unlock)
        QTimer.singleShot(80, unlock)

    def _capture_window_geometry(self) -> None:
        geometry = self.geometry()
        notes_min, notes_max = self._notes_width_bounds()
        settings = self.state.settings
        settings.window_width = max(MIN_WINDOW_WIDTH, geometry.width())
        settings.window_height = max(MIN_WINDOW_HEIGHT, geometry.height())
        settings.window_x = geometry.x()
        settings.window_y = geometry.y()
        settings.notes_dock_width = max(notes_min, min(notes_max, self.notes.width()))

    def _notes_width_bounds(self) -> tuple[int, int]:
        try:
            return theme.token_px("w_dock_notes_min"), theme.token_px("w_dock_notes_max")
        except theme.ThemeTokenError:
            return MIN_NOTES_DOCK_WIDTH, MAX_NOTES_DOCK_WIDTH

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._capture_window_geometry()
        self._save()
        self._pool.wait_for_done(3000)
        super().closeEvent(event)
