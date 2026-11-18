"""Lanceur de scripts : refus de la coquille, extensions admises, independance du processus enfant.

Aucun script n'est lance ici, et un seul temoin est ecrit (dans `tmp_path`, pour la lecture du
shebang). `resolve_cwd` ne touche le disque que pour verifier un override.

Les temoins qui doivent etre absolus dependent du systeme : « D:/... » n'est pas un chemin absolu
sous POSIX et « /home/... » ne l'est pas sous Windows. Un temoin de la mauvaise moitie serait
refuse pour « chemin relatif » et masquerait la regle que le test pretend verifier.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app import scripts
from app.models import ScriptSpec

IS_WINDOWS = os.name == "nt"
DOS = pytest.mark.skipif(IS_WINDOWS, reason="comportement propre a POSIX")
WIN = pytest.mark.skipif(not IS_WINDOWS, reason="comportement propre a Windows")

if IS_WINDOWS:
    CHEMIN_TEMOIN = Path("D:/temoin_inexistant/maj_hors_application.bat")
    DOSSIER_ABSENT = "D:/un/dossier/qui/n-existe-pas"
else:
    CHEMIN_TEMOIN = Path("/temoin-inexistant/maj_hors_application.sh")
    DOSSIER_ABSENT = "/un/dossier/qui/n-existe-pas"


@pytest.mark.parametrize("chemin", ["D:/x&y;z.bat", "D:/a|b.bat", "D:/a>b.bat", "D:/a^b.bat"])
def test_metacaracteres_de_coquille_refuses(chemin: str) -> None:
    with pytest.raises(scripts.ScriptError):
        scripts._reject_shell_metacharacters(Path(chemin))


@pytest.mark.parametrize("chemin", ["D:/maj/update conda.bat", "D:/un-dossier/maj.bat", "D:/a(1).bat"])
def test_chemin_normal_accepte(chemin: str) -> None:
    scripts._reject_shell_metacharacters(Path(chemin))


@WIN
def test_powershell_passe_par_file() -> None:
    assert scripts.build_command(Path("D:/a.ps1"))[0] == "powershell.exe"


@WIN
def test_la_console_windows_separee_est_gardee() -> None:
    """Le drapeau qui ouvre une console distincte ne doit pas disparaitre de Windows."""
    # Memes precautions qu'a `app/scripts.py:49` : lire l'attribut par `getattr` garde la
    # verification des types propre a chaque systeme sans inventer un membre sous Linux.
    assert scripts.NEW_CONSOLE == int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0)) != 0


@DOS
def test_shebang_dict_l_interprete_du_script(tmp_path: Path) -> None:
    script = tmp_path / "maj.sh"
    script.write_text("#!/usr/bin/env bash\necho bonjour\n", encoding="utf-8")
    assert scripts.build_command(script) == ["/usr/bin/env", "bash", str(script)]


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        ("#!/usr/bin/env bash\n", ["/usr/bin/env", "bash"]),
        ("#!/bin/sh\n", ["/bin/sh"]),
        ("#!/bin/bash -e\r\n", ["/bin/bash", "-e"]),
        (": rien\n", []),
        ("", []),
    ],
)
def test_le_shebang_declare_l_interprete(ligne: str, attendu: list[str]) -> None:
    assert scripts._shebang_interpreter(ligne) == attendu


def test_shebang_sans_chemin_absolu_refuse() -> None:
    """Le noyau ignore un `#!bash` : le refuser vaut mieux qu'un interpreter different de celui annonce."""
    with pytest.raises(scripts.ScriptError):
        scripts._shebang_interpreter("#!bash\n")


def test_le_shebang_s_arrete_au_premier_saut_de_ligne(tmp_path: Path) -> None:
    """Gardien : la ligne suivante ne devient pas un interprete (le « echo » du script)."""
    script = tmp_path / "temoin.sh"
    script.write_text("#!/bin/sh\necho bonjour\n", encoding="utf-8")
    assert scripts._read_shebang(script) == ["/bin/sh"]


@pytest.mark.parametrize("extension", [".py", ".md", ".txt", ".exe"])
def test_extension_hors_liste_refusee(extension: str) -> None:
    with pytest.raises(scripts.ScriptError):
        scripts.build_command(Path(f"D:/a{extension}"))


@pytest.mark.parametrize("extension", [".bat", ".cmd", ".ps1"])
@DOS
def test_extension_windows_refusee_hors_windows(extension: str) -> None:
    with pytest.raises(scripts.ScriptError):
        scripts.build_command(Path(f"/tmp/a{extension}"))


@pytest.mark.parametrize("extension", [".sh", ".bash", ".zsh"])
@WIN
def test_extension_posix_refusee_hors_posix(extension: str) -> None:
    with pytest.raises(scripts.ScriptError):
        scripts.build_command(Path(f"D:/a{extension}"))


def test_extensions_admises_declarables() -> None:
    """`script_suffixes()` est la seule liste d'extensions : courte, non vide, propre au systeme."""
    attendues = {".bat", ".cmd", ".ps1"} if IS_WINDOWS else {".sh", ".bash", ".zsh"}
    assert set(scripts.script_suffixes()) == attendues, (
        "une extension ajoutee doit garder la regle des metacaracteres et l'interdit .py"
    )
    assert not set(scripts.SCRIPT_SUFFIXES_WINDOWS) & set(scripts.SCRIPT_SUFFIXES_POSIX), (
        "les deux listes ne doivent jamais se recouvrir : un script refuse est affiche refusé"
    )


@pytest.mark.parametrize("extension", scripts.SCRIPT_SUFFIXES_WINDOWS + scripts.SCRIPT_SUFFIXES_POSIX)
def test_commande_construite_en_liste(extension: str, tmp_path: Path) -> None:
    """Toute extension connue du systeme rend une liste de chaines : `shell=True` reste impossible."""
    temoin = tmp_path / f"a{extension}"
    if extension not in scripts.script_suffixes():
        with pytest.raises(scripts.ScriptError):
            scripts.build_command(temoin)
        return
    temoin.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
    commande = scripts.build_command(temoin)
    assert commande and all(isinstance(partie, str) for partie in commande), commande


def test_environnement_enfant_debarasse_du_venv_de_l_appli() -> None:
    env = scripts.launch_env()
    restes = [cle for cle in scripts.SCRUBBED_ENV_KEYS if cle in env]
    assert not restes, f"variables de l'application encore presentes : {restes}"
    dossier_venv = scripts.blocked_env_folders()
    assert dossier_venv, "le venv de l'appli doit etre identifie pour le menage"
    cle_chemin = next((cle for cle in env if cle.upper() == "PATH"), "")
    fuites = [entree for entree in env[cle_chemin].split(os.pathsep) if scripts._is_blocked_entry(entree, dossier_venv)]
    assert not fuites, f"le PATH enfant contient encore l'environnement de l'appli : {fuites}"
    assert env[cle_chemin] != os.environ[cle_chemin], "le PATH enfant doit etre reellement modifie"


def test_le_uv_de_l_appli_ne_fuite_pas_dans_l_environnement_enfant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV_CACHE_DIR", "/tmp/uv-cache-temoin")
    monkeypatch.setenv("UV_SYSTEM_PYTHON", "1")
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    restes = [cle for cle in scripts.launch_env() if cle.startswith("UV_")]
    assert not restes, f"variables uv de l'application encore presentes : {restes}"


def test_la_session_graphique_n_est_jamais_retiree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans DISPLAY ni WAYLAND_DISPLAY, aucun terminal ne s'ouvre : le menage doit passer a cote."""
    cibles = sorted(scripts.KEEP_FOR_GRAPHICS)
    for cle in cibles:
        monkeypatch.setenv(cle, f"temoin-{cle}")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv-de-l-appli")
    monkeypatch.setenv("PYTHONPATH", "/tmp/src-de-l-appli")
    env = scripts.launch_env()
    for cle in cibles:
        assert env.get(cle) == f"temoin-{cle}", f"{cle} a ete retire de l'environnement enfant"
    assert "VIRTUAL_ENV" not in env and "PYTHONPATH" not in env


@DOS
def test_sans_session_graphique_aucun_terminal_n_est_propose() -> None:
    env = {
        cle: valeur for cle, valeur in scripts.launch_env().items() if cle not in scripts.GRAPHICAL_SESSION_VARIABLES
    }
    assert scripts.find_terminal(env) is None, "sans serveur d'affichage, le mode journal s'impose"


@DOS
def test_terminal_detecte_est_un_executable_existant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun lancement : la detection ne fait que chercher l'executable."""
    monkeypatch.setenv("DISPLAY", ":0")
    found = scripts.find_terminal(scripts.launch_env())
    assert found is None or Path(found[0]).is_file(), found


@DOS
def test_terminal_impose_par_variable_inexistant_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un terminal declare a la main et absent doit etre signale, pas remplace par le journal."""
    monkeypatch.setenv(scripts.TERMINAL_OVERRIDE_VARIABLE, "terminal-qui-n-existe-pas")
    monkeypatch.setenv("DISPLAY", ":0")
    with pytest.raises(scripts.ScriptError):
        scripts.find_terminal(scripts.launch_env())


@DOS
def test_le_journal_d_un_lancement_sans_terminal_va_dans_data_launches() -> None:
    journal = scripts.launch_log_path(Path("/tmp/de/maj conda (1).sh"))
    assert journal.parent.name == "launches" and journal.parent.parent.name == "data", journal
    assert journal.name.startswith("maj_conda__1_-") and journal.suffix == ".log", journal.name


def test_script_ailleurs_que_dans_l_appli_prend_son_propre_dossier() -> None:
    choisi = scripts.resolve_cwd(ScriptSpec(path=str(CHEMIN_TEMOIN)), CHEMIN_TEMOIN)
    assert choisi == CHEMIN_TEMOIN.parent
    assert choisi != scripts.app_home().resolve(), "le dossier de l'appli n'est jamais le cwd par defaut"


def test_dossier_de_travail_inexistant_refuse() -> None:
    with pytest.raises(scripts.ScriptError):
        scripts.resolve_cwd(ScriptSpec(path="", cwd=DOSSIER_ABSENT), CHEMIN_TEMOIN)


def test_dossier_de_travail_relatif_refuse() -> None:
    with pytest.raises(scripts.ScriptError):
        scripts.resolve_cwd(ScriptSpec(path="", cwd="dossier/relatif"), CHEMIN_TEMOIN)


def test_chemin_de_script_relatif_refuse() -> None:
    """Jamais de resolution contre le dossier de l'appli : un chemin relatif est un refus."""
    with pytest.raises(scripts.ScriptError):
        scripts.plan_for(ScriptSpec(path="update.bat"))


def test_surcharge_de_dossier_acceptee_si_existante(tmp_path: Path) -> None:
    """Aucun temoin n'est cree ici : resolve_cwd ne touche le disque que pour verifier le cwd."""
    choisi = scripts.resolve_cwd(ScriptSpec(path="", cwd=str(tmp_path)), CHEMIN_TEMOIN)
    assert choisi == tmp_path.resolve()


def test_resume_d_un_plan_sans_lancement() -> None:
    """Le resume annoncant le script et son dossier se lit sans rien executer."""
    plan = scripts.ScriptPlan(
        script=CHEMIN_TEMOIN,
        cwd=CHEMIN_TEMOIN.parent,
        command=[str(CHEMIN_TEMOIN)],
    )
    assert plan.summary.startswith(f"{CHEMIN_TEMOIN.name} · dossier "), plan.summary
    assert plan.command[0]


def test_affichage_d_un_script_sans_etiquette() -> None:
    assert ScriptSpec(path="D:/maj/update conda.bat").display == "update conda.bat"
    assert ScriptSpec(path="D:/maj/a.bat", label="maj conda").display == "maj conda"
