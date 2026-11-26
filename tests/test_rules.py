"""Etage logique pure : regles de filtrage, colonnes de versions, statut, categories de lignes.

Aucun widget ici : ces controles ne bougent pas quand l'interface change, et ils sont la
moitie des bugs deja rencontres. Ils tournent en quelques millisecondes.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app import filters
from app.models import (
    KIND_LATEST,
    KIND_LATEST_LOCAL,
    KIND_LOCAL,
    KIND_OTHER,
    KIND_PLAIN,
    KIND_STALE,
    MAX_DOWNLOADS,
    MAX_VISIBLE_VERSIONS,
    Asset,
    ReleaseInfo,
    Repo,
    Settings,
    Status,
    tag_matches,
)

REGLES_INCLURE: tuple[tuple[str, str, bool], ...] = (
    ("*.whl", "PySide6-6.9.0-Qt6.9-Py3.13.whl", True),
    ("*.whl", "pyproject.toml", False),
    ("PySide6-*", "PySide6-6.9.0.whl", True),
    ("PySide6-*", "other-6.9.0.whl", False),
    ("*py3.13*", "PySide6-6.9.0-py3.13-win_amd64.whl", True),
    ("*-py3.12.whl", "x-py3.12.whl", True),
    ("v0.2.*;v0.3.*", "v0.3.1", True),
    ("v0.2.*;v0.3.*", "v0.4.0", False),
    ("a,b", "a,b", True),
    ("re:^v\\d+\\.\\d+$", "v12.3", True),
    ("re:^v\\d+\\.\\d+$", "v12.3-rc1", False),
)

MOTIFS_DE_TAG: tuple[tuple[str, str, bool], ...] = (
    ("v0.2.*", "v0.2.1", True),
    ("v0.2.*", "v0.3.0", False),
    ("v0.2.*", "2.1.0", False),
    ("v0.*", "v0.3.0", True),
    ("release-??", "release-12", True),
    ("", "importe_peu", True),
)


def repo_sonde(**surcharge: object) -> Repo:
    """Petit repo de travail, surchargeable par test. Instance fraiche a chaque appel : aucune liste partagee."""
    base = Repo(id="acme/tool", owner="acme", name="tool", url="https://github.com/acme/tool", title="Tool")
    return replace(base, **surcharge)


@pytest.mark.parametrize(("inclure", "valeur", "attendu"), REGLES_INCLURE)
def test_regles_inclure(inclure: str, valeur: str, attendu: bool) -> None:
    assert filters.keep(valeur, inclure, "") is attendu, f"{inclure!r} contre {valeur!r}"


def test_exclusion_de_regime() -> None:
    assert not filters.keep("v1.0-rc2", "v1.*", "*-rc*"), "un tag exclu passe quand meme"
    assert filters.keep("v1.0", "v1.*", "*-rc*"), "l'exclusion a rejete un tag qui devait passer"
    assert filters.keep("v1.0", "", ""), "aucun motif doit laisser passer le tag"


@pytest.mark.parametrize("motif", ["re:[abc", "re:*"])
def test_regex_invalide_signalee(motif: str) -> None:
    assert filters.rules_error(motif), f"regex invalide non signalee : {motif!r}"


def test_motif_valide_non_signale() -> None:
    assert not filters.rules_error("*.whl;*setup.exe")


@pytest.mark.parametrize(("motif", "tag", "attendu"), MOTIFS_DE_TAG)
def test_motif_de_tag(motif: str, tag: str, attendu: bool) -> None:
    assert tag_matches(motif, tag) is attendu


def test_motif_de_tag_pilote_statut_et_colonnes() -> None:
    probe = repo_sonde(
        tag_pattern="v0.*",
        tag_exclude="*-rc*",
        local_version="2.1.0",
        releases=[
            ReleaseInfo(tag="2.1.0"),
            ReleaseInfo(tag="v0.2.5"),
            ReleaseInfo(tag="v0.3.0-rc1"),
            ReleaseInfo(tag="v0.3.0"),
        ],
        last_fetch_at="2026-01-01T00:00:00+00:00",
        last_fetch_ok=True,
    )
    assert probe.latest is not None and probe.latest.tag == "v0.3.0"
    assert [item.tag for item in probe.matching_releases] == ["v0.3.0", "v0.2.5"]
    assert sorted(item.tag for item in probe.other_releases) == ["2.1.0", "v0.3.0-rc1"]
    assert probe.status is not Status.UP_TO_DATE, "un tag hors motif a redonne l'etat A JOUR"
    assert not probe.tag_is_allowed("2.1.0"), "un tag hors motif est compare a la version locale"


def test_colonne_droite_bornee_par_le_choix_rejetees() -> None:
    autorises = [ReleaseInfo(tag=f"v1.{n}.0", published_at=f"2026-01-{n + 10:02d}T00:00:00+00:00") for n in range(8)]
    hors_motif = [ReleaseInfo(tag=f"2.{n}.0", published_at=f"2020-01-{n + 10:02d}T00:00:00+00:00") for n in range(4)]
    probe = repo_sonde(
        max_versions=1,
        max_rejected_versions=2,
        tag_pattern="v1.*",
        releases=[*autorises, *hors_motif],
    )
    assert [item.tag for item in probe.matching_releases] == ["v1.7.0"]
    assert [item.tag for item in probe.rejected_releases] == ["v1.6.0", "v1.5.0"]
    # Obsoletes et hors motif concourent, puis la colonne se tronque sur son propre reglage.
    assert len(probe.rejected_candidates) == 2 * probe.max_rejected_versions
    assert len(probe.rejected_candidates) > len(probe.rejected_releases)


def test_colonnes_jamais_plus_grosses_que_le_cap() -> None:
    """Les deux colonnes additionnees ne depassent jamais ce que la base est censee garder."""
    probe = repo_sonde(
        max_versions=25,
        max_rejected_versions=15,
        releases=[ReleaseInfo(tag=f"v{i}.0") for i in range(MAX_VISIBLE_VERSIONS + 10)],
    )
    assert len(probe.matching_releases) == 25, "la colonne retenue doit atteindre son reglage"
    assert len(probe.rejected_releases) == 15, "la colonne rejetee doit atteindre son reglage"
    assert len(probe.matching_releases) + len(probe.rejected_releases) <= probe.storage_cap()


def test_valeur_hors_cran_retombe_sur_le_cran_le_plus_proche() -> None:
    """Un state.json herite d'un ancien spin 1-25 doit se lire avec les combos affiches."""
    lu = Repo.from_dict({"id": "a/b", "owner": "a", "name": "b", "max_versions": 12, "max_rejected_versions": 8})
    assert lu.max_versions == 10
    assert lu.max_rejected_versions == 10
    assert Repo.from_dict({"id": "a/b", "owner": "a", "name": "b", "max_versions": 13}).max_versions == 15
    assert Settings.from_dict({"max_versions": 12}).max_versions == 10


def test_cap_de_stockage_est_le_maximum_des_deux_colonnes() -> None:
    """La base ne suit pas le reglage affiche : le remonter ne doit jamais exiger un re-fetch."""
    assert repo_sonde(max_versions=5, max_rejected_versions=5).storage_cap() == MAX_VISIBLE_VERSIONS
    assert repo_sonde(max_versions=25, max_rejected_versions=25).storage_cap() == MAX_VISIBLE_VERSIONS


def test_selection_stockee_remplit_les_deux_colonnes() -> None:
    sonde = repo_sonde(max_versions=5, max_rejected_versions=5)
    candidates = [ReleaseInfo(tag=f"v{n}.0") for n in range(20, 0, -1)]
    sonde.releases = sonde.pick_candidates(candidates, cap=sonde.storage_cap())
    assert len(sonde.matching_releases) == 5, "la colonne retenue doit atteindre son reglage"
    assert len(sonde.rejected_releases) == 5, "la colonne rejetee doit atteindre son reglage"


def test_reglages_25_et_15_remplissent_chaque_colonne() -> None:
    """Chaque colonne affiche son propre reglage, pas une somme plafonnee a 25."""
    sonde = repo_sonde(max_versions=25, max_rejected_versions=15)
    candidates = [ReleaseInfo(tag=f"v{n}.0") for n in range(60, 0, -1)]
    sonde.releases = sonde.pick_candidates(candidates, cap=sonde.storage_cap())
    gauche = [item.tag for item in sonde.matching_releases]
    droite = [item.tag for item in sonde.rejected_releases]
    assert len(gauche) == 25, "la colonne retenue doit atteindre son reglage"
    assert len(droite) == 15, "la colonne rejetee doit atteindre son reglage"
    assert gauche[-1] == "v36.0" and droite[0] == "v35.0", "la colonne de droite ne doit sauter aucune version"


def test_filtre_des_assets_en_base() -> None:
    probe = repo_sonde(
        tag_pattern="v*",
        asset_include="*.whl",
        asset_exclude="*debug*",
        releases=[
            ReleaseInfo(
                tag="v1.0",
                assets=[
                    Asset(name="a.whl", url="https://x/a.whl", size=10),
                    Asset(name="a-debug.whl", url="https://x/ad.whl", size=10),
                    Asset(name="a.tar.gz", url="https://x/a.tar.gz", size=10),
                ],
            )
        ],
    )
    kept, dropped = probe.apply_asset_filters()
    assert (kept, dropped) == (1, 2)
    assert [asset.name for release in probe.releases for asset in release.assets] == ["a.whl"]
    dumped = json.dumps(probe.to_dict())
    assert "a.tar.gz" not in dumped and "a-debug" not in dumped, "un asset filtre est serialise"


def test_recueil_desactive_jette_tout() -> None:
    probe = repo_sonde(
        assets_enabled=False,
        releases=[ReleaseInfo(tag="v1.0", assets=[Asset(name="a.whl", url="https://x/a.whl")])],
    )
    assert probe.apply_asset_filters() == (0, 1)
    assert probe.releases[0].assets == []
    assert not probe.asset_is_allowed("a.whl")


def test_choix_asset_par_defaut_abandonne() -> None:
    probe = repo_sonde(
        default_asset_name="a.whl",
        releases=[ReleaseInfo(tag="v1.0", assets=[Asset(name="a.whl", url="https://x/a.whl")])],
    )
    assert probe.prune_asset_choice()
    probe.asset_include = "*.zip"
    probe.apply_asset_filters()
    assert not probe.prune_asset_choice()


STATUTS: tuple[tuple[str, Status], ...] = (
    ("v1.2.0", Status.UP_TO_DATE),
    ("v1.1.0", Status.NEW_VERSION),
    ("v9.9.9", Status.AHEAD),
    ("", Status.UNKNOWN),
)


@pytest.mark.parametrize(("locale", "attendu"), STATUTS)
def test_statut_selon_version_locale(locale: str, attendu: Status) -> None:
    probe = repo_sonde(
        tag_pattern="v*",
        local_version=locale,
        releases=[ReleaseInfo(tag="hors_motif"), ReleaseInfo(tag="v1.2.0"), ReleaseInfo(tag="v1.1.0")],
        last_fetch_at="2026-01-01T00:00:00+00:00",
        last_fetch_ok=True,
    )
    assert probe.status is attendu


def test_un_tag_hors_motif_ne_donne_jamais_a_jour() -> None:
    probe = repo_sonde(
        tag_pattern="v*",
        local_version="hors_motif",
        releases=[ReleaseInfo(tag="hors_motif"), ReleaseInfo(tag="v1.2.0")],
        last_fetch_at="2026-01-01T00:00:00+00:00",
        last_fetch_ok=True,
    )
    assert probe.status is not Status.UP_TO_DATE, "un tag hors motif a redonne l'etat A JOUR"


def test_dernier_fetch_en_echec_prime_sur_tout() -> None:
    probe = repo_sonde(
        local_version="v1.2.0",
        releases=[ReleaseInfo(tag="v1.2.0")],
        last_fetch_at="2026-01-01T00:00:00+00:00",
        last_fetch_ok=False,
        last_fetch_error="Repo introuvable.",
    )
    assert probe.status is Status.ERROR


CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("v1.2.0", "left", KIND_LATEST),
    ("v1.1.0", "left", KIND_PLAIN),
    ("v1.0.0", "right", KIND_STALE),
    ("annexe", "right", KIND_OTHER),
)


@pytest.mark.parametrize(("tag", "cote", "attendu"), CATEGORIES)
def test_categorie_de_ligne(tag: str, cote: str, attendu: str) -> None:
    probe = repo_sonde(
        tag_pattern="v*",
        max_versions=1,
        max_rejected_versions=5,
        local_version="",
        releases=[
            ReleaseInfo(tag="v1.2.0"),
            ReleaseInfo(tag="v1.1.0"),
            ReleaseInfo(tag="v1.0.0"),
            ReleaseInfo(tag="annexe"),
        ],
    )
    release = next(item for item in probe.releases if item.tag == tag)
    assert probe.release_kind(release, cote) == attendu


def test_version_locale_designee_change_la_categorie() -> None:
    probe = repo_sonde(
        tag_pattern="v*",
        local_version="v1.1.0",
        releases=[ReleaseInfo(tag="v1.2.0"), ReleaseInfo(tag="v1.1.0")],
    )
    release = next(item for item in probe.releases if item.tag == "v1.1.0")
    assert probe.release_kind(release, "left") is KIND_LOCAL
    probe.local_version = "v1.2.0"
    latest = probe.latest
    assert latest is not None and probe.release_kind(latest, "left") is KIND_LATEST_LOCAL


def test_le_souvenir_des_fichiers_ecrits_tient_sur_le_bandeau() -> None:
    """Le souvenir porte par le repo : un fetch recree les assets, il ne doit pas perdre les chemins."""
    repo = repo_sonde()
    repo.remember_download("v1.0.0", "tool.zip", "chemin/un.zip")
    repo.remember_download("v1.0.0", "tool.tar.gz", "chemin/deux.tar.gz")
    repo.remember_download("v0.9.0", "tool.zip", "chemin/vieux.zip")
    assert repo.downloads_for("v1.0.0") == {"tool.zip": "chemin/un.zip", "tool.tar.gz": "chemin/deux.tar.gz"}
    assert repo.downloads_for("v0.9.0") == {"tool.zip": "chemin/vieux.zip"}, "les versions sont isolees"
    assert repo.downloads_for("v2.0.0") == {}, "une version inconnue ne doit rien inventer"
    assert Repo.from_dict(repo.to_dict()).downloads == repo.downloads


def test_le_souvenir_des_fichiers_ne_croit_sans_limite() -> None:
    repo = repo_sonde()
    for index in range(MAX_DOWNLOADS + 40):
        repo.remember_download("v1", f"f{index}.zip", f"chemin/f{index}.zip")
    assert len(repo.downloads) == MAX_DOWNLOADS, "le souvenir doit etre plafonne"
    assert "v1|f0.zip" not in repo.downloads, "c'est le plus ancien qui doit partir"
