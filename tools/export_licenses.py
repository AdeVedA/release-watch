"""Récupère les textes de licence des paquets INSTALLÉS, sans aucun appel réseau.

Pourquoi ce script : la licence d'un paquet est une obligation de distribution, et le texte
embarqué dans un `.exe` doit correspondre à la version exacte installée. Une copie faite à la
main devient fausse à la première mise à jour de dépendance. Ici la source est le dossier
`.dist-info` de chaque paquet du virtualenv : c'est local, reproductible, et vérifiable.

Ce que le script refuse de faire : inventer un texte. Si un paquet ne declare aucun fichier de
licence, ou si les textes légaux suivis à la main (`legal/`) manquent, il sort en code 1 avec la
liste exacte de ce qui manque. Une CI ne peut donc pas publier un livrable sous-licencié.

    uv.exe run python tools/export_licenses.py
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib.metadata import Distribution, distributions
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = ROOT / "licenses"
LEGAL_DIR: Path = ROOT / "legal"
INDEX_NAME: str = "INDEX.md"

# uv installe le groupe `dev` dans le meme virtualenv que les dependances de fonctionnement :
# sans ce tri, `licenses/` serait encombre des licences de pytest et de ses dependances, qui ne
# sont pas dans le livrable. Un nom inconnu reste cote « fonctionnement » : c'est le tri sur
# lequel on veut se tromper dans le sens prudent.
DEV_DISTRIBUTIONS: frozenset[str] = frozenset(
    {
        "pytest",
        "iniconfig",
        "packaging",
        "pluggy",
        "pygments",
        "colorama",
    }
)

# Textes légaux suivus à la main, parce qu'aucun paquet Python ne les fournit : PySide6 et
# shiboken6 ne livrent qu'un renvoi vers la licence commerciale Qt, pas le texte LGPL.
#
# Un seul texte est exige. L'exception « GNU LGPL version 3 additional permissions » de la Qt
# Company ne leve des obligations que la ou la bibliotheque n'est PAS remplacable par le destinataire
# (lien statique, executable d'un seul morceau). Le livrable est construit en `--onedir` : les
# `Qt6*.dll` restent des fichiers distincts que l'on peut ecraser, ce que la section 6 de la LGPL
# demande. L'exception n'apporte donc rien ici, et son texte n'est pas une obligation.
REQUIRED_LEGAL_FILES: tuple[str, ...] = ("lgpl-3.0.txt",)
LEGAL_SOURCES: dict[str, str] = {
    "lgpl-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
}

# Tout ce que contient `legal/` part dans le livrable (le `.exe` recoit le dossier entier par
# `--add-data "legal;legal"`), sauf ce mode d'emploi. Les deux chemins d'embarquement portent ainsi
# les memes textes, et un fichier ajoute ici est visible sans toucher au script.
LEGAL_DIR_README: str = "README.md"

LICENSE_NAME_HINTS: tuple[str, ...] = ("license", "licence", "copying", "notice", "authors")


@dataclass(frozen=True)
class LicenceFile:
    """Un fichier de licence trouvé dans un paquet installé."""

    distribution: str
    version: str
    expression: str
    filename: str
    source: Path


def is_license_file(path: Path) -> bool:
    """Nom évocateur (`LICENSE`, `LICENSE.APACHE`, `NOTICE`…) ou fichier du dossier `licenses/`."""
    if path.parent.name.lower() == "licenses":
        return True
    stem = path.name.lower().split(".")[0]
    return any(hint in stem for hint in LICENSE_NAME_HINTS)


def license_expression(dist: Distribution) -> str:
    """Expression SPDX déclarée par le paquet (`License-Expression`, sinon `License`)."""
    metadata = dist.metadata
    declared = (metadata.get("License-Expression") or metadata.get("License") or "").strip()
    return " ".join(declared.split()) or "(non declaree)"


def collected_files() -> list[LicenceFile]:
    """Tous les fichiers de licence des paquets installés, par paquet."""
    found: list[LicenceFile] = []
    for dist in distributions():
        name = (dist.metadata["Name"] or "").strip()
        version = dist.version or "?"
        if not name or name.lower() in DEV_DISTRIBUTIONS:
            continue
        for entry in dist.files or ():
            path = Path(str(dist.locate_file(entry)))
            if not is_license_file(path) or not path.is_file():
                continue
            found.append(
                LicenceFile(
                    distribution=name,
                    version=version,
                    expression=license_expression(dist),
                    filename=path.name,
                    source=path,
                )
            )
    return found


def runtime_distributions() -> list[str]:
    """Noms des paquets installés qui se retrouvent dans le livrable (développement exclu)."""
    noms: list[str] = []
    for dist in distributions():
        name = (dist.metadata["Name"] or "").strip().lower()
        if name and name not in DEV_DISTRIBUTIONS:
            noms.append(name)
    return sorted(set(noms))


def distributions_without_license(files: list[LicenceFile]) -> list[str]:
    """Paquets du livrable sans aucun texte de licence : bloquant pour une distribution."""
    covered = {item.distribution.lower() for item in files}
    return sorted(name for name in runtime_distributions() if name not in covered)


def write_index(entries: list[LicenceFile], legal_names: list[str]) -> None:
    """Tableau lisible de ce qui est embarqué : il accompagne le livrable dans `licenses/`."""
    lignes: list[str] = [
        "# Licences des composants embarqués",
        "",
        "Généré par `tools/export_licenses.py` depuis les paquets installés : ne pas éditer à la main.",
        "",
        "| Paquet | Version | Licence déclarée | Fichiers embarqués |",
        "| --- | --- | --- | --- |",
    ]
    par_paquet: dict[tuple[str, str, str], list[str]] = {}
    for item in entries:
        par_paquet.setdefault((item.distribution, item.version, item.expression), []).append(item.filename)
    for distribution, version, expression in sorted(par_paquet):
        fichiers = ", ".join(f"`{nom}`" for nom in sorted(par_paquet[(distribution, version, expression)]))
        lignes.append(f"| {distribution} | {version} | {expression} | {fichiers} |")
    if legal_names:
        lignes += ["", "## Textes légaux suivis à la main (`legal/`)", ""]
        lignes += [f"- `{nom}`" for nom in sorted(legal_names)]
    (OUTPUT_DIR / INDEX_NAME).write_text("\n".join(lignes) + "\n", encoding="utf-8")


def export() -> int:
    """Copie tout ce qui doit être embarqué, puis rend un code de sortie parlant."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    (OUTPUT_DIR / "runtime").mkdir(parents=True)

    entries = collected_files()
    for item in entries:
        dossier = OUTPUT_DIR / "runtime" / f"{item.distribution}-{item.version}"
        dossier.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item.source, dossier / item.filename)

    legal_names: list[str] = []
    manquants: list[str] = []
    (OUTPUT_DIR / "legal").mkdir(parents=True, exist_ok=True)
    if LEGAL_DIR.is_dir():
        for source in sorted(LEGAL_DIR.iterdir()):
            if not source.is_file() or source.name == LEGAL_DIR_README:
                continue
            legal_names.append(source.name)
            shutil.copyfile(source, OUTPUT_DIR / "legal" / source.name)
    for name in REQUIRED_LEGAL_FILES:
        if name not in legal_names:
            manquants.append(f"legal/{name}  (a recuperer : {LEGAL_SOURCES[name]})")

    for name in distributions_without_license(entries):
        manquants.append(f"paquet « {name} » installe sans aucun fichier de licence dans son .dist-info")

    write_index(entries, legal_names)

    print(f"licences copiees : {len(entries)} fichiers -> {OUTPUT_DIR.relative_to(ROOT)}/")
    for item in sorted(entries, key=lambda i: (i.distribution, i.filename)):
        print(f"  {item.distribution} {item.version}  {item.expression}  ->  {item.filename}")
    if manquants:
        print("\nMANQUANT (publication bloquee) :")
        for ligne in manquants:
            print(f"  - {ligne}")
        return 1
    return 0


def main() -> int:
    return export()


if __name__ == "__main__":
    raise SystemExit(main())
