"""Le seul contrat entre les tests et l'interface : role parlant -> objectName.

Les objectName sont deja charges par le projet (selecteurs QSS, findChild()). Ce fichier
en est l'inventaire : quand un widget est renomme, deplace ou re-parente, une seule
ligne change ici, et les tests continuent de lire le meme role.

Un role absent du bandeau est une regression : test_manifeste_bandeau la signale, comme
theme.render() signale un token QSS absent de la palette.
"""

from __future__ import annotations

from collections.abc import Mapping

# Un bandeau de repo. Les roles 'ligne_*' vivent sur les lignes de version, donc dans
# le sous-arbre du bandeau.
BANNER_ROLES: Mapping[str, str] = {
    "chevron": "bannerToggle",
    "poignee": "btnDragOrder",
    "etat": "bannerStatus",
    "titre": "bannerTitle",
    "version_locale": "lblLocalVersion",
    "fetch": "btnFetch",
    "exclusion_globale": "btnExcludeCheckAll",
    "groupe_fetch": "grpFetch",
    "script": "btnLaunch",
    "reglage_scripts": "btnPickScript",
    "groupe_script": "grpScript",
    "github": "btnOpenGithub",
    "plus": "btnMore",
    "combo_versions": "cmbMaxVersions",
    "combo_rejetees": "cmbMaxRejectedVersions",
    "motif_tags": "editTagPattern",
    "exclusion_tags": "editTagExclude",
    "colonne_retenues": "btnColLeft",
    "colonne_rejetees": "btnColRight",
    "case_assets": "chkAssets",
    "filtre_assets": "editAssetInclude",
    "exclusion_assets": "editAssetExclude",
    "combo_asset": "cmbDefaultAsset",
    "resume_assets": "lblAssetInfo",
    "infos_bandeau": "lblHint",
    "dossier_telechargement": "btnDownloadDir",
    "ligne_version": "rowVersion",
    "ligne_meta": "rowMeta",
    "ligne_asset": "btnAsset",
    "ligne_dossier": "btnOpenFolder",
    "ligne_locale": "btnValidate",
}

# Une ligne de version seule.
ROW_ROLES: Mapping[str, str] = {
    "version": "rowVersion",
    "meta": "rowMeta",
    "asset": "btnAsset",
    "dossier": "btnOpenFolder",
    "locale": "btnValidate",
}

# La fenetre.
WINDOW_ROLES: Mapping[str, str] = {
    "barre_actions": "mainToolBar",
    "verifier_tous": "btnCheckAll",
    "verifier_exclus": "btnCheckExcluded",
    "logo": "toolLogo",
    "compteur_repos": "lblRepoCount",
    "zone_bandeaux": "bannersHost",
    "barre_insertion": "dragInsertBar",
    "barre_etat": "statusBar",
    "message_etat": "statusLabel",
    "effacer_message": "btnClearStatus",
    "progression": "progressAll",
    "selecteur_langue": "btnLanguage",
    "titre_fenetre": "mainWindow",
}

# Le panneau de notes.
NOTES_ROLES: Mapping[str, str] = {
    "titre": "lblNotesTitle",
    "corps": "txtNotes",
    "section_assets": "secAssetsToggle",
    "section_contributeurs": "secContribToggle",
    "puce_date": "chipNotes",
    "puce_source": "chipNotesSource",
    "puce_prepublication": "chipNotesPre",
    "flotter": "btnDockNotesFloat",
    "fermer": "btnDockNotesClose",
}

# Les trois dialogues.
ADD_REPO_ROLES: Mapping[str, str] = {
    "url": "editRepoUrl",
    "valider": "btnValidateRepo",
    "titre": "editRepoTitle",
    "erreur": "dlgError",
    "annuler": "btnCancel",
    "ok": "btnOk",
}
SCRIPTS_ROLES: Mapping[str, str] = {
    "ligne_chemin": "editScriptPath",
    "ligne_etiquette": "editScriptLabel",
    "ligne_dossier": "editScriptCwd",
    "ajouter_ligne": "btnAddScriptRow",
    "erreur": "dlgError",
    "annuler": "btnCancel",
    "ok": "btnOk",
}
SETTINGS_ROLES: Mapping[str, str] = {
    "max_versions": "cmbDefaultMaxVersions",
    "dossier_telechargement": "editDownloadDir",
    "annuler": "btnCancel",
    "ok": "btnOk",
}

# Le dialogue de saisie d'un titre ou d'une version locale.
INPUT_ROLES: Mapping[str, str] = {
    "champ": "editInputValue",
    "annuler": "btnCancel",
    "ok": "btnOk",
}

# Ce qui doit rester visible quand le bandeau est replie sur une seule ligne.
HEAD_ROLES: tuple[str, ...] = (
    "chevron",
    "poignee",
    "etat",
    "titre",
    "version_locale",
    "fetch",
    "exclusion_globale",
    "groupe_fetch",
    "script",
    "reglage_scripts",
    "groupe_script",
    "github",
    "plus",
)

# Ce qui disparait quand le bandeau est replie.
DETAIL_ROLES: tuple[str, ...] = (
    "combo_versions",
    "combo_rejetees",
    "motif_tags",
    "exclusion_tags",
    "colonne_retenues",
    "colonne_rejetees",
    "case_assets",
    "filtre_assets",
    "exclusion_assets",
    "combo_asset",
    "infos_bandeau",
    "dossier_telechargement",
)

# Reglages de recueil des assets : masques quand la case 'assets' est decochee.
ASSET_CONTROL_ROLES: tuple[str, ...] = (
    "filtre_assets",
    "exclusion_assets",
    "combo_asset",
    "infos_bandeau",
)

# Doivent rester visibles malgre le recueil des assets desactive.
ASSET_KEPT_ROLES: tuple[str, ...] = ("case_assets", "resume_assets")
