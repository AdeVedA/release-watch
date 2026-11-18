"""Audit zéro-confiance, lancé par l'agent.

Prouve trois choses :
1. aucune connexion ne part pendant le démarrage, la construction des fenêtres et
   des dialogues (`socket` et `requests` sont neutralisés et enregistrés) ;
2. aucune redirection ne peut sortir du HTTPS ni de la liste blanche d'hôtes ;
3. un nom d'asset venu du réseau ne peut pas écrire hors du dossier choisi.

    uv.exe run python tools/audit_net.py
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json  # noqa: E402
from unittest import mock  # noqa: E402

import requests  # noqa: E402

NET_CALLS: list[str] = []


def _blocked_request(self: object, *args: object, **kwargs: object) -> requests.Response:
    url = kwargs.get("url") or (args[1] if len(args) > 1 else "?")
    NET_CALLS.append(str(url))
    raise requests.exceptions.RequestException("reseau neutralise par l'audit")


def _blocked_connection(*args: object, **kwargs: object) -> None:
    NET_CALLS.append("socket")
    raise OSError("socket neutralise par l'audit")


class _BlockedSocket(socket.socket):
    def __init__(self, *args: object, **kwargs: object) -> None:
        NET_CALLS.append("socket")
        raise OSError("socket neutralise par l'audit")


from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import github, scripts, theme  # noqa: E402
from app.models import Asset, ScriptSpec, Settings  # noqa: E402
from app.store import StateStore  # noqa: E402
from app.widgets.add_repo_dialog import AddRepoDialog  # noqa: E402
from app.widgets.main_window import MainWindow  # noqa: E402
from app.widgets.notes_dock import NotesDock  # noqa: E402
from app.widgets.scripts_dialog import ScriptsDialog  # noqa: E402
from app.widgets.settings_dialog import SettingsDialog  # noqa: E402

RESULTS: list[tuple[bool, str]] = []

# Temoins absolus sur le systeme qui execute l'audit : « D:/... » n'est pas absolu sous POSIX, un
# temoin de la mauvaise moitie serait refuse pour « chemin relatif » et masquerait la regle testee.
CHEMIN_TEMOIN = (
    Path("D:/temoin_inexistant/maj_hors_application.bat")
    if os.name == "nt"
    else Path("/temoin-inexistant/maj_hors_application.sh")
)
DOSSIER_ABSENT = "D:/un/dossier/qui/n-existe-pas" if os.name == "nt" else "/un-dossier-qui-n-existe-pas"


def check(condition: bool, label: str) -> None:
    RESULTS.append((bool(condition), label))


def expect_error(kind: type[BaseException], call: Callable[[], object], label: str) -> None:
    try:
        call()
    except kind:
        check(True, label)
        return
    except BaseException as exc:  # noqa: BLE001 - l'audit doit nommer l'erreur recue
        check(False, f"{label} : recu {type(exc).__name__} ({exc})")
        return
    check(False, f"{label} : aucune exception levee")


def phase_silence(app: QApplication) -> None:
    temp = Path(tempfile.mkdtemp(prefix="audit_"))
    state = {
        "schema": 1,
        "settings": {"max_versions": 5, "download_dir": ""},
        "repos": [
            {
                "id": "pyside/pyside6",
                "owner": "PySide",
                "name": "PySide6",
                "url": "https://github.com/PySide/PySide6",
                "title": "PySide6",
                "local_version": "v6.8.0",
                "scripts": [{"path": "D:/maj/a.bat", "cwd": "D:/maj", "label": "maj"}],
                "releases": [
                    {
                        "tag": "v6.9.0",
                        "name": "6.9.0",
                        "url": "https://github.com/PySide/PySide6/releases/tag/v6.9.0",
                        "notes_md": "- x",
                        "assets": [{"name": "a.whl", "url": "https://objects.githubusercontent.com/a.whl", "size": 1}],
                    }
                ],
                "last_fetch_at": "2026-10-30T08:00:00+00:00",
                "last_fetch_ok": True,
            }
        ],
    }
    temp.joinpath("state.json").write_text(json.dumps(state), encoding="utf-8")

    theme.apply_theme(app, ROOT / "data")
    window = MainWindow(app, StateStore(temp / "state.json"))
    window.show()
    app.processEvents()
    for repo in window.state.repos:
        window._banners[repo.id].refresh()
    AddRepoDialog(
        window._pool,
        github.GitHubClient,
        {repo.id for repo in window.state.repos},
        Settings().max_versions,
        window,
    )
    ScriptsDialog(window.state.repos[0], window)
    SettingsDialog(window.state.settings, window)
    window.notes.show_release("PySide6", window.state.repos[0].releases[0])
    app.processEvents()
    check(not NET_CALLS, f"aucune connexion au demarrage et a la construction (0 attendu, {len(NET_CALLS)})")
    window.close()


def phase_hygiene() -> None:
    client = github.GitHubClient()
    check(client._session.trust_env is False, "trust_env desactive (ni proxy implicite ni ~/.netrc)")
    source = (ROOT / "app" / "github.py").read_text(encoding="utf-8")
    check("allow_redirects=True" not in source, "aucun suivi automatique : allow_redirects=False partout")
    check(
        client._session.max_redirects > 0,
        "max_redirects laisse au defaut (a 0, requests leve TooManyRedirects des le premier 302)",
    )
    check("Authorization" not in client._session.headers, "aucun jeton envoye en mode anonyme")
    check(
        client._session.headers.get("User-Agent") == "script-launcher",
        "User-Agent present (GitHub le doit, sinon 403)",
    )
    client.close()


def phase_redirects() -> None:
    base = "https://api.github.com/repos/a/b"
    expect_error(
        github.InsecureURLError,
        lambda: github.next_hop({"Location": "http://evil.example/x"}, base),
        "redirection vers du HTTP refusee",
    )
    expect_error(
        github.RedirectRefusedError,
        lambda: github.next_hop({"Location": "https://evil.example/x"}, base),
        "redirection vers un hôte inconnu refusee",
    )
    expect_error(
        github.RedirectRefusedError,
        lambda: github.next_hop({"Location": "https://github.com.evil.tld/x"}, base),
        "redirection vers un suffixe imite (github.com.evil.tld) refusee",
    )
    check(
        github.next_hop({"location": "https://api.github.com/repos/c/d"}, base) == "https://api.github.com/repos/c/d",
        "en-tete 'location' en minuscules lu (verif defensif, requests normalise deja)",
    )
    check(
        github.next_hop({"Location": "https://api.github.com/repos/c/d"}, base) == "https://api.github.com/repos/c/d",
        "redirection legitime github.com -> github.com acceptee",
    )
    expect_error(
        github.GitHubError,
        lambda: github.next_hop({}, base),
        "redirection sans destination refusee",
    )
    for host, allowed in (
        ("https://raw.githubusercontent.com/o/r/x", True),
        ("https://objects.githubusercontent.com/x/y", True),
        ("https://codeload.github.com/o/r/tar.gz/refs/tags/v1", True),
        ("https://api.github.com.evil.tld/x", False),
        ("https://evil.tld/github.com", False),
        ("https://github.com.oops/", False),
    ):
        check(github.host_allowed(host) is allowed, f"liste blanche hotte : {host}")


def phase_egress() -> None:
    client = github.GitHubClient()
    folder = Path(tempfile.mkdtemp(prefix="audit_dl_"))
    expect_error(
        github.InsecureURLError,
        lambda: client.download_asset(Asset(name="x.zip", url="http://github.com/x.zip"), folder),
        "telechargement en HTTP refuse avant toute connexion",
    )
    expect_error(
        github.RedirectRefusedError,
        lambda: client.download_asset(Asset(name="x.zip", url="https://evil.example/x.zip"), folder),
        "telechargement vers un hôte hors liste refuse avant toute connexion",
    )
    client.close()
    check(not NET_CALLS, "les refus se font sans ouvrir de socket")


def phase_names() -> None:
    cases: list[tuple[str, str]] = [
        ("../../Windows/system32/evil.exe", "evil.exe"),
        ("C:\\Windows\\evil.exe", "evil.exe"),
        ("a/../b.zip", "b.zip"),
        ("nul.zip", "_nul.zip"),
        ("CON.txt", "_CON.txt"),
        ('we<ir>d".zip', "weird.zip"),
    ]
    for raw, expected in cases:
        got = github.safe_asset_name(raw, fallback="asset")
        check(got == expected, f"nom d'asset assaini : {raw!r} -> {got!r} (attendu {expected!r})")
    check(github.safe_asset_name("", fallback="asset") == "asset", "nom vide -> fallback")
    check(github.safe_asset_name("../../..", fallback="asset") == "asset", "traversee seule -> fallback")
    long_name = github.safe_asset_name("z" * 400 + ".zip", fallback="asset")
    check(len(long_name) <= github.MAX_NAME_LENGTH, "nom trop long tronque")
    for raw in ("../../x/y.exe", "C:\\x\\y.zip", "..\\..\\a.zip"):
        got = github.safe_asset_name(raw, fallback="asset")
        check(
            "/" not in got and "\\" not in got and ":" not in got,
            f"aucun separateur dans {got!r} (venu de {raw!r})",
        )


def phase_urls() -> None:
    for raw, expected in (
        ("https://github.com/PySide/PySide6", ("PySide", "PySide6")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("owner/repo", ("owner", "repo")),
    ):
        check(github.parse_repo_url(raw) == expected, f"URL acceptee : {raw}")
    for raw in (
        "https://evil.github.com/owner/repo",
        "https://github.com/./.",
        "http://gitlab.com/owner/repo",
        "https://github.com/owner",
        "",
    ):
        expect_error(
            github.BadRepoUrlError,
            lambda raw=raw: github.parse_repo_url(raw),
            f"URL refusee : {raw!r}",
        )
    expect_error(
        github.BadRepoUrlError,
        lambda: github.parse_repo_url("https://github.com/" + "o" * 120 + "/repo"),
        "nom de repo trop long refuse",
    )


def phase_scripts() -> None:
    expect_error(
        scripts.ScriptError,
        lambda: scripts._reject_shell_metacharacters(Path("D:/x&y;z.bat")),
        "metacaracteres de coquille refuses dans le chemin du script",
    )
    try:
        scripts._reject_shell_metacharacters(Path("D:/maj/update conda.bat"))
    except scripts.ScriptError as exc:
        check(False, f"chemin normal refuse a tort : {exc}")
    else:
        check(True, "chemin normal accepte")

    if scripts.IS_WINDOWS:
        check(
            scripts.build_command(Path("D:/a.ps1"))[0] == "powershell.exe",
            ".ps1 passe par powershell -File (pas d'interpretation de chaine)",
        )
        check(
            scripts.NEW_CONSOLE != 0,
            "CREATE_NEW_CONSOLE : le script garde sa console separee sur Windows",
        )
        check(
            all(isinstance(part, str) for part in scripts.build_command(Path("D:/a.bat"))),
            "commande construite en liste (aucun shell=True possible)",
        )
        expect_error(
            scripts.ScriptError,
            lambda: scripts.build_command(Path("D:/a.sh")),
            "script shell refuse sur Windows (rien ne l'executerait)",
        )
    else:
        temoins = Path(tempfile.mkdtemp(prefix="audit_scripts_"))
        shebang = temoins / "maj.sh"
        shebang.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
        check(
            scripts.build_command(shebang) == ["/bin/sh", str(shebang)],
            "le script shell est lance par l'interprete qu'il annonce dans son shebang",
        )
        check(
            all(isinstance(part, str) for part in scripts.build_command(shebang)),
            "commande construite en liste (aucun shell=True possible)",
        )
        sans_shebang = temoins / "sans_shebang.sh"
        sans_shebang.write_text("echo x\n", encoding="utf-8")
        check(
            scripts.build_command(sans_shebang) == ["/bin/sh", str(sans_shebang)],
            "script sans shebang : repli /bin/sh",
        )
        absent = temoins / "absent.sh"
        absent.write_text("#!/usr/bin/n-existe-pas\necho x\n", encoding="utf-8")
        expect_error(
            scripts.ScriptError,
            lambda: scripts.build_command(absent),
            "interprete annonce par le shebang et inexistant refuse",
        )
        expect_error(
            scripts.ScriptError,
            lambda: scripts.build_command(temoins / "maj.bat"),
            "script windows refuse sous Linux",
        )
        check(
            '"$@"' in scripts.HOLD_CONSOLE and str(shebang) not in scripts.HOLD_CONSOLE,
            "le chemin du script n'entre jamais dans la chaine donnee au shell",
        )
    expect_error(
        scripts.ScriptError,
        lambda: scripts.build_command(Path("D:/a.py")),
        "plus aucun .py lancable depuis l'application",
    )

    # Indépendance du processus enfant : ni le venv de l'application, ni son dossier.
    env = scripts.launch_env()
    leftover = [key for key in scripts.SCRUBBED_ENV_KEYS if key in env]
    check(not leftover, f"variables de l'application absentes de l'environnement enfant : {leftover or 'aucune'}")
    folders = scripts.blocked_env_folders()
    check(bool(folders), f"venv de l'application identifie pour le menage : {folders}")
    path_key = next((key for key in env if key.upper() == "PATH"), "")
    leaked = [entry for entry in env[path_key].split(os.pathsep) if scripts._is_blocked_entry(entry, folders)]
    check(not leaked, f"PATH enfant sans le venv de l'appli : {leaked or 'propre'}")
    check(env[path_key] != os.environ[path_key], "PATH enfant effectivement modifie")

    # Indépendance du dossier de travail. Aucun fichier n'est créé ni écrit ici :
    # `resolve_cwd` ne touche le disque que pour vérifier un remplacement, jamais pour écrire.
    outside = CHEMIN_TEMOIN
    chosen = scripts.resolve_cwd(ScriptSpec(path=str(outside)), outside)
    check(chosen == outside.parent, f"script place ailleurs : cwd = son propre dossier {chosen}")
    check(chosen != scripts.app_home().resolve(), "le dossier de l'appli n'est jamais le cwd par defaut")
    expect_error(
        scripts.ScriptError,
        lambda: scripts.resolve_cwd(ScriptSpec(path="", cwd=DOSSIER_ABSENT), outside),
        "dossier de travail inexistant refuse au lieu d'un repli silencieux",
    )
    expect_error(
        scripts.ScriptError,
        lambda: scripts.resolve_cwd(ScriptSpec(path="", cwd="dossier/relatif"), outside),
        "dossier de travail relatif refuse",
    )
    expect_error(
        scripts.ScriptError,
        lambda: scripts.plan_for(ScriptSpec(path="update.bat")),
        "chemin relatif refuse (jamais resolu contre le dossier de l'appli)",
    )
    expect_error(
        scripts.ScriptError,
        lambda: scripts.build_command(Path("D:/a.md")),
        f"extension hors {', '.join(scripts.script_suffixes())} refusee",
    )
    check(bool(scripts.launch_env()), "lenvironnement calcule accompagne le plan")

    if scripts.IS_WINDOWS:
        return

    # Ce qui est propre a POSIX : la fenetre de terminal, son absence, et le journal de repli.
    with mock.patch.dict(
        os.environ,
        {
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-1",
            "VIRTUAL_ENV": "/tmp/venv-de-l-appli",
            "UV_CACHE_DIR": "/tmp/uv",
        },
    ):
        garde = scripts.launch_env()
    check(
        garde.get("DISPLAY") == ":0" and garde.get("WAYLAND_DISPLAY") == "wayland-1",
        "les variables de session graphique ne sont jamais retirees",
    )
    check(not [key for key in garde if key.startswith("UV_")], "aucune variable uv de l'application ne fuite")
    with mock.patch.dict(os.environ, {"LD_PRELOAD": f"{scripts.app_home()}/vendor/lib.so:/home/u/mes_bibs/lib.so"}):
        filtre = scripts.launch_env()
    check(
        filtre.get("LD_PRELOAD") == "/home/u/mes_bibs/lib.so",
        f"LD_PRELOAD : seul le chemin de l'application est retire ({filtre.get('LD_PRELOAD')})",
    )
    sans_affichage = {
        key: value for key, value in scripts.launch_env().items() if key not in scripts.GRAPHICAL_SESSION_VARIABLES
    }
    check(scripts.find_terminal(sans_affichage) is None, "sans session graphique : mode journal, aucun terminal tente")
    with mock.patch.dict(os.environ, {"DISPLAY": ":0", scripts.TERMINAL_OVERRIDE_VARIABLE: "audit-terminal-absent"}):
        expect_error(
            scripts.ScriptError,
            lambda: scripts.find_terminal(scripts.launch_env()),
            "terminal impose par RELEASEWATCH_TERMINAL et inexistant refuse",
        )
    journal = scripts.launch_log_path(Path("/tmp/maj conda (1).sh"))
    check(
        journal.parent.name == "launches"
        and journal.parent.parent.name == "data"
        and journal.name.startswith("maj_conda__1_-"),
        f"journal de repli ecrit sous data/launches/ avec un nom sur : {journal.name}",
    )


def phase_links() -> None:
    accepted: list[str] = []
    refused: list[str] = []
    dock = NotesDock()
    dock.link_accepted.connect(accepted.append)
    dock.link_refused.connect(refused.append)
    for target in ("https://github.com/o/r", "http://evil.example", "file:///C:/Windows/x", "x"):
        dock._on_anchor(QUrl(target))
    check(accepted == ["https://github.com/o/r"], f"seul HTTPS ouvre : {accepted}")
    check(len(refused) == 3, f"liens refuses traces : {refused}")


def main() -> int:
    app = QApplication(sys.argv)
    with ExitStack() as gates:
        gates.enter_context(mock.patch.object(requests.Session, "get", _blocked_request))
        gates.enter_context(mock.patch.object(requests.Session, "request", _blocked_request))
        gates.enter_context(mock.patch.object(socket, "socket", _BlockedSocket))
        gates.enter_context(mock.patch.object(socket, "create_connection", _blocked_connection))
        gates.enter_context(mock.patch.object(socket, "getaddrinfo", _blocked_connection))
        phase_silence(app)
        phase_hygiene()
        phase_redirects()
        phase_egress()
        phase_names()
        phase_urls()
        phase_scripts()
        phase_links()

    failures = [label for ok, label in RESULTS if not ok]
    for ok, label in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(
        f"\n{len(RESULTS)} controles, {len(failures)} echecs, {len(NET_CALLS)} tentative(s) de connexion enregistree(s)"
    )
    return 1 if failures or NET_CALLS else 0


if __name__ == "__main__":
    raise SystemExit(main())
