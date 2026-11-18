"""Ajout d'un repo : saisie de l'adresse, validation via l'API, titre."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.github import BadRepoUrlError, GitHubClient, RepoMeta, parse_repo_url
from app.i18n import t
from app.jobs import JobPool, ValidateJob
from app.models import Repo
from app.widgets.ghost_field import GhostLineEdit

# Exemple d'URL jamais traduit : c'est une adresse, pas un mot de l'interface.
URL_EXAMPLE = "https://github.com/PySide/PySide6"


class AddRepoDialog(QDialog):
    def __init__(
        self,
        pool: JobPool,
        client_factory: Callable[[], GitHubClient],
        existing_ids: set[str],
        default_max_versions: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("addRepoDialog")
        self.setMinimumWidth(520)

        self._pool = pool
        self._client_factory = client_factory
        self._existing_ids = existing_ids
        self._default_max_versions = default_max_versions
        self._meta: RepoMeta | None = None
        self._job: ValidateJob | None = None
        self._title_touched = False
        self._validating = False

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("dlgTitle")
        root.addWidget(self.title_label)

        self.hint = QLabel()
        self.hint.setObjectName("dlgHint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.edit_url = GhostLineEdit()
        self.edit_url.setObjectName("editRepoUrl")
        self.edit_url.setPlaceholderText(URL_EXAMPLE)

        self.btn_validate = QPushButton()
        self.btn_validate.setObjectName("btnValidateRepo")
        theme.set_role(self.btn_validate, "accent")
        url_row.addWidget(self.edit_url, 1)
        url_row.addWidget(self.btn_validate)
        root.addLayout(url_row)

        self.info = QLabel("")
        self.info.setObjectName("dlgHint")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        self.error = QLabel("")
        self.error.setObjectName("dlgError")
        self.error.setWordWrap(True)
        root.addWidget(self.error)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.caption = QLabel()
        self.caption.setObjectName("dlgFieldLabel")
        self.edit_title = QLineEdit()
        self.edit_title.setObjectName("editRepoTitle")
        title_row.addWidget(self.caption)
        title_row.addWidget(self.edit_title, 1)
        root.addLayout(title_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel = QPushButton()
        self.cancel.setObjectName("btnCancel")
        theme.set_role(self.cancel, "ghost")
        self.cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton()
        self.btn_ok.setObjectName("btnOk")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._accept)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.btn_ok)
        root.addLayout(buttons)

        self.retranslate()

        self.edit_url.textChanged.connect(self._on_url_changed)
        self.edit_title.textEdited.connect(self._on_title_touched)
        self.btn_validate.clicked.connect(self._on_validate)

    # ------------------------------------------------------------------ textes

    def retranslate(self) -> None:
        """Réécrit tous les textes du dialogue dans la langue active."""
        self.setWindowTitle(t("Ajouter un repo GitHub"))
        self.title_label.setText(t("Ajouter un repo à monitorer"))
        self.hint.setText(
            t(
                "Formes acceptées : https://github.com/owner/repo, "
                "git@github.com:owner/repo.git, owner/repo. Repo public uniquement."
            )
        )
        self.edit_url.setToolTip(
            t(
                "URL du dépôt public. Formes acceptées :\n"
                "https://github.com/owner/repo, git@github.com:owner/repo.git, owner/repo.\n"
                "Aucun identifiant : l'accès est anonyme, les repos privés sont invisibles."
            )
        )
        self.btn_validate.setText(t("Vérification…") if self._validating else t("Vérifier"))
        self.btn_validate.setToolTip(
            t(
                "Une seule requête anonyme vers api.github.com pour ce repo.\n"
                "Aucune connexion avant ce clic. Remplit le titre proposé et active « Ajouter »."
            )
        )
        self.caption.setText(t("Titre du bandeau"))
        self.edit_title.setToolTip(
            t("Nom affiché sur le bandeau.\nProposé automatiquement après « Vérifier », puis modifiable.")
        )
        self.cancel.setText(t("Annuler"))
        self.cancel.setToolTip(t("Ferme sans rien enregistrer."))
        self.btn_ok.setText(t("Ajouter"))
        self.btn_ok.setToolTip(
            t("Enregistre le repo dans data/state.json.\nGrisé tant que « Vérifier » n'a pas réussi.")
        )

    # ------------------------------------------------------------------ état

    def _reset_validated(self) -> None:
        self._meta = None
        self.btn_ok.setEnabled(False)
        self.info.setText("")

    def _on_url_changed(self, text: str) -> None:
        self._reset_validated()
        self.error.setText("")
        if self._title_touched:
            return
        try:
            owner, name = parse_repo_url(text)
        except BadRepoUrlError:
            self.edit_title.setText("")
            return
        self.edit_title.setText(name)

    def _on_title_touched(self) -> None:
        self._title_touched = True

    # ------------------------------------------------------------------ validation

    def _on_validate(self) -> None:
        self.error.setText("")
        try:
            owner, name = parse_repo_url(self.edit_url.text())
        except BadRepoUrlError as exc:
            self.error.setText(str(exc))
            return
        if Repo.make_id(owner, name) in self._existing_ids:
            self.error.setText(t("Ce repo est déjà dans la liste."))
            return
        self._validating = True
        self.btn_validate.setEnabled(False)
        self.btn_validate.setText(t("Vérification…"))
        self.info.setText(t("Interrogation de l'API GitHub…"))
        self._job = ValidateJob(self._client_factory, owner, name)
        self._job.signals.finished.connect(self._on_validated)
        self._job.signals.failed.connect(self._on_validate_failed)
        self._pool.start(self._job)

    def _on_validated(self, meta: object) -> None:
        self._validating = False
        self.btn_validate.setEnabled(True)
        self.btn_validate.setText(t("Vérifier"))
        self.info.setText("")
        if not isinstance(meta, RepoMeta):
            self.error.setText(t("Réponse inattendue de l'API."))
            return
        # Un setText programmé n'est pas une saisie : sans blocage, textChanged repasse
        # par _on_url_changed -> _reset_validated et efface la validation qui vient de
        # réussir. « Ajouter » restait actif mais _meta était revenu à None.
        self.edit_url.blockSignals(True)
        self.edit_url.setText(meta.html_url)
        self.edit_url.blockSignals(False)
        if not self._title_touched:
            self.edit_title.setText(meta.name)
        description = meta.description or t("(pas de description)")
        self.info.setText(
            t("Repo valide : {description}   ·   {stars} stars").format(description=description, stars=meta.stars)
        )
        # _meta posé en dernier : tout ce qui peut déclencher un signal est soldé.
        self._meta = meta
        self.btn_ok.setEnabled(True)

    def _on_validate_failed(self, message: str) -> None:
        self._validating = False
        self.btn_validate.setEnabled(True)
        self.btn_validate.setText(t("Vérifier"))
        self.info.setText("")
        self.error.setText(message)

    # ------------------------------------------------------------------ sortie

    def _accept(self) -> None:
        if self._meta is None:
            self.error.setText(t("Bouton Vérifier d'abord."))
            return
        self.accept()

    def build_repo(self) -> Repo:
        meta = self._meta
        if meta is None:
            raise RuntimeError("Repo non valide")
        title = self.edit_title.text().strip() or meta.name
        return Repo(
            id=Repo.make_id(meta.owner, meta.name),
            owner=meta.owner,
            name=meta.name,
            url=meta.html_url,
            title=title,
            max_versions=self._default_max_versions,
            max_rejected_versions=self._default_max_versions,
        )
