"""Invariants de l'interface : ce qui doit rester vrai quel que soit le scenario.

Aucune coordonnee de pixel, aucun nom d'attribut de widget : on verifie des regles
(« replie = une ligne », « tout widget interactif a un tooltip », « les roles du contrat
existent »). Un widget renomme ou deplace ne casse rien ici : seul tests/contract.py
bouge. Ce qui releve du rendu (alignement a x pixels pres, boites dessinees) ne se juge
pas par assertion, mais à l'oeil.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QWidget,
)

from app import about, theme
from app.models import (
    KIND_LATEST,
    KIND_LATEST_LOCAL,
    KIND_LOCAL,
    KIND_OTHER,
    KIND_STALE,
    STATUS_TOKEN,
    Status,
    status_label,
)
from app.widgets.elided_label import ElidedLabel
from app.widgets.ghost_field import GhostLineEdit
from app.widgets.main_window import MainWindow
from app.widgets.repo_banner import STATUS_GLYPH, TWO_COLUMNS_MIN, RepoBanner
from tests.contract import (
    ADD_REPO_ROLES,
    ASSET_CONTROL_ROLES,
    ASSET_KEPT_ROLES,
    BANNER_ROLES,
    DETAIL_ROLES,
    HEAD_ROLES,
    NOTES_ROLES,
    ROW_ROLES,
    SCRIPTS_ROLES,
    SETTINGS_ROLES,
    WINDOW_ROLES,
)
from tests.harness import banner_of, find_role, must_find, role_of, settle, ui_state

INTERACTIVE: tuple[type, ...] = (QPushButton, QToolButton, QCheckBox, QComboBox, QLineEdit, QSpinBox)
QT_INTERNAL: frozenset[str] = frozenset({"qt_toolbar_ext_button", "qt_spinbox_lineedit"})


# ------------------------------------------------------------------ contrat de nommage


@pytest.mark.parametrize("role", sorted(BANNER_ROLES))
def test_manifeste_bandeau(role: str, banner: RepoBanner) -> None:
    assert find_role(banner, BANNER_ROLES, role) is not None, f"le role {role!r} a disparu du bandeau"


@pytest.mark.parametrize("role", sorted(WINDOW_ROLES))
def test_manifeste_fenetre(role: str, window: MainWindow) -> None:
    assert find_role(window, WINDOW_ROLES, role) is not None, f"le role {role!r} a disparu de la fenetre"


@pytest.mark.parametrize("role", sorted(NOTES_ROLES))
def test_manifeste_panneau_notes(role: str, window: MainWindow) -> None:
    assert find_role(window.notes, NOTES_ROLES, role) is not None, f"le role {role!r} a disparu du panneau notes"


def test_manifeste_dialogue_ajouter_un_repo(add_repo_dialog: QWidget) -> None:
    absents = [role for role in ADD_REPO_ROLES if find_role(add_repo_dialog, ADD_REPO_ROLES, role) is None]
    assert not absents, f"roles disparus du dialogue ajouter un repo : {absents}"


def test_manifeste_dialogue_scripts(scripts_dialog: QWidget) -> None:
    absents = [role for role in SCRIPTS_ROLES if find_role(scripts_dialog, SCRIPTS_ROLES, role) is None]
    assert not absents, f"roles disparus du dialogue scripts : {absents}"


def test_manifeste_dialogue_reglages(settings_dialog: QWidget) -> None:
    absents = [role for role in SETTINGS_ROLES if find_role(settings_dialog, SETTINGS_ROLES, role) is None]
    assert not absents, f"roles disparus du dialogue reglages : {absents}"


# ------------------------------------------------------------------ tooltips et etats


def test_tout_widget_interactif_a_un_tooltip(window: MainWindow, dialogs: list[QWidget]) -> None:
    """Un widget cliquable sans tooltip est une regression : l'information n'existe plus ailleurs."""
    sans_tooltip: list[str] = []
    vus: set[int] = set()
    for root in (window, *dialogs):
        for widget in (root, *root.findChildren(QWidget)):
            if id(widget) in vus or not isinstance(widget, INTERACTIVE):
                continue
            vus.add(id(widget))
            if widget.objectName() in QT_INTERNAL or not widget.isEnabled():
                continue
            if not widget.toolTip().strip():
                sans_tooltip.append(f"{type(widget).__name__}#{widget.objectName() or 'sans-nom'}")
    assert not sans_tooltip, f"widgets interactifs sans tooltip : {sans_tooltip}"


def test_etat_visible_est_un_point_et_le_libelle_seulement_dans_le_tooltip(window: MainWindow) -> None:
    for repo in window.state.repos:
        bann = banner_of(window, repo)
        etiquette = role_of(bann, BANNER_ROLES, "etat", QLabel)
        assert etiquette.text() == STATUS_GLYPH, f"{repo.id} : l'etat s'affiche en texte"
        assert status_label(repo.status) in etiquette.toolTip(), f"{repo.id} : le libelle d'etat a quitte le tooltip"
        assert bann.property("status") == STATUS_TOKEN[repo.status], f"{repo.id} : propriete QSS d'etat fausse"


def test_la_version_locale_ne_vient_jamais_de_l_installation(banner: RepoBanner) -> None:
    tooltip = must_find(banner, BANNER_ROLES, "version_locale").toolTip()
    assert "installation locale" in tooltip, "le tooltip doit dire que rien n'est interroge sur la machine"


def test_un_changement_d_etat_a_chaud_repose_la_propriete_qss(banner: RepoBanner) -> None:
    """set_property fait le un/polish : sans lui la couleur ne suivrait qu'au prochain clic."""
    repo = banner._repo
    derniere = repo.latest
    assert derniere is not None
    repo.local_version = derniere.tag
    banner.refresh()
    settle(banner)
    assert repo.status is Status.UP_TO_DATE
    assert banner.property("status") == STATUS_TOKEN[Status.UP_TO_DATE]
    etiquette = must_find(banner, BANNER_ROLES, "etat")
    assert etiquette.property("status") == STATUS_TOKEN[Status.UP_TO_DATE]


# ------------------------------------------------------------------ repli du bandeau


def test_bandeau_replie_ne_garde_que_la_ligne_de_tete(window: MainWindow) -> None:
    with ui_state(window, collapsed=True):
        for bann in (banner_of(window, repo) for repo in window.state.repos):
            for role in HEAD_ROLES:
                widget = must_find(bann, BANNER_ROLES, role)
                assert widget.isVisibleTo(bann), f"replie : le role {role!r} a disparu de la ligne de tete"
            for role in DETAIL_ROLES:
                widget = must_find(bann, BANNER_ROLES, role)
                assert not widget.isVisibleTo(bann), f"replie : le role {role!r} devrait etre masque"
            for ligne in bann.detail_rows():
                assert not ligne.isVisibleTo(bann), f"replie : la ligne {ligne.objectName()} est encore visible"


def test_bandeau_deplie_affiche_les_lignes_de_reglages(window: MainWindow) -> None:
    with ui_state(window, collapsed=False):
        bann = banner_of(window, window.state.repos[0])
        for ligne in bann.detail_rows():
            assert ligne.isVisibleTo(bann), f"deplie : la ligne {ligne.objectName()} est masquee"


def test_double_clic_sur_le_titre_plie_le_bandeau(banner: RepoBanner) -> None:
    titre = must_find(banner, BANNER_ROLES, "titre")
    position = titre.mapTo(banner, QPointF(2, 2))
    evenement = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    avant = banner._repo.collapsed
    QApplication.sendEvent(banner.head_row, evenement)
    settle(banner)
    assert banner._repo.collapsed is not avant, "le double-clic sur une zone neutre ne plie plus"


# ------------------------------------------------------------------ recueil des assets


def test_assets_desactives_masquent_les_reglages_mais_pas_la_case(window: MainWindow) -> None:
    with ui_state(window, collapsed=False, assets=False):
        bann = banner_of(window, window.state.repos[0])
        for role in ASSET_CONTROL_ROLES:
            widget = must_find(bann, BANNER_ROLES, role)
            assert not widget.isVisibleTo(bann), f"assets decoches : le role {role!r} est encore visible"
        for role in ASSET_KEPT_ROLES:
            widget = must_find(bann, BANNER_ROLES, role)
            assert widget.isVisibleTo(bann), f"assets decoches : le role {role!r} doit rester visible"
        resume = role_of(bann, BANNER_ROLES, "resume_assets", QLabel)
        assert resume.text(), "le resume non-asset (fetch, scripts, exclusion) est reste vide"


def test_assets_desactives_vident_les_assets_de_la_base(window: MainWindow) -> None:
    repo = window.state.repos[0]
    assert repo.releases[0].assets, "l'echantillon doit partir avec des assets"
    with ui_state(window, collapsed=False, assets=False):
        assert repo.assets_enabled is False
        assert all(liquid.assets == [] for liquid in repo.releases), "des assets sont restes en base"


# ------------------------------------------------------------------ colonnes de versions


def test_colonnes_de_versions_collees_aux_modeles(window: MainWindow) -> None:
    for repo in window.state.repos:
        bann = banner_of(window, repo)
        gauche = [liquid.version.full_text() for liquid in bann.rows_by_side()["left"]]
        droite = [liquid.version.full_text() for liquid in bann.rows_by_side()["right"]]
        attendu_gauche = [liquid.tag for liquid in repo.matching_releases]
        attendu_droite = [liquid.tag for liquid in repo.rejected_releases]
        assert gauche == attendu_gauche, f"{repo.id} : colonne retenues != modele"
        assert droite == attendu_droite, f"{repo.id} : colonne rejetees != modele"


def test_une_colonne_masquee_laisse_l_autre_affichee(window: MainWindow) -> None:
    repo = window.state.repos[0]
    with ui_state(window, collapsed=False, hidden_column="right"):
        bann = banner_of(window, repo)
        assert repo.column_right_collapsed is True
        corps = bann.column_bodies()
        assert not corps["right"].isVisibleTo(bann), "la colonne rejetees est encore affichee"
        assert corps["left"].isVisibleTo(bann), "la colonne retenues a disparu avec sa voisine"
        bouton = role_of(bann, BANNER_ROLES, "colonne_rejetees", QAbstractButton)
        assert not bouton.isChecked(), "le bouton de colonne ne refletait pas l'etat masque"


@pytest.mark.parametrize(("largeur", "empile"), [(TWO_COLUMNS_MIN + 240, False), (TWO_COLUMNS_MIN - 60, True)])
def test_les_colonnes_s_empilent_sous_la_largeur_seuil(banner: RepoBanner, largeur: int, empile: bool) -> None:
    # Pas de settle() ici : la largeur forcee serait annulee par le layout parent. Le seuil
    # se lit sur la largeur courante du bandeau, comme le fait resizeEvent() a l'ecran.
    banner.resize(largeur, banner.height())
    banner.relayout_release_rows()
    assert banner.columns_stacked() is empile, f"largeur {largeur} : empilement attendu {empile}"


def test_plus_de_legende_au_dessus_des_colonnes(banner: RepoBanner) -> None:
    """Les colonnes n'ont plus de tete : tout se pilote depuis la ligne de filtres."""
    for nom in ("colCaption", "colToggleLeft", "colToggleRight", "tagCompact"):
        assert banner.findChild(QLabel, nom) is None, f"l'ancien widget {nom} est revenu"
    assert must_find(banner, BANNER_ROLES, "colonne_retenues") is not None


# ------------------------------------------------------------------ lignes de version


def test_pre_release_en_italique(banner: RepoBanner) -> None:
    versions = {liquid.version.full_text(): liquid for rows in banner.rows_by_side().values() for liquid in rows}
    ligne = versions.get("v6.8.1")
    assert ligne is not None, "la pre-release v6.8.1 a disparu des lignes"
    assert ligne.version.font().italic(), "la pre-release n'est plus en italique"


def test_categories_de_lignes(banner: RepoBanner) -> None:
    rencontre = {str(liquid.property("kind") or "") for rows in banner.rows_by_side().values() for liquid in rows}
    attendues = {KIND_LATEST, KIND_STALE, KIND_OTHER, KIND_LOCAL}
    assert attendues.issubset(rencontre), f"categories jamais rencontrees : {sorted(attendues - rencontre)}"


def test_la_version_locale_designee_sur_la_derniere_change_la_categorie(banner: RepoBanner) -> None:
    repo = banner._repo
    derniere = repo.latest
    assert derniere is not None
    repo.local_version = derniere.tag
    banner.refresh()
    settle(banner)
    rencontre = {str(liquid.property("kind") or "") for rows in banner.rows_by_side().values() for liquid in rows}
    assert KIND_LATEST_LOCAL in rencontre, "la ligne de la version locale designee n'est pas marquee courante"


# ------------------------------------------------------------------ ordre et exclusion


def test_reorganisation_deplace_le_modele_et_le_widget(window: MainWindow) -> None:
    ids = [repo.id for repo in window.state.repos]
    deplace = ids[-1]
    window._reorder_repo(deplace, 0)
    settle(window)
    assert [repo.id for repo in window.state.repos] == [deplace, *ids[:-1]]
    positions = [window._host_layout.indexOf(banner_of(window, repo)) for repo in window.state.repos]
    assert positions == sorted(positions), "l'ordre des bandeaux a l'ecran ne suit plus l'ordre enregistre"


def test_exclusion_du_controle_global(window: MainWindow) -> None:
    cibles = {repo.id for repo in window._check_targets()}
    exclus = [repo for repo in window.state.repos if repo.excluded_check_all]
    assert exclus, "l'echantillon ne contient aucun repo exclu : le controle ne prouve rien"
    for repo in window.state.repos:
        if repo.excluded_check_all:
            assert repo.id not in cibles, f"{repo.id} exclu mais encore cible par le controle global"
        else:
            assert repo.id in cibles, f"{repo.id} inclus mais absent du controle global"
    for repo in exclus:
        bouton = role_of(banner_of(window, repo), BANNER_ROLES, "exclusion_globale", QAbstractButton)
        assert bouton.isChecked(), f"{repo.id} : le bouton d'exclusion ne refletait pas l'exclusion"


# ------------------------------------------------------------------ barre d'etat


def test_le_message_de_la_barre_d_etat_tient_dans_sa_propre_etiquette(window: MainWindow) -> None:
    fenetre = window
    fenetre._say("Trois récupérations en cours", Status.UNKNOWN)
    settle(fenetre)
    etiquette = must_find(fenetre, WINDOW_ROLES, "message_etat")
    assert isinstance(etiquette, ElidedLabel), "la barre d'etat n'utilise plus une etiquette elidable"
    assert etiquette.full_text() == "Trois récupérations en cours"
    assert etiquette.toolTip() == "Trois récupérations en cours", "le texte complet a quitte le tooltip"
    assert fenetre.bar.currentMessage() == "", "un message temporaire s'imposerait en largeur"
    bouton = role_of(fenetre, WINDOW_ROLES, "effacer_message", QAbstractButton)
    assert bouton.isVisibleTo(fenetre), "le bouton d'effacement doit accompagner un message"
    bouton.click()
    settle(fenetre)
    assert etiquette.full_text() == ""
    assert not bouton.isVisibleTo(fenetre), "le bouton d'effacement reste visible sans message"


# ------------------------------------------------------------------ theme


def test_aucun_token_qss_non_resolu() -> None:
    rendu = theme.render()
    restants = [ligne.strip() for ligne in rendu.splitlines() if "$" in ligne]
    assert not restants, f"tokens non resolus dans la feuille appliquee : {restants}"


def test_un_theme_recharge_ne_casse_pas_le_placeholder_italique(window: MainWindow) -> None:
    """Un re-polish reecrit la police depuis la regle QWidget : l'italique doit etre repose."""
    theme.repolish_tree(window)
    settle(window)
    champs = [champ for champ in window.findChildren(GhostLineEdit)]
    assert champs, "aucun champ a placeholder dans la fenetre"
    for champ in champs:
        if champ.text():
            continue
        assert champ.font().italic(), f"placeholder non italique apres re-polish : #{champ.objectName()}"
        champ.setText("saisie")
        assert not champ.font().italic(), f"la saisie est italique : #{champ.objectName()}"
        champ.setText("")


# ------------------------------------------------------------------ panneau de notes


def test_aucune_puce_sans_release_affichee(window: MainWindow) -> None:
    notes = window.notes
    for role in ("puce_date", "puce_source", "puce_prepublication"):
        for puce in [p for p in notes.findChildren(QLabel) if p.objectName() == NOTES_ROLES[role]]:
            assert not puce.isVisibleTo(notes), f"la puce {role} est visible sans release"


def test_sections_assets_et_contributeurs(window: MainWindow) -> None:
    repo = window.state.repos[0]
    release = repo.releases[0]
    window.notes.show_release(repo.title, release)
    settle(window)
    bouton_assets = role_of(window.notes, NOTES_ROLES, "section_assets", QAbstractButton)
    bouton_contributeurs = role_of(window.notes, NOTES_ROLES, "section_contributeurs", QAbstractButton)
    assert str(release.assets.__len__()) in bouton_assets.text(), (
        f"libelle de la section assets : {bouton_assets.text()}"
    )
    assert bouton_contributeurs.isEnabled(), "la section contributeurs est grelottee alors qu'il y en a"
    bouton_contributeurs.click()
    settle(window)
    assert bouton_contributeurs.isChecked()


def test_la_taille_de_police_des_notes_reste_sur_les_crans(window: MainWindow) -> None:
    crans = theme.font_size_steps()
    for valeur in (1, 999, crans[0], crans[-1], crans[-1] + 3):
        applique = window.notes.apply_font_size(valeur)
        assert applique in crans, f"taille {valeur} -> {applique}, hors crans de la palette"
    assert window.notes.font_size() in crans


# ------------------------------------------------- telechargements, exclus et segments


def test_le_bouton_dossier_n_apparait_qu_une_fois_un_fichier_ecrit(window: MainWindow) -> None:
    """Le 📂 est la preuve qu'un fichier est sorti : une ligne sans ecrit ne doit rien proposer.

    Les lignes sont lues APRES chaque refresh() : refresh() detruit et recree les ReleaseRow,
    une liste gardee par-devers lui pointerait sur des objets C++ deja supprimes.
    """
    repo = next(r for r in window.state.repos if r.id == "pyside/pyside6")
    banner = banner_of(window, repo)

    def lignes() -> list[QWidget]:
        return [liquid for rows in banner.rows_by_side().values() for liquid in rows]

    def visibles() -> list[QWidget]:
        return [liquid for liquid in lignes() if role_of(liquid, ROW_ROLES, "dossier", QPushButton).isVisibleTo(window)]

    souvenir = dict(repo.downloads)
    assert visibles() == [lignes()[0]], "l'echantillon a un seul telechargement, sur la premiere ligne retenue"
    try:
        repo.downloads.clear()
        banner.refresh()
        settle(window)
        assert visibles() == [], "un dossier sans fichier ecrit ne doit rien proposer"
        repo.downloads.update(souvenir)
        banner.refresh()
        settle(window)
        assert visibles() == [lignes()[0]], "le fichier ecrit doit rendre le bouton accessible"
    finally:
        repo.downloads.clear()
        repo.downloads.update(souvenir)
        banner.refresh()
        settle(window)


def test_le_verifier_des_exclus_ne_vise_que_les_exclus(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    """⊘ de la barre d'outils : memes regles de passe que le controle global, cible inversee."""
    exclus = {repo.id for repo in window.state.repos if repo.excluded_check_all}
    inclus = {repo.id for repo in window.state.repos if not repo.excluded_check_all}
    assert exclus and inclus, "l'echantillon doit contenir des bandeaux des deux cotes"
    lances: list[list[str]] = []
    monkeypatch.setattr(window, "_run_pass", lambda cibles, notice: lances.append([r.id for r in cibles]))
    bouton = role_of(window, WINDOW_ROLES, "verifier_exclus", QAbstractButton)
    assert bouton.toolTip(), "un bouton de barre d'outils sans explication est une regression"
    bouton.click()
    settle(window)
    assert lances == [sorted(exclus)], f"la passe doit viser exactement les exclus {exclus}"
    assert inclus.isdisjoint(lances[0]), "un repo inclus ne doit pas passer par cette passe"


def test_les_paires_de_boutons_partagent_la_meme_boite(window: MainWindow) -> None:
    """Fetch/⊘ et Script/🛠 sont des segments : un seul parent, une seule hauteur, un seul cadre."""
    for repo in window.state.repos:
        banner = banner_of(window, repo)
        for role_groupe, roles in (
            ("groupe_fetch", ("fetch", "exclusion_globale")),
            ("groupe_script", ("script", "reglage_scripts")),
        ):
            groupe = role_of(banner, BANNER_ROLES, role_groupe, QWidget)
            membres: list[QAbstractButton] = []
            for role in roles:
                membre = role_of(banner, BANNER_ROLES, role, QAbstractButton)
                assert membre.parentWidget() is groupe, f"{role} n'est pas enfant de {role_groupe}"
                membres.append(membre)
            hauteurs = {membre.height() for membre in membres}
            assert len(hauteurs) == 1, f"{role_groupe} : les deux boutons n'ont pas la meme hauteur"
            assert groupe.isVisibleTo(window), f"{role_groupe} doit rester visible quand le bandeau est replie"


# ------------------------------------------------------------------ identite


def test_identite_de_la_fenetre(window: MainWindow) -> None:
    assert window.windowTitle() == about.window_title()
    assert not window.windowIcon().isNull(), "la fenetre n'a plus d'icone"


def test_la_version_affichee_est_celle_du_projet() -> None:
    """L'ecran et `pyproject.toml` portent le meme numero : une release ne peut plus mentir.

    Le numero n'est recopie en dur dans AUCUN test (un test qui connait le numero oblige a
    modifier les tests a chaque release). Le bump se fait dans `app/about.py` ET
    `pyproject.toml`, et ce controle est le seul garde-fou qui dit laquelle des deux lignes
    a ete oubliee.
    """
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as descripteur:
        declaree = str(tomllib.load(descripteur)["project"]["version"])
    assert about.APP_VERSION == declaree, f"app/about.py annonce {about.APP_VERSION}, pyproject.toml annonce {declaree}"
