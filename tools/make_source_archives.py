"""Fabrique les deux archives source d'une release, à partir du dépôt (aucun appel réseau).

Pourquoi deux archives alors que le contenu est le même : `git archive` exporte le contenu des
blobs, donc en LF partout. Le `.zip` « Windows » est livré tel quel, mais garder `.gitattributes`
dans l'archive Linux serait un piège : ce fichier impose `eol=crlf` au checkout, ce qui n'a aucun
sens sur ce système. L'archive Linux est donc la même, `.gitattributes` en moins.

Avertissement : `git archive` travaille sur le COMMIT courant, pas sur le dossier de travail.
Un fichier non commité n'apparaît pas dans l'archive. D'où l'ordre imposé par la release :
commit -> tag -> archives.

    uv.exe run python tools/make_source_archives.py --out C:\\rw_build
"""

from __future__ import annotations

import argparse
import io
import subprocess
import zipfile
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
APP_SLUG: str = "ReleaseWatch"
ARCHIVE_FORMAT: str = "zip"
# Le seul fichier que l'archive « linux » perd : il impose des fins de ligne Windows.
LINUX_DROP: str = ".gitattributes"


def git_archive_bytes(prefix: str) -> bytes:
    """Archive zip du HEAD, en mémoire, avec le dossier racine `prefix`."""
    rendu = subprocess.run(
        ["git", "archive", f"--format={ARCHIVE_FORMAT}", f"--prefix={prefix}/", "HEAD"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        check=False,
    )
    if rendu.returncode != 0:
        raise SystemExit(f"git archive a echoue : {rendu.stderr.decode('utf-8', 'replace').strip()}")
    return rendu.stdout


def drop_entries(archive: bytes, drops: tuple[str, ...]) -> bytes:
    """Réécrit une archive en retirant les entrées dont le nom relatif est dans `drops`."""
    source = zipfile.ZipFile(io.BytesIO(archive))
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as destination:
        for info in source.infolist():
            nom = info.filename.split("/", 1)[-1]
            if nom in drops:
                continue
            destination.writestr(info, source.read(info.filename))
    return tampon.getvalue()


def build(out_dir: Path, version: str) -> list[Path]:
    """Écrit les deux archives et rend leurs chemins."""
    out_dir.mkdir(parents=True, exist_ok=True)
    productions: list[Path] = []
    pour_systeme: list[tuple[str, tuple[str, ...]]] = [
        ("windows-x64", ()),
        ("linux-x64", (LINUX_DROP,)),
    ]
    for suffixe, drops in pour_systeme:
        prefix = f"{APP_SLUG}-{version}-source-{suffixe}"
        contenu = git_archive_bytes(prefix)
        if drops:
            contenu = drop_entries(contenu, drops)
        chemin = out_dir / f"{prefix}.zip"
        chemin.write_bytes(contenu)
        productions.append(chemin)
    return productions


def main() -> int:
    parseur = argparse.ArgumentParser(description="Archives source d'une release (dépôt -> zip).")
    parseur.add_argument("--out", type=Path, default=ROOT / "dist", help="dossier de destination")
    parseur.add_argument("--version", default="", help="numéro de version (sinon lu dans pyproject.toml)")
    arguments = parseur.parse_args()

    version = arguments.version or project_version()
    for chemin in build(arguments.out, version):
        print(f"archive source : {chemin} ({chemin.stat().st_size} octets)")
    return 0


def project_version() -> str:
    """Version déclarée dans `pyproject.toml` : le nom de l'archive ne peut pas la deviner."""
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as descripteur:
        return str(tomllib.load(descripteur)["project"]["version"])


if __name__ == "__main__":
    raise SystemExit(main())
