"""Anti-régression de la traduction : clés littérales, table anglaise, dates et bascule."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QPushButton

from app.about import APP_NAME, APP_VERSION, window_title
from app.i18n import format_date, set_language, size_units, t
from app.models import Settings
from app.store import StateStore
from app.translations.en import EN
from app.widgets.input_dialog import TextInputDialog
from app.widgets.main_window import MainWindow
from app.widgets.repo_banner import RepoBanner
from tests.contract import BANNER_ROLES, INPUT_ROLES, WINDOW_ROLES
from tests.harness import click_role, role_of, settle
from tests.sample import state_document

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
WIDGETS_DIR = APP_DIR / "widgets"
TRANSLATION_PATH = APP_DIR / "translations" / "en.py"

VISIBLE_SETTERS = frozenset(
    {
        "addAction",
        "addItem",
        "setPlaceholderText",
        "setText",
        "setToolTip",
        "setWindowTitle",
    }
)


def _app_python_files() -> list[Path]:
    return [path for path in APP_DIR.rglob("*.py") if "translations" not in path.parts]


def _keys_used_in_code() -> set[str]:
    keys: set[str] = set()
    for path in _app_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                    raise AssertionError(f"la clé de t() doit être un littéral : {path}:{node.lineno}")
                if not isinstance(node.args[0].value, str):
                    raise AssertionError(f"la clé de t() doit être une chaîne : {path}:{node.lineno}")
                keys.add(node.args[0].value)
    return keys


def _raw_visible_literals() -> list[str]:
    violations: list[str] = []
    for path in sorted(WIDGETS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in VISIBLE_SETTERS:
                continue
            arguments = [
                *node.args,
                *(keyword.value for keyword in node.keywords if keyword.arg in {"text", "title", "label"}),
            ]
            for argument in arguments:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    if any(character.isalpha() for character in argument.value):
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.attr}")
    return violations


def test_table_anglaise_est_complete() -> None:
    manquantes = sorted(_keys_used_in_code() - set(EN))
    assert not manquantes, f"clés absentes de app/translations/en.py : {manquantes}"


def test_table_anglaise_sans_doublon() -> None:
    tree = ast.parse(TRANSLATION_PATH.read_text(encoding="utf-8"), filename=str(TRANSLATION_PATH))
    cles: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    cles.append(key.value)
    doublons = sorted({cle for cle in cles if cles.count(cle) > 1})
    assert not doublons, f"clés anglaises écrites deux fois : {doublons}"


def test_aucune_cle_de_t_construite() -> None:
    _keys_used_in_code()


def test_aucun_texte_visible_non_translate_dans_un_widget() -> None:
    violations = _raw_visible_literals()
    assert not violations, f"texte visible passé en brut : {violations}"


def test_dates_selon_langue() -> None:
    set_language("fr")
    assert format_date("2026-04-18T09:00:00Z") == "18/04/26"
    set_language("en")
    assert format_date("2026-04-18T09:00:00Z") == "26/04/18"


def test_unites_de_taille_selon_langue() -> None:
    set_language("fr")
    assert size_units() == ("Ko", "Mo", "Go")
    set_language("en")
    assert size_units() == ("kB", "MB", "GB")


def test_language_persistee_avant_construction(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state_document(settings=Settings(language="en"))), encoding="utf-8")
    assert StateStore(state_path).peek_language() == "en"
    assert StateStore(state_path).load().settings.language == "en"


def test_dialogue_de_saisie_a_des_boutons_traduits(input_dialog: TextInputDialog) -> None:
    ok = role_of(input_dialog, INPUT_ROLES, "ok", QPushButton)
    cancel = role_of(input_dialog, INPUT_ROLES, "annuler", QPushButton)
    champ = role_of(input_dialog, INPUT_ROLES, "champ", QLineEdit)

    assert ok.text() == t("Valider")
    assert cancel.text() == t("Annuler")
    assert ok.toolTip()
    assert cancel.toolTip()
    assert champ.text() == "1.2.3"


def test_dialogue_de_saisie_en() -> None:
    set_language("en")
    dialog = TextInputDialog(t("Version locale"), t("Titre affiché :"), "v6.8.0")
    ok = role_of(dialog, INPUT_ROLES, "ok", QPushButton)
    cancel = role_of(dialog, INPUT_ROLES, "annuler", QPushButton)
    assert ok.text() == EN["Valider"]
    assert cancel.text() == EN["Annuler"]
    assert ok.toolTip() == EN["Valide la saisie."]


def test_bascule_langue_reecrit_la_fenetre(window: MainWindow, banner: RepoBanner) -> None:
    col_gauche = role_of(banner, BANNER_ROLES, "colonne_retenues", QAbstractButton)
    message = role_of(window, WINDOW_ROLES, "message_etat", QLabel)

    titre_fr = window.windowTitle()
    colonne_fr = col_gauche.text()

    assert titre_fr == window_title()
    # Le numéro de version vient de `app.about` : aucune assertion ne doit le recopier en dur,
    # sinon chaque release obligerait à modifier les tests. On tient l'invariant
    # (nom + numéro + libellé traduit), pas une chaîne figée.
    assert titre_fr == f"{APP_NAME} {APP_VERSION} — {t('moniteur de releases GitHub')}"
    assert colonne_fr == t("↓↑ retenues")

    click_role(window, WINDOW_ROLES, "selecteur_langue")
    settle(window)

    assert window.windowTitle() == f"{APP_NAME} {APP_VERSION} — {EN['moniteur de releases GitHub']}"
    assert col_gauche.text() == EN["↓↑ retenues"]
    assert message.text() == EN["Interface en anglais."]

    click_role(window, WINDOW_ROLES, "selecteur_langue")
    settle(window)

    assert window.windowTitle() == titre_fr
    assert col_gauche.text() == colonne_fr
    assert message.text() == t("Interface en français.")


def test_selecteur_de_langue_a_un_tooltip(window: MainWindow) -> None:
    selecteur = role_of(window, WINDOW_ROLES, "selecteur_langue", QAbstractButton)
    assert selecteur.toolTip()
