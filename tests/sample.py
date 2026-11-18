"""Etat d'exemple des tests, construit avec les modeles de l'application.

Le fixture n'est plus du JSON fige : il passe par to_dict() et son numero de schema vient
de app.store. Il ne peut donc plus deriver quand le format de state.json change, et
test_store.py le verifie.
"""

from __future__ import annotations

import os

from app.models import Asset, ReleaseInfo, Repo, ScriptSpec, Settings
from app.store import SCHEMA_VERSION

# Les chemins d'exemple restent croyables sur le systeme qui execute les tests : un « D:/maj »
# s'affiche « refusé » sur Linux et fait mentir les captures comme les infobulles.
if os.name == "nt":
    DOSSIER_TELECHARGEMENT = "D:/telechargements"
    CHEMIN_SCRIPT = "D:/maj/update_pyside.bat"
    DOSSIER_SCRIPT = "D:/maj"
else:
    DOSSIER_TELECHARGEMENT = "/home/utilisateur/telechargements"
    CHEMIN_SCRIPT = "/home/utilisateur/maj/update_pyside.sh"
    DOSSIER_SCRIPT = "/home/utilisateur/maj"


def script_exemple() -> ScriptSpec:
    """Un ScriptSpec neuf a chaque appel : un bandeau ne doit pas partager son objet avec un autre."""
    return ScriptSpec(path=CHEMIN_SCRIPT, cwd=DOSSIER_SCRIPT, label="maj conda")


NOTES_WITH_CONTRIBUTORS = (
    "## 6.9.0\n\n- support **Qt 6.9**\n- corrections de `QtCore.Signal`\n\n"
    "## New Contributors\n\n"
    "- @alice made their first contribution in https://github.com/PySide/PySide6/pull/1\n"
    "- @bob made their first contribution in https://github.com/PySide/PySide6/pull/2\n\n"
    "**Full Changelog**: https://github.com/PySide/PySide6/compare/v6.8.0...v6.9.0\n"
)


def pyside_repo() -> Repo:
    """Bandeau deplace, filtre de tags actif, assets conserves, un script, une pre-release."""
    return Repo(
        id="pyside/pyside6",
        owner="PySide",
        name="PySide6",
        url="https://github.com/PySide/PySide6",
        title="PySide6",
        max_versions=5,
        tag_pattern="v6.*",
        local_version="v6.8.0",
        local_version_source="release",
        asset_include="*.whl",
        default_asset_name="PySide6-6.8.0-Qt6.8-Py3.13.whl",
        download_dir=DOSSIER_TELECHARGEMENT,
        downloads={"v6.9.0|PySide6-6.9.0-Qt6.9-Py3.13.whl": f"{DOSSIER_TELECHARGEMENT}/PySide6-6.9.0-Qt6.9-Py3.13.whl"},
        scripts=[script_exemple()],
        releases=[
            ReleaseInfo(
                tag="v6.9.0",
                name="6.9.0",
                url="https://github.com/PySide/PySide6/releases/tag/v6.9.0",
                published_at="2026-10-12T09:00:00Z",
                notes_md=NOTES_WITH_CONTRIBUTORS,
                assets=[
                    Asset(name="PySide6-6.9.0-Qt6.9-Py3.13.whl", url="https://x/1.whl", size=65432100),
                    Asset(name="PySide6-6.9.0-Debug.zip", url="https://x/3.zip", size=999),
                ],
            ),
            ReleaseInfo(
                tag="v6.8.1",
                name="6.8.1 rc",
                published_at="2026-09-02T09:00:00Z",
                notes_md="Pre-release de test.\n",
                prerelease=True,
                assets=[Asset(name="PySide6-6.8.1-Qt6.8-Py3.13.whl", url="https://x/4.whl", size=999)],
            ),
            ReleaseInfo(
                tag="v6.8.0",
                name="6.8.0",
                published_at="2026-07-02T09:00:00Z",
                notes_md="## 6.8.0\n\nStabilite.\n",
                assets=[Asset(name="PySide6-6.8.0-Qt6.8-Py3.13.whl", url="https://x/5.whl", size=999)],
            ),
            ReleaseInfo(
                tag="v6.7.0",
                name="6.7.0",
                published_at="2026-04-02T09:00:00Z",
                notes_md="Ancienne version.\n",
                assets=[Asset(name="PySide6-6.7.0.tar.gz", url="https://x/7.tar.gz", size=4242)],
            ),
            ReleaseInfo(
                tag="v6.6.0",
                name="6.6.0",
                published_at="2026-01-05T09:00:00Z",
                notes_md="Version obsolete.\n",
            ),
            ReleaseInfo(
                tag="v6.5.0",
                name="6.5.0",
                published_at="2025-10-05T09:00:00Z",
                notes_md="Version obsolete.\n",
            ),
            ReleaseInfo(
                tag="2.1.0",
                name="paquet annexe 2.1.0",
                published_at="2026-11-01T09:00:00Z",
                notes_md="Publie pour un paquet annexe, sans rapport avec PySide6.",
            ),
        ],
        last_fetch_at="2026-10-30T08:00:00+00:00",
        last_fetch_ok=True,
    )


def htmx_repo() -> Repo:
    """Bandeau replie, sans asset conserve, version locale a jour."""
    return Repo(
        id="htmx-dev/htmx",
        owner="htmx-dev",
        name="htmx",
        url="https://github.com/htmx-dev/htmx",
        title="htmx",
        collapsed=True,
        local_version="v2.0.5",
        local_version_source="release",
        releases=[
            ReleaseInfo(
                tag="v2.0.5",
                name="v2.0.5",
                published_at="2026-09-20T09:00:00Z",
                notes_md="bug fixes",
            )
        ],
        last_fetch_at="2026-10-30T08:01:00+00:00",
        last_fetch_ok=True,
    )


def broken_repo() -> Repo:
    """Dernier fetch en echec = etat d'erreur, et exclu du controle global."""
    return Repo(
        id="private/repo",
        owner="private",
        name="repo",
        url="https://github.com/private/repo",
        title="Repo casse",
        collapsed=True,
        excluded_check_all=True,
        last_fetch_at="2026-10-30T08:02:00+00:00",
        last_fetch_ok=False,
        last_fetch_error="Repo introuvable, orthographe a verifier, ou repo prive.",
    )


def sample_repos() -> list[Repo]:
    return [pyside_repo(), htmx_repo(), broken_repo()]


def state_document(repos: list[Repo] | None = None, settings: Settings | None = None) -> dict[str, object]:
    """Document state.json de l'echantillon, au schema courant de l'application."""
    return {
        "schema": SCHEMA_VERSION,
        "settings": (settings or Settings(max_versions=5, notes_font_size=13)).to_dict(),
        "repos": [repo.to_dict() for repo in (repos if repos is not None else sample_repos())],
    }
