"""Lancement de scripts utilisateur dans une console séparée, sans rien leur imposer.

Règle centrale : le script doit se comporter comme s'il était lancé depuis son propre dossier
par l'explorateur Windows (ou par le gestionnaire de fichiers sur Linux). L'application ne doit
rien lui imposer. Deux fuites étaient possibles, elles sont fermées toutes les deux :

* le dossier courant : il est calculé en absolu depuis le chemin du script, un chemin relatif est
  refusé (sinon il serait résolu contre le dossier de l'application, ce qui fait créer des fichiers
  au mauvais endroit) ;
* l'environnement : l'application est portée par uv, qui pose `VIRTUAL_ENV` et met le venv de
  l'application en tête du `PATH`. Un script qui écrit simplement `pip install` ou `python`
  toucherait donc le venv de l'application. `launch_env()` retire ces traces avant de lancer quoi
  que ce soit.

La console, elle, n'existe que sous Windows (`CREATE_NEW_CONSOLE` : une fenêtre qui survit au
script). Sur Linux il n'y a aucune console attachée à une application graphique : le script est
donc lancé dans un émulateur de terminal trouvé sur le `PATH`, fenêtre maintenue ouverte ; à
défaut de terminal — ou sans session graphique — la sortie part dans un journal de
`data/launches/` dont le chemin est affiché à la barre d'état. Dans les deux cas le chemin du
script ne passe jamais dans une chaîne interprétée : il reste dans `argv`, et la seule chaîne
donnée à un shell est un littéral du programme (`HOLD_CONSOLE`).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.i18n import t
from app.models import ScriptSpec
from app.paths import app_root, data_dir

IS_WINDOWS: bool = os.name == "nt"

# Extensions acceptées : une liste courte par système, jamais une liste unique aux deux systèmes.
# Un `.sh` choisi sur Windows reste donc refusé (rien ne l'exécuterait), et un `.bat` sur Linux
# aussi : `plan_for()` les marque « refusé » dans l'infobulle et l'entrée de menu est grisée.
SCRIPT_SUFFIXES_WINDOWS: tuple[str, ...] = (".bat", ".cmd", ".ps1")
SCRIPT_SUFFIXES_POSIX: tuple[str, ...] = (".sh", ".bash", ".zsh")

NEW_CONSOLE: int = int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

# Jeu volontairement identique sur les deux systèmes : ces caractères sont légaux dans un nom de
# fichier POSIX, mais une seule règle des deux côtés garde un seul test et ferme tout chemin qui
# finirait un jour dans une ligne de commande.
SHELL_METACHARACTERS: frozenset[str] = frozenset({'"', "&", "|", "<", ">", "^", "\n", "\r"})

# Variables héritées qui désignent l'application (ou son interpréteur) au script enfant.
SCRUBBED_ENV_KEYS: frozenset[str] = frozenset(
    {
        "VIRTUAL_ENV",
        "VIRTUAL_ENV_PROMPT",
        "UV_PROJECT_ENVIRONMENT",
        "UV_RUN_RECURSION_DEPTH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE",
        "PYTHONEXECUTABLE",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
    }
)
# Le lanceur est piloté par uv : toute variable `UV_*` héritée parlerait de l'environnement de
# l'application à un script qui lance lui-même `uv`.
SCRUBBED_ENV_PREFIXES: tuple[str, ...] = ("UV_",)
# Variables à nettoyer par dossier (et non par nom) : un chemin qui pointe dans l'application
# désignerait ses bibliothèques. Un `LD_PRELOAD` personnel de l'utilisateur est conservé.
FILTERED_PATH_ENV_KEYS: tuple[str, ...] = ("LD_LIBRARY_PATH", "LD_PRELOAD")
# Sans elles, aucun émulateur de terminal ne peut ouvrir de fenêtre : jamais retirées.
KEEP_FOR_GRAPHICS: frozenset[str] = frozenset(
    {
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "DBUS_SESSION_BUS_ADDRESS",
    }
)

# Émulateurs de terminal testés dans l'ordre : (commande, option qui introduit le reste de argv).
# Syntaxe propre à chaque terminal : `RELEASEWATCH_TERMINAL` permet d'imposer le nom d'un autre,
# avec l'option de la table (`--` par défaut) ; une cible absente ou sans session graphique bascule
# sur le journal, jamais sur un échec silencieux.
TERMINAL_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("x-terminal-emulator", "--"),
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("xfce4-terminal", "-x"),
    ("mate-terminal", "--"),
    ("lxterminal", "-e"),
    ("xterm", "-e"),
    ("alacritty", "-e"),
    ("kitty", "--"),
    ("foot", "--"),
)
TERMINAL_OVERRIDE_VARIABLE: str = "RELEASEWATCH_TERMINAL"
DEFAULT_TERMINAL_OPTION: str = "--"
GRAPHICAL_SESSION_VARIABLES: tuple[str, ...] = ("DISPLAY", "WAYLAND_DISPLAY")
# Littéral de shell : `"$@"` est l'argv du script (jamais interpolé dans la chaîne), puis la
# fenêtre reste ouverte sur un shell interactif. Le marqueur `rc=` n'est pas traduit : c'est du
# shell, pas de l'interface de l'application.
HOLD_CONSOLE: str = '"$@"; printf "\\n[release-watch] rc=%s\\n" "$?"; exec "${SHELL:-/bin/sh}" -i'
SHELL_ARG0: str = "release-watch"
POSIX_SHELLS: tuple[str, ...] = ("/bin/bash", "/bin/sh")
SHEBANG_MAX_HEAD: int = 256
LOGS_FOLDER_NAME: str = "launches"
LOG_NAME_MAX: int = 40

KIND_CONSOLE: str = "console"
KIND_LOG: str = "journal"


class ScriptError(RuntimeError):
    """Script absent, extension non supportée, dossier invalide ou lancement impossible."""


@dataclass(slots=True)
class ScriptPlan:
    """Ce qui sera exécuté : vérifiable sans rien lancer."""

    script: Path
    cwd: Path
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return t("{name} · dossier {folder}").format(name=self.script.name, folder=self.cwd)


@dataclass(slots=True)
class LaunchResult:
    """Ce qui a été lancé : le mode sert à dire à l'utilisateur où regarder la sortie."""

    kind: str
    process: subprocess.Popen[str]
    log: Path | None = None

    @property
    def console(self) -> bool:
        return self.kind == KIND_CONSOLE


def script_suffixes() -> tuple[str, ...]:
    """Extensions acceptées sur le système courant. La seule source de cette liste."""
    return SCRIPT_SUFFIXES_WINDOWS if IS_WINDOWS else SCRIPT_SUFFIXES_POSIX


def _reject_shell_metacharacters(path: Path) -> None:
    """Un shell relit la ligne de commande : un métacaractère dans un chemin serait exécuté.

    Aucun de ces caractères n'est autorisé dans un nom de fichier Windows ; ils sont refusés aussi
    sur Linux, où ils sont pourtant légaux, pour garder une seule règle et un seul test.
    """
    found = sorted(char for char in str(path) if char in SHELL_METACHARACTERS)
    if found:
        raise ScriptError(
            t("Chemin de script refusé (caractères interprétés par l'interpréteur : {chars}) : {path}").format(
                chars=" ".join(repr(char) for char in found), path=path
            )
        )


def app_home() -> Path:
    """Racine de l'application : dossier du projet source, ou dossier de l'executable gele."""
    return app_root()


def blocked_env_folders() -> list[Path]:
    """Dossiers d'interpréteur à retirer du `PATH` enfant : le venv et le python de l'appli."""
    folders: list[Path] = []
    candidates = [
        os.environ.get("VIRTUAL_ENV", ""),
        os.environ.get("UV_PROJECT_ENVIRONMENT", ""),
        str(Path(sys.executable).parent),
    ]
    for raw in candidates:
        cleaned = raw.strip()
        if not cleaned:
            continue
        try:
            resolved = Path(cleaned).expanduser().resolve()
        except OSError:
            continue
        if resolved not in folders:
            folders.append(resolved)
    return folders


def _is_blocked_entry(entry: str, folders: list[Path]) -> bool:
    cleaned = entry.strip().strip('"')
    if not cleaned:
        return True
    try:
        resolved = Path(cleaned).expanduser().resolve()
    except OSError:
        return False
    return any(resolved == folder or folder in resolved.parents for folder in folders)


def _filter_path_variable(env: dict[str, str], key: str, folders: list[Path]) -> None:
    value = env.get(key)
    if value is None:
        return
    kept = [entry for entry in value.split(os.pathsep) if not _is_blocked_entry(entry, folders)]
    if kept:
        env[key] = os.pathsep.join(kept)
    else:
        env.pop(key, None)


def launch_env() -> dict[str, str]:
    """Environnement de la console enfant, débarrassé de tout ce qui vient de l'application."""
    env = dict(os.environ)
    for key in tuple(env):
        # Les variables de session graphique ne sont jamais retirées : sans elles, aucune fenêtre de
        # terminal ne s'ouvrirait et le mode journal s'imposerait en silence.
        if key in KEEP_FOR_GRAPHICS:
            continue
        if key in SCRUBBED_ENV_KEYS or key.startswith(SCRUBBED_ENV_PREFIXES):
            env.pop(key, None)
    folders = blocked_env_folders()
    for key in tuple(env):
        if key.upper() == "PATH":
            _filter_path_variable(env, key, folders)
        elif not IS_WINDOWS and key.upper() in FILTERED_PATH_ENV_KEYS:
            _filter_path_variable(env, key, [*folders, app_home()])
    return env


def _shebang_interpreter(first_line: str) -> list[str]:
    """Interprètes annoncés par une ligne « #! », liste vide si la ligne n'est pas un shebang.

    Le noyau n'accepte qu'un chemin absolu comme interprète : un `#!bash` est refusé au lieu d'être
    ignoré en silence, sinon le script tournerait avec un interprète différent de celui qu'il annonce.
    """
    line = first_line.lstrip("\ufeff").strip("\r\n")
    if not line.startswith("#!"):
        return []
    parts = line[2:].split()
    if not parts:
        return []
    if not parts[0].startswith("/"):
        raise ScriptError(t("Interprète de shebang refusé (chemin absolu attendu) : {shebang}").format(shebang=line))
    return parts


def _read_shebang(path: Path) -> list[str]:
    """Interprètes annoncés par la première ligne du script, liste vide si ce n'est pas un shebang."""
    try:
        with path.open("rb") as handle:
            head = handle.read(SHEBANG_MAX_HEAD)
    except OSError as exc:
        raise ScriptError(t("Script illisible : {path} ({exc})").format(path=path, exc=exc)) from exc
    lines = head.decode("utf-8", errors="replace").splitlines()
    return _shebang_interpreter(lines[0] if lines else "")


def _posix_shell() -> str:
    """Shell utilisé pour tenir la fenêtre de terminal ouverte : bash si présent, sinon sh."""
    return next((shell for shell in POSIX_SHELLS if Path(shell).is_file()), POSIX_SHELLS[-1])


def build_command(path: Path) -> list[str]:
    """argv du script : jamais une chaîne, jamais `shell=True`, sur les deux systèmes."""
    suffix = path.suffix.lower()
    supported = ", ".join(script_suffixes())
    if suffix not in script_suffixes():
        raise ScriptError(
            t("Extension non prise en charge : {suffix}. Supportées : {supported}.").format(
                suffix=suffix or t("(aucune)"), supported=supported
            )
        )
    if IS_WINDOWS:
        if suffix in (".bat", ".cmd"):
            return ["cmd.exe", "/c", str(path)]
        return ["powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    interpreter = _read_shebang(path) or [POSIX_SHELLS[-1]]
    # Seul le premier jeton est un executable : `#!/usr/bin/env bash` annonce `env`, et `bash` est
    # son argument (resolu par `env` au moment de l'executer, pas ici).
    if not Path(interpreter[0]).is_file():
        raise ScriptError(
            t("Interprète annoncé par le script introuvable : {interpreter} ({path})").format(
                interpreter=interpreter[0], path=path
            )
        )
    return [*interpreter, str(path)]


def resolve_script(spec: ScriptSpec) -> Path:
    """Chemin du script, toujours absolu : un chemin relatif serait résolu contre le dossier de l'appli."""
    raw = spec.path.strip()
    if not raw:
        raise ScriptError(t("Aucun chemin de script renseigné."))
    script = Path(raw).expanduser()
    if not script.is_absolute():
        raise ScriptError(
            t(
                "Chemin de script relatif refusé : {path}. Re-sélectionne le script avec le bouton "
                "pour mémoriser un chemin absolu."
            ).format(path=raw)
        )
    try:
        script = script.resolve()
    except OSError as exc:
        raise ScriptError(t("Chemin de script illisible : {path} ({exc})").format(path=raw, exc=exc)) from exc
    if not script.is_file():
        raise ScriptError(t("Script introuvable : {path}").format(path=script))
    return script


def resolve_cwd(spec: ScriptSpec, script: Path) -> Path:
    """Dossier courant du script : le sien, sauf si un dossier de travail a été déclaré et vérifié."""
    raw = spec.cwd.strip()
    if not raw:
        return script.parent
    folder = Path(raw).expanduser()
    if not folder.is_absolute():
        raise ScriptError(
            t(
                "Dossier de travail relatif refusé : {path}. Donne un dossier absolu, ou laisse vide "
                "pour utiliser le dossier du script."
            ).format(path=raw)
        )
    try:
        folder = folder.resolve()
    except OSError as exc:
        raise ScriptError(t("Dossier de travail illisible : {path} ({exc})").format(path=raw, exc=exc)) from exc
    if not folder.is_dir():
        raise ScriptError(t("Dossier de travail introuvable : {path}").format(path=folder))
    return folder


def plan_for(spec: ScriptSpec) -> ScriptPlan:
    """Tout ce qui sera lancé, calculé et vérifié sans lancer quoi que ce soit."""
    script = resolve_script(spec)
    _reject_shell_metacharacters(script)
    cwd = resolve_cwd(spec, script)
    _reject_shell_metacharacters(cwd)
    return ScriptPlan(
        script=script,
        cwd=cwd,
        command=build_command(script),
        env=launch_env(),
    )


def has_graphical_session(env: Mapping[str, str]) -> bool:
    """Une fenêtre de terminal n'est possible que si le serveur d'affichage est joignable."""
    return any(env.get(name) for name in GRAPHICAL_SESSION_VARIABLES)


def find_terminal(env: Mapping[str, str]) -> list[str] | None:
    """Émulateur de terminal à utiliser, `None` si aucun n'est exploitable ici.

    Aucun lancement n'est tenté : seule l'existence de l'exécutable est vérifiée. Le chemin
    d'écrasement (`RELEASEWATCH_TERMINAL`) est vérifié, lui, par un refus : un terminal déclaré à
    la main et absent doit être signalé, pas remplacé silencieusement par le journal.
    """
    if IS_WINDOWS or not has_graphical_session(env):
        return None
    wanted = env.get(TERMINAL_OVERRIDE_VARIABLE, "").strip()
    if wanted:
        if shutil.which(wanted, path=env.get("PATH")) is None:
            raise ScriptError(
                t("Terminal indiqué par {variable} introuvable : {wanted}").format(
                    variable=TERMINAL_OVERRIDE_VARIABLE, wanted=wanted
                )
            )
        option = next((flag for name, flag in TERMINAL_CANDIDATES if name == wanted), DEFAULT_TERMINAL_OPTION)
        return [wanted, option]
    for name, option in TERMINAL_CANDIDATES:
        found = shutil.which(name, path=env.get("PATH"))
        if found is not None:
            return [found, option]
    return None


def launch_log_path(script: Path, moment: datetime | None = None) -> Path:
    """Chemin du journal du mode sans terminal : un fichier par lancement, dans `data/launches/`."""
    stamp = (moment or datetime.now(tz=UTC)).strftime("%Y%m%d-%H%M%S")
    stem = re.sub(r"[^\w.-]", "_", script.stem)[:LOG_NAME_MAX] or "script"
    return data_dir() / LOGS_FOLDER_NAME / f"{stem}-{stamp}.log"


@contextmanager
def _refused(script: Path) -> Generator[None]:
    """Un refus du système devient un `ScriptError` affichable : jamais un traceback à l'interface."""
    try:
        yield
    except OSError as exc:
        raise ScriptError(t("Lancement impossible de {script} : {exc}").format(script=script, exc=exc)) from exc


def launch(spec: ScriptSpec) -> LaunchResult:
    """Lance le script et rend le mode employé : console (Windows ou terminal) ou journal."""
    plan = plan_for(spec)
    if IS_WINDOWS:
        with _refused(plan.script):
            process = subprocess.Popen(
                plan.command, cwd=str(plan.cwd), env=plan.env, creationflags=NEW_CONSOLE, text=True
            )
        return LaunchResult(KIND_CONSOLE, process)
    terminal = find_terminal(plan.env)
    if terminal is not None:
        argv = [*terminal, _posix_shell(), "-c", HOLD_CONSOLE, SHELL_ARG0, *plan.command]
        with _refused(plan.script):
            process = subprocess.Popen(
                argv,
                cwd=str(plan.cwd),
                env=plan.env,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
            )
        return LaunchResult(KIND_CONSOLE, process)
    log = launch_log_path(plan.script)
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("wb")
    except OSError as exc:
        raise ScriptError(
            t("Journal de lancement inaccessible : {folder} ({exc})").format(folder=log.parent, exc=exc)
        ) from exc
    try:
        with _refused(plan.script):
            process = subprocess.Popen(
                plan.command,
                cwd=str(plan.cwd),
                env=plan.env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
    finally:
        handle.close()
    return LaunchResult(KIND_LOG, process, log)
