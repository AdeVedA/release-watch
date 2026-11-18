"""Table anglaise. Clé = le texte français tel qu'il est écrit dans le widget.

Remplie au fil de la conversion ; une clé manquante retombe sur le français.
Le test `tests/test_rules.py::test_table_anglaise_est_complete` échoue dès qu'une
clé utilisée dans le code est absente d'ici.
"""

from __future__ import annotations

EN: dict[str, str] = {
    # ---- app/filters.py : erreurs de motif, affichees dans le bandeau ----
    "trop de motifs ({count}), maximum {limit}": "too many patterns ({count}), maximum {limit}",
    "motif trop long ({length} caractères), maximum {limit}": (
        "pattern too long ({length} characters), maximum {limit}"
    ),
    "'re:' suivi d'une regex attendue": "'re:' must be followed by a regex",
    "regex invalide '{pattern}' : {exc}": "invalid regex '{pattern}': {exc}",
    # ---- app/models.py : libelles d'etat (infobulle du point colore) ----
    "À JOUR": "UP TO DATE",
    "NOUVELLE VERSION": "NEW VERSION",
    "HORS RELEASE": "AHEAD OF RELEASE",
    "VERSION LOCALE À DÉFINIR": "LOCAL VERSION TO SET",
    "ERREUR FETCH": "FETCH ERROR",
    "(sans nom)": "(unnamed)",
    # ---- app/github.py : erreurs reseau, affichees dans le bandeau ou la barre ----
    "Nom de repo invalide.": "Invalid repo name.",
    "Nom de repo trop long.": "Repo name too long.",
    "Adresse invalide. Formes acceptées : https://github.com/owner/repo, "
    "git@github.com:owner/repo.git, ou owner/repo.": (
        "Invalid address. Accepted forms: https://github.com/owner/repo, git@github.com:owner/repo.git, or owner/repo."
    ),
    "URL non HTTPS refusée : {url}": "Non-HTTPS URL refused: {url}",
    "Redirection sans destination depuis : {url}": "Redirection with no destination from: {url}",
    "Redirection vers un hôte hors liste blanche refusée : {url}": (
        "Refused redirection to a host outside the allowlist: {url}"
    ),
    "Réponse GitHub inattendue : une liste était attendue.": ("Unexpected GitHub response: a list was expected."),
    "Réponse GitHub inattendue : un objet était attendu.": ("Unexpected GitHub response: an object was expected."),
    "Repo introuvable, orthographe à vérifier, ou repo privé.": (
        "Repo not found: check the spelling, or the repo is private."
    ),
    "Quota anonyme GitHub atteint (60 requêtes/heure). Attendre environ {wait} min.": (
        "GitHub anonymous quota reached (60 requests/hour). Wait about {wait} min."
    ),
    "Accès refusé par GitHub (403) : {detail}": "Access denied by GitHub (403): {detail}",
    "GitHub a répondu {code} pour {url}": "GitHub replied {code} for {url}",
    "Requête impossible vers {url} : {exc}": "Request failed for {url}: {exc}",
    "Seul {host} est interrogé par l'application : {url}": "The app only queries {host}: {url}",
    "Trop de redirections consécutives pour {url}": "Too many consecutive redirections for {url}",
    "Redirection hors {host} refusée : {url}": "Refused redirection outside {host}: {url}",
    "Hôte de téléchargement hors liste blanche : {url}": "Download host outside the allowlist: {url}",
    "Dossier de téléchargement inaccessible {folder} : {exc}": ("Inaccessible download folder {folder}: {exc}"),
    "Trop de redirections pour télécharger {name}": "Too many redirections while downloading {name}",
    "Redirection de téléchargement refusée vers {url}": "Refused download redirection to {url}",
    "Téléchargement refusé ({code}) : {url}": "Download refused ({code}): {url}",
    "Téléchargement interrompu : {exc}": "Download interrupted: {exc}",
    "Échec d'écriture de {file} : {exc}": "Failed to write {file}: {exc}",
    "Nom de fichier indisponible après 999 essais : {name}": ("File name unavailable after 999 tries: {name}"),
    # ---- app/scripts.py : erreurs du lanceur de scripts ----
    "{name} · dossier {folder}": "{name} · folder {folder}",
    "Chemin de script refusé (caractères interprétés par l'interpréteur : {chars}) : {path}": (
        "Refused script path (characters interpreted by the shell: {chars}): {path}"
    ),
    "Extension non prise en charge : {suffix}. Supportées : {supported}.": (
        "Unsupported extension: {suffix}. Supported: {supported}."
    ),
    "(aucune)": "(none)",
    "Aucun chemin de script renseigné.": "No script path given.",
    "Chemin de script relatif refusé : {path}. Re-sélectionne le script avec le bouton "
    "pour mémoriser un chemin absolu.": (
        "Refused relative script path: {path}. Pick the script again with the button to store an absolute path."
    ),
    "Chemin de script illisible : {path} ({exc})": "Unreadable script path: {path} ({exc})",
    "Script introuvable : {path}": "Script not found: {path}",
    "Dossier de travail relatif refusé : {path}. Donne un dossier absolu, ou laisse vide "
    "pour utiliser le dossier du script.": (
        "Refused relative working folder: {path}. Give an absolute folder, or leave it empty to use the script folder."
    ),
    "Dossier de travail illisible : {path} ({exc})": "Unreadable working folder: {path} ({exc})",
    "Dossier de travail introuvable : {path}": "Working folder not found: {path}",
    "Lancement impossible de {script} : {exc}": "Cannot launch {script}: {exc}",
    "Interprète de shebang refusé (chemin absolu attendu) : {shebang}": (
        "Refused shebang interpreter (absolute path expected): {shebang}"
    ),
    "Script illisible : {path} ({exc})": "Unreadable script: {path} ({exc})",
    "Interprète annoncé par le script introuvable : {interpreter} ({path})": (
        "Interpreter announced by the script is missing: {interpreter} ({path})"
    ),
    "Terminal indiqué par {variable} introuvable : {wanted}": ("Terminal named by {variable} is missing: {wanted}"),
    "Journal de lancement inaccessible : {folder} ({exc})": ("Launch log folder unreachable: {folder} ({exc})"),
    # ---- app/theme.py : erreurs de feuille de style, dialogue de demarrage ----
    "Feuille de style introuvable : {path}": "Stylesheet not found: {path}",
    "Tokens de palette absents pour {file} : {missing} (éditer {module}.py)": (
        "Missing palette tokens for {file}: {missing} (edit {module}.py)"
    ),
    "Aucun token de taille {prefix}N dans la palette": "No size token {prefix}N in the palette",
    "Token de dimension absent de la palette : {name}": "Size token missing from the palette: {name}",
    "Token non exprimé en pixels : {name}={value}": "Token not expressed in pixels: {name}={value}",
    "Token de dimension invalide : {name}={value}": "Invalid size token: {name}={value}",
    # ---- app/store.py : etat persiste illisible ou non ecrivable ----
    "{path} : JSON invalide ({exc})": "{path}: invalid JSON ({exc})",
    "Impossible de lire {path} : {exc}": "Cannot read {path}: {exc}",
    "{path} : racine JSON attendue, obtenu {found}": "{path}: expected a JSON object, got {found}",
    "Impossible d'écrire {path} : {exc}": "Cannot write {path}: {exc}",
    # ---- app/about.py + main.py : titre et dialogues de demarrage ----
    "moniteur de releases GitHub": "GitHub releases monitor",
    "Thème": "Theme",
    "État illisible": "Unreadable state",
    "{error}\n\nCorrige ou supprime le fichier, puis relance.": ("{error}\n\nFix or delete the file, then relaunch."),
    # ---- app/widgets/release_row.py : ligne de version (meta, infobulle, boutons) ----
    "Dernière version autorisée par le filtre du bandeau": "Latest version allowed by the banner filter",
    "Dernière version autorisée, et version désignée comme installée": (
        "Latest allowed version, and version set as installed"
    ),
    "Version désignée comme installée, pas la dernière autorisée": (
        "Version set as installed, not the latest allowed one"
    ),
    "Autorisée par le filtre mais au-delà du cap de versions affichées": (
        "Allowed by the filter but past the cap of shown versions"
    ),
    "Refusée par le motif ou l'exclusion : jamais comparée à ta version locale": (
        "Refused by the pattern or the exclusion: never compared to your local version"
    ),
    "Version autorisée par le filtre, intermédiaire": "Version allowed by the filter, in between",
    "Clic : description dans le panneau latéral.": "Click: description in the side panel.",
    "Flèches haut/bas : naviguer entre les versions.": "Up/down arrows: move between versions.",
    "pre-release (nom en italique)": "pre-release (name in italics)",
    "Source : tag GitHub, pas une release avec notes.": "Source: GitHub tag, not a release with notes.",
    "ses notes et ses assets": "its notes and its assets",
    "ses notes": "its notes",
    "Ce tag ne suit pas le filtre de tag du bandeau : il reste affiché,\n"
    "{notes} restent accessibles, mais il n'est jamais\n"
    "comparé à ta version locale (sauf si tu le désignes comme version locale).": (
        "This tag does not follow the banner tag filter: it is still shown,\n"
        "{notes} stay reachable, but it is never\n"
        "compared to your local version (unless you set it as the local version)."
    ),
    "✓ locale": "✓ local",
    "locale": "local",
    "Cette version est déjà désignée comme installée localement": ("This version is already set as installed locally"),
    "Désigner cette version comme installée localement": "Set this version as installed locally",
    "Recueil des assets désactivé": "Asset collection disabled",
    "Aucun asset pour cette version": "No asset for this version",
    "Télécharger {name}": "Download {name}",
    "Choisir un asset : {names}": "Pick an asset: {names}",
    "Fichiers déjà écrits pour cette version :": "Files already written for this version:",
    "Clique : ouvre le dossier de « {name} ».": "Click: opens the folder of “{name}”.",
    "Aucun fichier encore écrit pour cette version": "No file written yet for this version",
    # ---- app/widgets/notes_dock.py : panneau lateral des notes ----
    "taille inconnue": "unknown size",
    "{n} octet": "{n} byte",
    "{n} octets": "{n} bytes",
    "octets": "bytes",
    "Notes de release": "Release notes",
    "Assets": "Assets",
    "Liste des assets conservés pour cette version (ceux passés par le filtre du bandeau).": (
        "List of assets kept for this version (those that passed the banner filter)."
    ),
    "Contributeurs": "Contributors",
    "Sections de contribution récupérées dans les notes GitHub. Aucune requête supplémentaire.": (
        "Contribution sections read from the GitHub notes. No extra request."
    ),
    "Aucune version sélectionnée": "No version selected",
    "Description lue depuis la release GitHub, affichée ici en Markdown": (
        "Description read from the GitHub release, shown here in Markdown"
    ),
    "Date de publication de la release": "Release publication date",
    "Nombre d'assets conservés pour cette version": "Number of assets kept for this version",
    "Provenance des données : release GitHub ou simple tag": ("Where the data comes from: GitHub release or plain tag"),
    "Cette version est signalée pre-release par GitHub": "GitHub flags this version as a pre-release",
    "Panneau de description de la release sélectionnée": "Description panel for the selected release",
    "Détacher ou rattacher le panneau": "Detach or dock the panel",
    "Fermer le panneau de description": "Close the description panel",
    "Publiée le {date}": "Published on {date}",
    "{n} asset": "{n} asset",
    "{n} assets": "{n} assets",
    "tag sans release": "tag without release",
    "release GitHub": "GitHub release",
    "pre-release": "pre-release",
    "> Aucune description associée à ce tag.": "> No description attached to this tag.",
    "Aucun asset conservé : recueil désactivé ou tout a été filtré.": (
        "No asset kept: collection disabled or everything was filtered out."
    ),
    "(lien sans protocole)": "(link without protocol)",
    # ---- app/widgets/add_repo_dialog.py ----
    "Ajouter un repo GitHub": "Add a GitHub repo",
    "Ajouter un repo à monitorer": "Add a repo to monitor",
    "Formes acceptées : https://github.com/owner/repo, git@github.com:owner/repo.git, "
    "owner/repo. Repo public uniquement.": (
        "Accepted forms: https://github.com/owner/repo, git@github.com:owner/repo.git, owner/repo. Public repos only."
    ),
    "URL du dépôt public. Formes acceptées :\n"
    "https://github.com/owner/repo, git@github.com:owner/repo.git, owner/repo.\n"
    "Aucun identifiant : l'accès est anonyme, les repos privés sont invisibles.": (
        "URL of the public repository. Accepted forms:\n"
        "https://github.com/owner/repo, git@github.com:owner/repo.git, owner/repo.\n"
        "No credentials: access is anonymous, private repos are invisible."
    ),
    "Vérifier": "Check",
    "Vérification…": "Checking…",
    "Une seule requête anonyme vers api.github.com pour ce repo.\n"
    "Aucune connexion avant ce clic. Remplit le titre proposé et active « Ajouter ».": (
        "One anonymous request to api.github.com for this repo.\n"
        "No connection before this click. Fills the suggested title and enables “Add”."
    ),
    "Titre du bandeau": "Banner title",
    "Nom affiché sur le bandeau.\nProposé automatiquement après « Vérifier », puis modifiable.": (
        "Name shown on the banner.\nSuggested automatically after “Check”, then editable."
    ),
    "Annuler": "Cancel",
    "Ferme sans modifier.": "Closes without changing anything.",
    "Valider": "Apply",
    "Valide la saisie.": "Accepts the entry.",
    "Ferme sans rien enregistrer.": "Closes without saving anything.",
    "Ajouter": "Add",
    "Enregistre le repo dans data/state.json.\nGrisé tant que « Vérifier » n'a pas réussi.": (
        "Saves the repo in data/state.json.\nGreyed out until “Check” succeeds."
    ),
    "Ce repo est déjà dans la liste.": "This repo is already in the list.",
    "Interrogation de l'API GitHub…": "Querying the GitHub API…",
    "Réponse inattendue de l'API.": "Unexpected API response.",
    "(pas de description)": "(no description)",
    "Repo valide : {description}   ·   {stars} stars": "Valid repo: {description}   ·   {stars} stars",
    "Bouton Vérifier d'abord.": "Press Check first.",
    # ---- app/widgets/scripts_dialog.py ----
    "Scripts ({globs})": "Scripts ({globs})",
    "étiquette du script": "script label",
    "Nom affiché dans le menu du bouton « Script ».\nVide : le nom du fichier est utilisé.": (
        "Name shown in the “Script” button menu.\nEmpty: the file name is used."
    ),
    "chemin du script .bat / .cmd / .ps1": "script path .bat / .cmd / .ps1",
    "chemin du script .sh / .bash / .zsh": "script path .sh / .bash / .zsh",
    "Script lancé dans une console Windows séparée.\n"
    "Il se lance depuis SON propre dossier, comme un double-clic dans l'explorateur.": (
        "Script launched in its own Windows console.\nIt runs from ITS own folder, like a double-click in the explorer."
    ),
    "Script lancé dans un terminal séparé, fenêtre maintenue ouverte.\n"
    "Sans terminal ni session graphique, la sortie écrit un journal dans data/launches/.\n"
    "Il se lance depuis SON propre dossier, comme un double-clic dans le gestionnaire de fichiers.": (
        "Script launched in a separate terminal, kept open.\n"
        "With no terminal and no graphical session, the output writes a log in data/launches/.\n"
        "It runs from ITS own folder, like a double-click in the file manager."
    ),
    "L'environnement de l'application n'est pas hérité : ni son venv, ni son PATH.\n"
    "Le chemin doit être absolu (il est corrigé à l'enregistrement).": (
        "The app environment is not inherited: neither its venv nor its PATH.\n"
        "The path must be absolute (it is fixed on save)."
    ),
    "Choisir le script": "Pick the script",
    "dossier de travail (vide = dossier du script)": "working folder (empty = script folder)",
    "Dossier courant de la console au lancement.\n"
    "Vide : le dossier du script lui-même, ce qui est le comportement d'un double-clic.\n"
    "Un dossier inexistant est refusé au lieu d'être remplacé silencieusement.": (
        "Current folder of the console at launch.\n"
        "Empty: the script's own folder, which is what a double-click does.\n"
        "A missing folder is refused instead of silently replaced."
    ),
    "Choisir le dossier de travail": "Pick the working folder",
    "Retirer ce script": "Remove this script",
    "Script à lancer": "Script to run",
    "Dossier de travail du script": "Script working folder",
    "Scripts liés à {title}": "Scripts for {title}",
    "Scripts de {title}": "Scripts of {title}",
    "Lancés dans une console Windows séparée.": "Launched in their own Windows console.",
    "Lancés dans un terminal séparé, fenêtre maintenue ouverte ; sans terminal "
    "disponible, la sortie est écrite dans data/launches/ et son chemin est affiché à la barre d'état.": (
        "Launched in a separate terminal, kept open; with no terminal available, the output is "
        "written in data/launches/ and its path is shown in the status bar."
    ),
    "Extensions : {suffixes}. "
    "L'ordre de la liste est l'ordre du menu du bouton « Script ».\n"
    "Chaque script part de SON dossier et ne reçoit pas l'environnement de "
    "l'application (ni son venv, ni son PATH) : un « pip install » du script ne "
    "touche jamais l'application.": (
        "Extensions: {suffixes}. "
        "The list order is the order of the “Script” button menu.\n"
        "Each script starts from ITS own folder and does not get the application "
        "environment (neither its venv nor its PATH): a “pip install” from the script "
        "never touches the application."
    ),
    "Ajouter un script": "Add a script",
    "Ajoute une ligne vide. Rien n'est enregistré avant « Enregistrer ».": (
        "Adds an empty row. Nothing is saved before “Save”."
    ),
    "Ferme sans modifier la liste des scripts de ce bandeau.": ("Closes without changing this banner's script list."),
    "Enregistrer": "Save",
    "Enregistre la liste dans data/state.json.\nL'ordre des lignes devient l'ordre du menu « Script ».": (
        "Saves the list in data/state.json.\nRow order becomes the order of the “Script” menu."
    ),
    "Scripts refusés : {problems}": "Refused scripts: {problems}",
    # ---- app/widgets/settings_dialog.py ----
    "Réglages": "Settings",
    "Réglages globaux": "Global settings",
    "Nombre de versions conservées par défaut pour un nouveau bandeau, "
    "dans la colonne retenue comme dans la colonne rejetée (crans {steps}).\n"
    "Un bandeau déjà présent garde son propre réglage.\n"
    "Stockage : les deux colonnes ensemble, plafonné à {cap} lignes.": (
        "Number of versions kept by default for a new banner, in the kept column as well as "
        "the rejected column (steps {steps}).\n"
        "An existing banner keeps its own setting.\n"
        "Storage: both columns together, capped at {cap} rows."
    ),
    "Versions récupérées par défaut": "Versions fetched by default",
    "Dossier proposé à chaque téléchargement": "Folder suggested for each download",
    "Dossier proposé par le dialogue de téléchargement.\n"
    "Le dialogue s'affiche à chaque fois : rien n'est écrit sans validation.\n"
    "Vide : l'explorateur s'ouvre sur son dossier habituel.": (
        "Folder suggested by the download dialog.\n"
        "The dialog shows every time: nothing is written without confirmation.\n"
        "Empty: the explorer opens on its usual folder."
    ),
    "Parcourir": "Browse",
    "Sélecteur de dossier local. Aucune connexion, aucune écriture :\nmodifie seulement le champ à côté.": (
        "Local folder picker. No connection, no write:\nonly changes the field next to it."
    ),
    "Dossier de téléchargement par défaut": "Download folder by default",
    "Chaque bandeau peut écraser ces deux valeurs.": "Each banner can override these two values.",
    "Ferme sans enregistrer.": "Closes without saving.",
    "Enregistre les réglages globaux dans data/state.json.\n"
    "Ne relance aucun fetch : les bandeaux gardent ce qu'ils ont déjà.": (
        "Saves the global settings in data/state.json.\nStarts no fetch: banners keep what they already have."
    ),
    "Dossier de téléchargement": "Download folder",
    # ---- app/widgets/main_window.py (barre d'actions, statut, file) ----
    "+ Ajouter un repo": "+ Add a repo",
    "⟳ Vérifier les repos": "⟳ Check the repos",
    "Fetch de tous les bandeaux, sauf ceux marqués ⊘ (exclus du contrôle global)": (
        "Fetch of every banner, except those marked ⊘ (excluded from the global check)"
    ),
    "⊘ Vérifier les exclus": "⊘ Check the excluded",
    "Fetch des seuls bandeaux marqués ⊘.\n« ⟳ Vérifier les repos » les saute : c'est ici qu'on les rattrape à la main.": (
        "Fetch of the banners marked ⊘ only.\n⟳ Check the repos skips them: this is where you catch up on them."
    ),
    "Aucun repo exclu du contrôle global": "No repo is excluded from the global check",
    "Fetch des {n} repo(s) exclu(s)…": "Fetch of the {n} excluded repo(s)…",
    "⚙ Réglages": "⚙ Settings",
    "🎨Thème⟳": "🎨Theme⟳",
    "Effacer le message affiché dans la barre d'état.": "Clear the message shown in the status bar.",
    "{n} repo(s)": "{n} repo(s)",
    "{n} repo(s) chargé(s) · {path}": "{n} repo(s) loaded · {path}",
    "Persistance impossible : {error}": "Cannot save: {error}",
    "{title} : fetch déjà en cours": "{title}: fetch already running",
    "{n} repo(s) exclu(s)": "{n} repo(s) excluded",
    "liste vide ou déjà en cours": "empty list or already running",
    "Rien à vérifier ({reason})": "Nothing to check ({reason})",
    " · {n} exclu(s)": " · {n} excluded",
    "Fetch de {n} repo(s){tail}…": "Fetch of {n} repo(s){tail}…",
    "Rattrapage des dates : {n} repo(s), {m} tag(s) en attente…": (
        "Catching up dates: {n} repo(s), {m} tag(s) still waiting…"
    ),
    "{title} : {n} version(s) récupérée(s) · {kept} asset(s) conservé(s), {dropped} jeté(s) par le filtre{tail}": (
        "{title}: {n} version(s) fetched · {kept} asset(s) kept, {dropped} dropped by the filter{tail}"
    ),
    " · quota restant {n}": " · {n} requests left",
    "quota restant {n}": "{n} requests left",
    "Téléchargement annulé": "Download cancelled",
    "Téléchargement : {name} → {folder}": "Downloading: {name} → {folder}",
    "{name} : {percent}% ({done} {unit} / {total} {unit})": "{name}: {percent}% ({done} {unit} / {total} {unit})",
    "{name} : {done} {unit} reçus": "{name}: {done} {unit} received",
    "Téléchargé : {path}": "Downloaded: {path}",
    "Échec téléchargement : {error}": "Download failed: {error}",
    "Enregistrer l'asset sous": "Save the asset as",
    "Tous les fichiers (*)": "All files (*)",
    "Dossier introuvable : {folder}": "Folder not found: {folder}",
    "(vide)": "(empty)",
    "Impossible d'ouvrir le dossier : {folder}": "Cannot open the folder: {folder}",
    "Console lancée : {summary}": "Console launched: {summary}",
    "Script lancé sans fenêtre : sortie dans {log}": "Script launched with no window: output in {log}",
    "{title} : {n} script(s)": "{title}: {n} script(s)",
    "Ajouté : {title}. Bouton Fetch pour récupérer les versions.": ("Added: {title}. Press Fetch to get the versions."),
    "Supprimer le bandeau": "Remove the banner",
    "Retirer {title} de la liste ?\nLes versions mémorisées et les scripts liés seront perdus (aucun fichier supprimé).": (
        "Remove {title} from the list?\nStored versions and linked scripts will be lost (no file is deleted)."
    ),
    "Conserver": "Keep",
    "Supprimer": "Delete",
    "Supprimé : {title}": "Removed: {title}",
    "Ouvrir ce lien ?": "Open this link?",
    "Le lien cliqué provient de la description écrite par l'auteur du repo.\nRien n'a encore été ouvert.\n\n{url}": (
        "The clicked link comes from the description written by the repo author.\nNothing has been opened yet.\n\n{url}"
    ),
    "Ouvrir le lien": "Open the link",
    "Ouverture du lien annulée": "Link opening cancelled",
    "Lien non HTTPS refusé, rien n'a été ouvert : {url}": "Non-HTTPS link refused, nothing was opened: {url}",
    "Impossible d'ouvrir : {url}": "Cannot open: {url}",
    "Panneau de description : police {size}px": "Notes panel: font {size}px",
    "Réglages : {n} versions · dl {folder}": "Settings: {n} versions · dl {folder}",
    "(à chaque fois)": "(every time)",
    "Thème non rechargé : {error}": "Theme not reloaded: {error}",
    "Thème rechargé : app/palette.py + resources/dark.qss": "Theme reloaded: app/palette.py + resources/dark.qss",
    "Ctrl+Maj+P : relit palette.py et dark.qss": "Ctrl+Shift+P: re-reads palette.py and dark.qss",
    "Interface en {name}.\nClique pour tout basculer en {other}.\nChoix enregistré dans data/state.json.": (
        "Interface in {name}.\nClick to switch everything to {other}.\nChoice saved in data/state.json."
    ),
    "Interface en anglais.": "Interface in English.",
    "Interface en français.": "Interface in French.",
    # ---- app/widgets/repo_banner.py ----
    "Asset téléchargé automatiquement pour les prochaines versions": (
        "Asset downloaded automatically for the next versions"
    ),
    "Liste de motifs séparés par point-virgule.\nGlob : '*.whl' (suffixe), 'PySide6-*' (préfixe), '*py3.13*' (chaîne).\nLes caractères - _ . , sont normaux. Un motif 're:...' est une regex.\nRien n'est conservé en base si un asset ne passe pas le filtre : re-fetch après modification.": (
        "List of patterns separated by semicolons.\n"
        "Glob: '*.whl' (suffix), 'PySide6-*' (prefix), '*py3.13*' (substring).\n"
        "The characters - _ . , are normal. A 're:...' pattern is a regex.\n"
        "Nothing is stored if an asset fails the filter: re-fetch after a change."
    ),
    "Tags à rejeter, mêmes motifs que le motif retenu (point-virgule, glob ou 're:').\nUn tag rejeté passe dans la colonne de droite : il n'est jamais comparé à ta version locale.\nExemple : *-rc*;*-beta*": (
        "Tags to reject, same patterns as the kept pattern (semicolon, glob or 're:').\n"
        "A rejected tag goes to the right column: it is never compared to your local version.\n"
        "Example: *-rc*;*-beta*"
    ),
    "Forme des tags comparés à ta version locale (glob : * et ?).\nExemples : {example}, v0.*, release-??\nVide = tous les tags. Plusieurs motifs séparés par point-virgule, un motif\n're:...' est une regex. Un tag qui ne correspond pas reste affiché à droite,\npour information, mais n'est jamais comparé à ta version locale.": (
        "Shape of the tags compared to your local version (glob: * and ?).\n"
        "Examples: {example}, v0.*, release-??\n"
        "Empty = all tags. Several patterns separated by semicolons, a\n"
        "'re:...' pattern is a regex. A tag that does not match is still shown on the right,\n"
        "for information, but is never compared to your local version."
    ),
    "Glisse cette poignée sur un autre bandeau pour changer l'ordre des repos.\nLa zone d'ancrage est gardée : le drop n'agit que sur un autre bandeau.": (
        "Drag this handle onto another banner to change the repo order.\n"
        "The drop zone is kept: the drop only acts on another banner."
    ),
    "Case décochée : les assets ne sont pas conservés, ni en base ni dans les lignes.\nLa requête GitHub reste la même (les assets arrivent avec la release) : ils sont\njetés à la réception. Re-fetch après modification.\nCase décochée : les réglages à garder / sauf / par défaut et la ligne d'infos\ndisparaissent ; le fetch et les scripts remontent à côté de la case.": (
        "Unchecked: assets are not stored, neither in the file nor in the rows.\n"
        "The GitHub request stays the same (assets arrive with the release): they are\n"
        "thrown away on arrival. Re-fetch after a change.\n"
        "Unchecked: the to keep / except / default settings and the info row\n"
        "disappear; fetch and scripts move up next to the box."
    ),
    "Replier / déployer les versions": "Collapse / expand the versions",
    "Déployer les versions": "Expand the versions",
    "Replier les versions": "Collapse the versions",
    "Interroge GitHub pour ce repo uniquement (5 à 25 dernières versions).": (
        "Queries GitHub for this repo only (the last 5 to 25 versions)."
    ),
    "Inclus dans 'Vérifier tous les repos'. Clique pour l'en exclure.": (
        "Included in 'Check all repos'. Click to exclude it."
    ),
    "EXCLU de 'Vérifier tous les repos'.\nLe bouton Fetch de ce bandeau fonctionne toujours. Clique pour réinclure.": (
        "EXCLUDED from 'Check all repos'.\nThis banner's Fetch button still works. Click to include it again."
    ),
    "Inclus dans 'Vérifier tous les repos'.\nClique pour exclure ce repo du contrôle global.": (
        "Included in 'Check all repos'.\nClick to exclude this repo from the global check."
    ),
    "exclu": "excluded",
    "exclu de": "excluded from",
    "exclu de 'Vérifier tous les repos'": "excluded from 'Check all repos'",
    "inclus dans": "included in",
    "{title} : {state} 'Vérifier tous les repos'": "{title}: {state} 'Check all repos'",
    "Choisir les scripts liés à ce repo": "Pick the scripts for this repo",
    "Ouvre {url} dans le navigateur": "Opens {url} in the browser",
    "Renommer, version manuelle, source des versions, dossier, supprimer": (
        "Rename, manual version, versions source, folder, delete"
    ),
    "Source des versions": "Versions source",
    "Tags du dépôt": "Repo tags",
    "Releases GitHub": "GitHub releases",
    "tags": "tags",
    "releases": "releases",
    "source : {source}": "source: {source}",
    "Derniers tags, enrichis par la release du même nom quand elle existe.\n"
    "Choix par défaut : un repo peut taguer sans publier de release.": (
        "Latest tags, enriched by the release carrying the same name when there is one.\n"
        "Default choice: a repo can tag without publishing a release."
    ),
    "Seulement les versions publiées en release : dates et notes sont là,\n"
    "mais les tags sans release disparaissent de la liste.": (
        "Only versions published as releases: dates and notes are there,\n"
        "but tags without a release disappear from the list."
    ),
    "Source de {title} : {source}. Lance « ⟳ Vérifier » pour récupérer cette liste.": (
        "Source for {title}: {source}. Run “⟳ Check” to fetch that list."
    ),
    " · rien de changé depuis le dernier fetch": " · nothing changed since the last fetch",
    " · {n} tag(s) daté(s)": " · {n} tag(s) dated",
    " · {n} en attente dans la fenêtre": " · {n} pending in the window",
    " · {n} hors fenêtre (non daté(s))": " · {n} outside the window (undated)",
    "{n} tag(s) recensé(s)": "{n} tag(s) indexed",
    "{n} date(s) payée(s)": "{n} date(s) paid for",
    "{n} en attente dans la fenêtre": "{n} pending in the window",
    "{n} hors fenêtre (non daté(s))": "{n} outside the window (undated)",
    "Renommer le titre": "Rename the title",
    "Définir une version locale manuelle": "Set a manual local version",
    "Ouvrir la page du repo": "Open the repo page",
    "Ouvrir le dossier de téléchargement": "Open the download folder",
    "Supprimer ce repo": "Delete this repo",
    "Nombre de versions retenues à gauche (colonne comparée)": "Number of kept versions on the left (compared column)",
    "Nombre de versions rejetées ou obsolètes affichées à droite": (
        "Number of rejected or obsolete versions shown on the right"
    ),
    "↓↑ retenues": "↓↑ kept",
    "rejetées ↓↑": "rejected ↓↑",
    "à garder": "to keep",
    "sauf": "except",
    "par défaut": "default",
    "assets": "assets",
    "Recueil des assets désactivé : fetch, scripts et exclusion restent visibles.": (
        "Asset collection off: fetch, scripts and exclusion stay visible."
    ),
    "Dossier où les assets sont téléchargés pour ce repo. Clique pour le changer.": (
        "Folder where this repo's assets are downloaded. Click to change it."
    ),
    "Fetch": "Fetch",
    "Fetch…": "Fetching…",
    "Script ⤶": "Script ⤶",
    "vers. locale ?": "local version?",
    "Version que tu as désignée comme installée localement.": "The version you marked as installed locally.",
    "Le programme n'interroge jamais l'installation locale.": "The program never inspects the local install.",
    "désignée sur une release": "marked on a release",
    "saisie à la main": "typed by hand",
    "Source : {origin}.": "Source: {origin}.",
    "Comparée au tag pattern : {pattern}": "Compared to the tag pattern: {pattern}",
    "Comparée à tous les tags récupérés.": "Compared to every fetched tag.",
    "Sauf ceux exclus par : {exclude}": "Except those excluded by: {exclude}",
    "La flèche montre l'écart avec la dernière version retenue.": "The arrow shows the gap with the latest kept version.",
    "Tu peux désigner la version locale sur n'importe quelle ligne, y compris à droite.": (
        "You can mark the local version on any row, including the right column."
    ),
    "Dernière récupération, scripts raccourcis et dossier d'écriture des assets.": (
        "Last fetch, shortcut scripts and the folder where assets are written."
    ),
    "Le dossier n'est pas interrogé : l'application ne vérifie pas ce qui est installé.": (
        "The folder is never inspected: the app does not check what is installed."
    ),
    "Erreur du dernier fetch : {error}": "Error of the last fetch: {error}",
    "dernière : {tag}": "latest: {tag}",
    "motif des tags à garder : {pattern}": "tag pattern to keep: {pattern}",
    "{kept} tag(s) retenu(s) sur {total}": "{kept} tag(s) kept out of {total}",
    "tags exclus : {exclude}": "excluded tags: {exclude}",
    "version locale : {version}": "local version: {version}",
    "aucune version locale définie": "no local version set",
    "dernier fetch : {when}": "last fetch: {when}",
    "erreur fetch : {error}": "fetch error: {error}",
    "fetch {when}": "fetch {when}",
    "jamais fetché": "never fetched",
    "{n} script": "{n} script",
    "{n} scripts": "{n} scripts",
    "⤓ {folder}": "⤓ {folder}",
    "(dossier demandé à chaque téléchargement)": "(folder asked for at each download)",
    "(choisir à chaque fois)": "(choose every time)",
    "Choisi : {name}": "Chosen: {name}",
    "(tous les tags)": "(all tags)",
    "(aucun)": "(none)",
    "gauche": "left",
    "droite": "right",
    "versions retenues": "kept versions",
    "versions rejetées ou obsolètes": "rejected or obsolete versions",
    "masquée": "hidden",
    "affichée": "shown",
    "pour la faire réapparaître": "to show it again",
    "pour la masquer": "to hide it",
    "Colonne {side} — {title} : {state}.\nClique {action}.": "{title} column ({side}): {state}.\nClick {action}.",
    "Détail : comparées à ta version locale.\nMotif retenu : {pattern}\nExclus : {excluded}\nCap affiché : {cap} versions.\n{kept} tag(s) retenu(s) sur {total} récupéré(s).": (
        "Details: compared to your local version.\n"
        "Kept pattern: {pattern}\n"
        "Excluded: {excluded}\n"
        "Shown cap: {cap} versions.\n"
        "{kept} tag(s) kept out of {total} fetched."
    ),
    " · {n} non affiché(s) au-delà du cap": " · {n} hidden beyond the cap",
    "Détail : tags refusés par le motif ou l'exclusion, et tags autorisés mais\nau-delà du cap de {cap} versions retenues à gauche.\nCap affiché à droite : {rejected_cap} versions rejetées ou obsolètes.\n{shown} affiché(s){hidden_note}.\nJamais comparés à ta version locale, mais leurs notes et leurs assets restent accessibles, et tu peux y désigner la version locale.": (
        "Details: tags refused by the pattern or the exclusion, and allowed tags\n"
        "beyond the cap of {cap} versions kept on the left.\n"
        "Shown cap on the right: {rejected_cap} rejected or obsolete versions.\n"
        "{shown} shown{hidden_note}.\n"
        "Never compared to your local version, but their notes and assets stay reachable, "
        "and you can mark the local version there."
    ),
    "Aucune version récupérée. Bouton Fetch.": "No version fetched. Press Fetch.",
    "Aucun tag ne passe le filtre : rien n'est comparé à ta version locale. Corrige le motif ou vide-le.": (
        "No tag passes the filter: nothing is compared to your local version. Fix the pattern or clear it."
    ),
    "Aucun tag rejeté ni obsolète.": "No rejected or obsolete tag.",
    "Aucun script choisi : bouton 🛠 pour en désigner un": "No script chosen: use the 🛠 button to pick one",
    "Chaque script est lancé depuis son propre dossier, sans l'environnement\nde l'application (ni son venv) :": (
        "Each script runs from its own folder, without the application environment\n(neither its venv):"
    ),
    "Chaque script est lancé depuis son propre dossier, sans l'environnement\n"
    "de l'application (ni son venv), dans un terminal ou un journal de data/launches/ :": (
        "Each script runs from its own folder, without the application environment\n"
        "(neither its venv), in a terminal or a log in data/launches/:"
    ),
    "{script}  ->  refusé : {error}": "{script}  ->  refused: {error}",
    "Refusé : {error}": "Refused: {error}",
    "Lancé depuis : {cwd}\nCommande : {command}": "Run from: {cwd}\nCommand: {command}",
    "Version locale": "Local version",
    "Version installée localement pour {title} :": "Version installed locally for {title}:",
    "Titre affiché :": "Shown title:",
    "Titre vide ignoré.": "Empty title ignored.",
    "Dossier de téléchargement : {folder}": "Download folder: {folder}",
    "{title} : version locale = {tag}": "{title}: local version = {tag}",
    "{title} : version locale = {version}": "{title}: local version = {version}",
    "(effacée)": "(cleared)",
    "{title} : {n} versions comparées à gauche": "{title}: {n} versions compared on the left",
    "{title} : {n} versions rejetées à droite": "{title}: {n} versions rejected on the right",
    "motif retenu": "kept pattern",
    "tags exclus": "excluded tags",
    "assets inclure": "assets to include",
    "assets exclure": "assets to exclude",
    "tous les tags": "all tags",
    "aucun": "none",
    "{title} : {label} refusé · {error}": "{title}: {label} refused · {error}",
    "{title} : motif '{pattern}' · {n} tag(s) comparé(s)": "{title}: pattern '{pattern}' · {n} tag(s) compared",
    "{title} : exclus '{pattern}' · {n} tag(s) déplacé(s) à droite": (
        "{title}: excluded '{pattern}' · {n} tag(s) moved to the right"
    ),
    "activé": "on",
    "désactivé": "off",
    "{title} : assets · recueil {state}": "{title}: assets · collection {state}",
    " · asset par défaut hors liste, à rechoisir": " · default asset out of the list, choose it again",
    "{title} : {kept} asset(s) conservé(s), {dropped} jeté(s){note}": (
        "{title}: {kept} asset(s) kept, {dropped} thrown away{note}"
    ),
    "Asset par défaut : {name}": "Default asset: {name}",
    "Les deux colonnes de versions sont masquées. Clique sur le bouton 'retenues' ou 'rejetées' pour les faire réapparaître.": (
        "Both version columns are hidden. Click the 'kept' or 'rejected' button to show them again."
    ),
}
