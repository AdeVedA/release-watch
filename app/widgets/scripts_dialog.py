"""Gestion des scripts liés à un repo : chemin, dossier de travail, étiquette."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.i18n import t
from app.models import Repo, ScriptSpec
from app.scripts import IS_WINDOWS, ScriptError, plan_for, script_suffixes
from app.widgets.ghost_field import GhostLineEdit


def file_filter() -> str:
    """Filtre du sélecteur de fichier. Le mot « Scripts » est le seul traduisible."""
    return t("Scripts ({globs})").format(globs=" ".join(f"*{suffix}" for suffix in script_suffixes()))


class ScriptRow(QWidget):
    def __init__(self, dialog: ScriptsDialog, spec: ScriptSpec | None = None) -> None:
        super().__init__(dialog)
        self.setObjectName("scriptRow")
        self._dialog = dialog

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.edit_label = GhostLineEdit(spec.display if spec else "")
        self.edit_label.setObjectName("editScriptLabel")

        self.edit_path = GhostLineEdit(spec.path if spec else "")
        self.edit_path.setObjectName("editScriptPath")

        self.btn_path = QToolButton()
        self.btn_path.setText("…")
        self.btn_path.setObjectName("btnBrowseScript")

        self.edit_cwd = GhostLineEdit(spec.cwd if spec else "")
        self.edit_cwd.setObjectName("editScriptCwd")

        self.btn_cwd = QToolButton()
        self.btn_cwd.setText("…")
        self.btn_cwd.setObjectName("btnBrowseCwd")

        self.btn_remove = QToolButton()
        self.btn_remove.setText("✕")
        self.btn_remove.setObjectName("btnRemoveScript")

        layout.addWidget(self.edit_label, 2)
        layout.addWidget(self.edit_path, 4)
        layout.addWidget(self.btn_path)
        layout.addWidget(self.edit_cwd, 3)
        layout.addWidget(self.btn_cwd)
        layout.addWidget(self.btn_remove)

        self.retranslate()

        self.btn_path.clicked.connect(self._browse_path)
        self.btn_cwd.clicked.connect(self._browse_cwd)
        self.btn_remove.clicked.connect(lambda: self._dialog.remove_row(self))

    def retranslate(self) -> None:
        """Réécrit les étiquettes, les valeurs par défaut et les infobulles de la ligne."""
        self.edit_label.setPlaceholderText(t("étiquette du script"))
        self.edit_label.setToolTip(
            t("Nom affiché dans le menu du bouton « Script ».\nVide : le nom du fichier est utilisé.")
        )
        self.edit_path.setPlaceholderText(
            t("chemin du script .bat / .cmd / .ps1") if IS_WINDOWS else t("chemin du script .sh / .bash / .zsh")
        )
        self.edit_path.setToolTip(
            (
                t(
                    "Script lancé dans une console Windows séparée.\n"
                    "Il se lance depuis SON propre dossier, comme un double-clic dans l'explorateur."
                )
                if IS_WINDOWS
                else t(
                    "Script lancé dans un terminal séparé, fenêtre maintenue ouverte.\n"
                    "Sans terminal ni session graphique, la sortie écrit un journal dans data/launches/.\n"
                    "Il se lance depuis SON propre dossier, comme un double-clic dans le gestionnaire de fichiers."
                )
            )
            + "\n"
            + t(
                "L'environnement de l'application n'est pas hérité : ni son venv, ni son PATH.\n"
                "Le chemin doit être absolu (il est corrigé à l'enregistrement)."
            )
        )
        self.btn_path.setToolTip(t("Choisir le script"))
        self.edit_cwd.setPlaceholderText(t("dossier de travail (vide = dossier du script)"))
        self.edit_cwd.setToolTip(
            t(
                "Dossier courant de la console au lancement.\n"
                "Vide : le dossier du script lui-même, ce qui est le comportement d'un double-clic.\n"
                "Un dossier inexistant est refusé au lieu d'être remplacé silencieusement."
            )
        )
        self.btn_cwd.setToolTip(t("Choisir le dossier de travail"))
        self.btn_remove.setToolTip(t("Retirer ce script"))

    def _browse_path(self) -> None:
        start = self.edit_path.text().strip() or self._dialog.suggested_folder()
        chosen, _ = QFileDialog.getOpenFileName(self, t("Script à lancer"), start, file_filter())
        if chosen:
            self.edit_path.setText(chosen)
            if not self.edit_cwd.text().strip():
                self.edit_cwd.setText(str(Path(chosen).parent))
            if not self.edit_label.text().strip():
                self.edit_label.setText(Path(chosen).name)

    def _browse_cwd(self) -> None:
        start = self.edit_cwd.text().strip() or self._dialog.suggested_folder()
        chosen = QFileDialog.getExistingDirectory(self, t("Dossier de travail du script"), start)
        if chosen:
            self.edit_cwd.setText(chosen)

    def spec(self) -> ScriptSpec:
        return ScriptSpec(
            path=self.edit_path.text().strip(),
            cwd=self.edit_cwd.text().strip(),
            label=self.edit_label.text().strip(),
        )


class ScriptsDialog(QDialog):
    def __init__(self, repo: Repo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scriptsDialog")
        self.setMinimumWidth(860)

        self._repo_title = repo.title
        self._rows: list[ScriptRow] = []

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("dlgTitle")
        root.addWidget(self.title_label)

        self.hint = QLabel()
        self.hint.setObjectName("dlgHint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        self.rows_holder = QVBoxLayout()
        self.rows_holder.setSpacing(6)
        root.addLayout(self.rows_holder)

        self.add_row_button = QPushButton()
        self.add_row_button.setObjectName("btnAddScriptRow")
        theme.set_role(self.add_row_button, "ghost")
        self.add_row_button.clicked.connect(lambda: self.add_row(None))
        root.addWidget(self.add_row_button)

        self.error = QLabel("")
        self.error.setObjectName("dlgError")
        self.error.setWordWrap(True)
        root.addWidget(self.error)

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

        self.specs_result: list[ScriptSpec] = list(repo.scripts)
        for spec in repo.scripts:
            self.add_row(spec)
        if not repo.scripts:
            self.add_row(None)

    def retranslate(self) -> None:
        """Réécrit le titre, l'aide, les boutons et chaque ligne de script."""
        self.setWindowTitle(t("Scripts liés à {title}").format(title=self._repo_title))
        self.title_label.setText(t("Scripts de {title}").format(title=self._repo_title))
        self.hint.setText(
            (
                t("Lancés dans une console Windows séparée.")
                if IS_WINDOWS
                else t(
                    "Lancés dans un terminal séparé, fenêtre maintenue ouverte ; sans terminal "
                    "disponible, la sortie est écrite dans data/launches/ et son chemin est affiché à la barre d'état."
                )
            )
            + " "
            + t(
                "Extensions : {suffixes}. "
                "L'ordre de la liste est l'ordre du menu du bouton « Script ».\n"
                "Chaque script part de SON dossier et ne reçoit pas l'environnement de "
                "l'application (ni son venv, ni son PATH) : un « pip install » du script ne "
                "touche jamais l'application."
            ).format(suffixes=", ".join(script_suffixes()))
        )
        self.add_row_button.setText(t("Ajouter un script"))
        self.add_row_button.setToolTip(t("Ajoute une ligne vide. Rien n'est enregistré avant « Enregistrer »."))
        self.cancel.setText(t("Annuler"))
        self.cancel.setToolTip(t("Ferme sans modifier la liste des scripts de ce bandeau."))
        self.ok.setText(t("Enregistrer"))
        self.ok.setToolTip(
            t("Enregistre la liste dans data/state.json.\nL'ordre des lignes devient l'ordre du menu « Script ».")
        )
        for row in self._rows:
            row.retranslate()

    def add_row(self, spec: ScriptSpec | None) -> None:
        row = ScriptRow(self, spec)
        self._rows.append(row)
        self.rows_holder.addWidget(row)

    def remove_row(self, row: ScriptRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self.rows_holder.removeWidget(row)
        row.deleteLater()

    def suggested_folder(self) -> str:
        return self._rows[0].edit_cwd.text().strip() if self._rows else ""

    def _accept(self) -> None:
        """Normalise et vérifie ici : le chemin enregistré est absolu, le dossier existe."""
        specs: list[ScriptSpec] = []
        problems: list[str] = []
        for row in self._rows:
            candidate = row.spec()
            if not candidate.path:
                continue
            try:
                plan = plan_for(candidate)
            except ScriptError as exc:
                problems.append(str(exc))
                continue
            row.edit_path.setText(str(plan.script))
            row.edit_cwd.setText(str(plan.cwd))
            specs.append(ScriptSpec(path=str(plan.script), cwd=str(plan.cwd), label=candidate.label))
        if problems:
            self.error.setText(t("Scripts refusés : {problems}").format(problems=" ; ".join(problems)))
            return
        self.specs_result = specs
        self.accept()
