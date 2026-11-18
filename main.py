"""Point d'entrée : QApplication, langue, thème, fenêtre principale."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app import i18n, theme
from app.about import APP_NAME, set_console_title, set_windows_app_id, window_icon
from app.i18n import t
from app.paths import data_dir
from app.store import StateError, StateStore
from app.widgets.main_window import MainWindow

SMOKE_FLAG: str = "--smoke-test"
SMOKE_LOG_NAME: str = "smoke-test.log"
# Le relayout des lignes est programme en differe par `showEvent()` : sans cette temporisation,
# l'arret partirait avant la passe de layout, c'est-a-dire avant ce qu'on veut voir planter.
SMOKE_DELAY_MS: int = 2000


def _wants_smoke(args: list[str]) -> bool:
    """`--smoke-test` : demarrage complet, puis arret automatique. Destine a la CI only."""
    return SMOKE_FLAG in args


def _dire_en_erreur(texte: str) -> None:
    """Ecrire sur la sortie d'erreur, seulement si elle existe.

    Un executable construit sans console (`--windowed`) n'a ni entree ni sortie : PyInstaller
    met `sys.stderr` a None. Sans ce garde, afficher l'echec du mode fumee ferait planter le mode
    fumee lui-meme, et la CI perdrait le message qu'elle cherchait a lire.
    """
    if sys.stderr is not None:
        print(texte, file=sys.stderr)


def _journal() -> Path:
    """Fichier ou le mode fumee laisse sa trace : a cote de l'executable quand il est gele."""
    return data_dir() / SMOKE_LOG_NAME


def _vider_journal() -> None:
    """Effacer la trace d'une campagne precedente.

    Un vieux plantage laisse dans `data/` devrait accuser la campagne qui l'a produit, pas la
    suivante. Sans cet effacement, lire le journal apres un succes ferait croire a une panne.
    """
    try:
        _journal().unlink(missing_ok=True)
    except OSError as exc:
        _dire_en_erreur(f"journal : effacement impossible : {exc}")


def _signaler_en_fumee(texte: str) -> None:
    """Signaler un echec du mode fumee la ou on peut le relire apres coup.

    Le stderr ne suffit pas : dans un executable `--windowed` il vaut None, donc le code 4
    arriverait sans aucune trace de l'exception. Le journal est ecrit a cote de l'executable,
    dans le meme `data/` que `state.json`.
    """
    _dire_en_erreur(texte)
    chemin: Path = _journal()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")
    except OSError as exc:
        _dire_en_erreur(f"journal : ecriture impossible dans {chemin} : {exc}")


def _run_smoke(app: QApplication) -> int:
    """Une CI ne regarde pas un ecran : elle lit un code de sortie. D'ou ce mode.

    Les exceptions levees dans un slot Qt ne remontent pas jusqu'a `main()` : Qt les confie a
    `sys.excepthook` et poursuit. Sans capture ici, un plantage du demarrage rendrait donc
    code 0, c'est-a-dire un faux « l'executable fonctionne ».
    """
    problems: list[str] = []

    def capture(kind: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
        problems.append("".join(traceback.format_exception(kind, value, tb)))

    previous: object = sys.excepthook
    sys.excepthook = capture
    try:
        QTimer.singleShot(SMOKE_DELAY_MS, app.quit)
        app.exec()
    finally:
        sys.excepthook = previous
    if problems:
        _signaler_en_fumee(problems[0])
        return 4
    return 0


def main() -> int:
    args: list[str] = sys.argv[1:]
    smoke: bool = _wants_smoke(args)
    if smoke:
        # La plateforme Qt est lue a la construction de QApplication (pas a l'import de PySide6) :
        # sans ecran, c'est ici qu'il faut la poser, sinon c'est `QApplication` qui meurt.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _vider_journal()

    app = QApplication([sys.argv[0], *[arg for arg in args if arg != SMOKE_FLAG]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("release-watch")
    set_windows_app_id()
    set_console_title()
    app.setWindowIcon(window_icon())

    store = StateStore.default()
    # La langue est posée avant la première fenêtre : même un dialogue d'erreur
    # (thème cassé ou état illisible) s'affiche dans la langue demandée par state.json.
    i18n.set_language(store.peek_language())

    try:
        theme.apply_theme(app, store.folder)
    except theme.ThemeTokenError as exc:
        if smoke:
            _signaler_en_fumee(f"theme : {exc}")
        else:
            QMessageBox.critical(None, t("Thème"), str(exc))
        return 2

    try:
        window = MainWindow(app, store)
    except StateError as exc:
        if smoke:
            _signaler_en_fumee(f"etat : {exc}")
        else:
            QMessageBox.critical(
                None,
                t("État illisible"),
                t("{error}\n\nCorrige ou supprime le fichier, puis relance.").format(error=exc),
            )
        return 3

    # La feuille est posée AVANT toute fenêtre : chaque widget créé ensuite est polit
    # contre elle à sa création. Reposer la feuille après la construction re-polissait
    # les ~3 000 widgets des bandeaux pour rien (961 ms mesurées), et le re-layout des
    # lignes est déjà programmé par MainWindow.showEvent(), sur les largeurs réelles.
    window.show()
    if smoke:
        return _run_smoke(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
