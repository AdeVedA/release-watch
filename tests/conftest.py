"""Fixtures : QApplication hors ecran, etat d'exemple, fenetre deja affichee et stabilisee.

L'etat d'exemple vit dans tests/sample.py. Une fixture ne recable jamais un scenario a la
main : c'est tests/harness.py::ui_state() qui le fait, et qui retablit l'etat d'origine.
    uv.exe run pytest
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app import github, theme  # noqa: E402
from app.i18n import set_language  # noqa: E402
from app.models import Repo, Settings  # noqa: E402
from app.store import StateStore  # noqa: E402
from app.widgets.add_repo_dialog import AddRepoDialog  # noqa: E402
from app.widgets.input_dialog import TextInputDialog  # noqa: E402
from app.widgets.main_window import MainWindow  # noqa: E402
from app.widgets.repo_banner import RepoBanner  # noqa: E402
from app.widgets.scripts_dialog import ScriptsDialog  # noqa: E402
from app.widgets.settings_dialog import SettingsDialog  # noqa: E402
from tests.harness import WINDOW_SIZE, banner_of, settle  # noqa: E402
from tests.sample import sample_repos, state_document  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    """Un seul QApplication hors ecran pour toute la session, theme applique une fois."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication), "le fixture session ne peut pas fabriquer de QApplication"
    theme.apply_theme(app, ROOT / "data")
    yield app


@pytest.fixture(autouse=True)
def langue_fr() -> None:
    """Chaque test démarre en français : un test de bascule ne contamine pas le suivant."""
    set_language("fr")


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state_document(), indent=2), encoding="utf-8")
    return path


@pytest.fixture
def window(qapp: QApplication, state_file: Path) -> Iterator[MainWindow]:
    """Fenetre construite sur l'echantillon, affichee, geometrie stabilisee.

    showEvent() reprogramme relayout_release_rows() en differe : sans settle() ici, la
    geometrie lue par le test n'est pas celle qui s'affiche a l'ecran.
    """
    shell = MainWindow(qapp, StateStore(state_file))
    shell.resize(*WINDOW_SIZE)
    shell.show()
    settle(shell)
    yield shell
    shell.close()


@pytest.fixture
def banner(window: MainWindow) -> RepoBanner:
    """Le bandeau deplace avec des versions et des assets : celui de PySide6."""
    return banner_of(window, window.state.repos[0])


@pytest.fixture
def notes(window: MainWindow) -> QWidget:
    return window.notes


@pytest.fixture
def add_repo_dialog(window: MainWindow) -> QWidget:
    return AddRepoDialog(
        window._pool,
        github.GitHubClient,
        {repo.id for repo in window.state.repos},
        Settings().max_versions,
        window,
    )


@pytest.fixture
def scripts_dialog(window: MainWindow) -> QWidget:
    return ScriptsDialog(window.state.repos[0], window)


@pytest.fixture
def settings_dialog(window: MainWindow) -> QWidget:
    return SettingsDialog(window.state.settings, window)


@pytest.fixture
def input_dialog(window: MainWindow) -> TextInputDialog:
    return TextInputDialog("Titre de test", "Valeur", "1.2.3", window)


@pytest.fixture
def dialogs(add_repo_dialog: QWidget, scripts_dialog: QWidget, settings_dialog: QWidget) -> list[QWidget]:
    """Les trois dialogues, construits mais non affiches : les controles portent sur leurs widgets."""
    return [add_repo_dialog, scripts_dialog, settings_dialog]


@pytest.fixture
def repos() -> list[Repo]:
    """Les repos de l'echantillon, hors fenetre, pour les controles de logique."""
    return sample_repos()
