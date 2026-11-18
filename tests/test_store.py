"""Persistance : round-trip des modeles, caps durs, ecriture atomique, lecture defensive.

Ces controles attrapent la derive du format : un champ de modele ajoute sans to_dict() /
from_dict() symetrique, ou un state.json plus gros que le cap, doivent echouer ici, pas
etre avales silencieusement par la lecture defensive.

Aucune valeur limite n'est recopiee : elles viennent de app.models.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import (
    MAX_NOTES_DOCK_WIDTH,
    MAX_RELEASES,
    MIN_NOTES_DOCK_WIDTH,
    MIN_WINDOW_WIDTH,
    AppState,
    ReleaseInfo,
    Repo,
    Settings,
)
from app.store import SCHEMA_VERSION, StateError, StateStore
from tests.sample import sample_repos, state_document


def store_in(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "data" / "state.json")


def test_le_fixture_ui_est_au_schema_courant() -> None:
    document = state_document()
    assert document["schema"] == SCHEMA_VERSION, (
        f"l'echantillon est au schema {document['schema']}, l'application est au {SCHEMA_VERSION}"
    )


@pytest.mark.parametrize("repo", sample_repos(), ids=lambda repo: repo.id)
def test_round_trip_d_un_repo(repo: Repo) -> None:
    """Un repo qui passe par le JSON doit revenir identique : sinon un champ est perdu."""
    assert Repo.from_dict(repo.to_dict()) == repo


def test_round_trip_des_reglages() -> None:
    reglages = Settings(max_versions=10, download_dir="D:/dl", notes_font_size=15, notes_dock_width=640)
    assert Settings.from_dict(reglages.to_dict()) == reglages


def test_relecture_defensive_d_un_schema_inconnu(tmp_path: Path) -> None:
    brut = {
        "schema": 999,
        "settings": {"max_versions": 4, "inconnu": {"deep": [1, 2]}},
        "repos": [{"id": "a/b", "owner": "a", "name": "b", "url": "https://github.com/a/b", "x": 1}],
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(brut), encoding="utf-8")
    etat = StateStore(path).load()
    assert etat.settings.max_versions == 5, "une valeur heritee d'un ancien spin retombe sur le cran"
    assert [repo.id for repo in etat.repos] == ["a/b"]
    assert etat.repos[0].title == "b", "un titre absent doit retomber sur le nom du repo"


def test_le_cap_max_versions_est_cadre_a_la_lecture() -> None:
    repo = Repo.from_dict({"id": "a/b", "owner": "a", "name": "b", "max_versions": 999})
    assert repo.max_versions <= MAX_RELEASES
    assert Repo.from_dict({"id": "a/b", "owner": "a", "name": "b"}).max_versions > 0


def test_json_invalide_leve(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{ ceci n'est pas du json", encoding="utf-8")
    with pytest.raises(StateError):
        StateStore(path).load()


def test_racine_non_objet_leve(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(StateError):
        StateStore(path).load()


def test_absence_de_fichier_donne_un_etat_vide(tmp_path: Path) -> None:
    assert StateStore(tmp_path / "absent.json").load().repos == []


def test_ecriture_atomique_et_sauvegarde(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    etat = AppState(settings=Settings(), repos=sample_repos())
    store.save(etat)
    assert store.path.is_file()
    assert not store.path.with_suffix(".json.tmp").exists(), "le fichier temporaire doit etre remplace"
    store.save(etat)
    assert Path(str(store.path) + ".bak").is_file(), "une sauvegarde doit preceder l'ecrasement"


def test_le_cap_d_ecriture_suit_les_deux_colonnes(tmp_path: Path) -> None:
    """La troncature a la licence est le cap des deux colonnes, plus un cap dur unique."""
    store = store_in(tmp_path)
    gros = Repo(
        id="gros/repo",
        owner="gros",
        name="repo",
        url="https://github.com/gros/repo",
        title="Gros",
        max_versions=5,
        max_rejected_versions=25,
        releases=[ReleaseInfo(tag=f"v{i}.0") for i in range(MAX_RELEASES + 12)],
    )
    store.save(AppState(settings=Settings(), repos=[gros]))
    assert len(store.load().repos[0].releases) == gros.storage_cap() == MAX_RELEASES + 5


def test_la_largeur_du_dock_notes_est_cadree() -> None:
    assert Settings.from_dict({"notes_dock_width": 99999}).notes_dock_width == MAX_NOTES_DOCK_WIDTH
    assert Settings.from_dict({"notes_dock_width": 1}).notes_dock_width == MIN_NOTES_DOCK_WIDTH


def test_une_fenetre_trop_etroite_retombe_sur_les_tailles_par_defaut() -> None:
    reglages = Settings.from_dict({"window_width": MIN_WINDOW_WIDTH - 40, "window_height": 10})
    assert reglages.window_width >= MIN_WINDOW_WIDTH
    assert reglages.window_height >= MIN_WINDOW_WIDTH
