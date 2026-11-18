# Contribuer

Ce dépôt est petit et volontairement strict. Les règles décrites ci-dessous ne relèvent d'aucune
préférence personnelle : chacune correspond soit à une dégradation constatée, soit à une obligation
légale. Leur absence se paie en silence — une interface qui se dégrade sans que personne ne s'en
aperçoive, ou un livrable publié qui n'est pas le code qui a été vérifié.

## Outils, et pourquoi leurs numéros sont écrits en dur

Trois outils vérifient le dépôt. Leurs numéros de version sont figés dans le bloc `env:` de
`.github/workflows/ci.yml` :

| Outil  | Ce qu'il contrôle                            | Numéro figé sous |
| ------ | -------------------------------------------- | ---------------- |
| `uv`   | installe exactement ce que déclare `uv.lock` | `UV_VERSION`     |
| `ruff` | lint (règles) et découpage du texte          | `RUFF_VERSION`   |
| `ty`   | contrôle des types                           | `TY_VERSION`     |

Un outil dont la version n'est pas figée peut faire rougir la CI sans le moindre changement dans ce
dépôt : c'est exactement ce que ces trois numéros empêchent.

`uv` est à la fois gestionnaire d'environnement et de paquets. `uvx <outil>` est son raccourci pour
**exécuter** un outil sans l'installer dans le projet : l'outil est téléchargé dans un environnement
temporaire, utilisé, puis jeté. Rien n'entre dans `pyproject.toml` ni dans `uv.lock`. Écrire
`uvx ruff@<numéro> check .` revient donc à exécuter la version précise de ruff que la CI exécute —
d'où le `uvx` dans les commandes plus bas.

## Lancer les contrôles

Les numéros à recopier dans les trois commandes `uvx` sont ceux du bloc `env:` de
`.github/workflows/ci.yml` :

```bash
uv sync                              # dépendances exactes, telles que figées dans uv.lock
uv run python main.py                # l'application
uv run pytest                        # la suite (interface pilotée hors écran, aucun appel réseau)
uvx ruff@<numéro> check .            # lint
uvx ruff@<numéro> format --check .   # découpage du texte
uvx ty@<numéro> check .              # types
uv run python tools/audit_net.py     # audit zéro-confiance du code réseau
```

Ces cinq contrôles sont relancés en CI, sur **Windows et Linux en parallèle**.

Deux points à connaître avant de toucher au style :

- **Les règles de ruff sont versionnées avec le dépôt** (`ruff.toml` à la racine) : largeur de ligne de
  120 caractères, règles `E, W, F, I, N, UP, B`, `E501` ignorée — c'est le formateur qui décide du
  découpage, pas le linter. Un `ruff check` lancé avec les réglages d'usine n'est pas le même contrôle :
  il ne vérifie ni le tri des imports, ni le nommage, ni les nids à bugs.
- **`ruff format --check` passe en CI.** Sans mise en forme préalable, la construction est rouge. La mise
  en forme s'obtient avec `uvx ruff@<numéro> format .`, qui ne fait que du découpage de lignes.

## Ce que la suite de tests interdit, et pourquoi

- **Les tests ne parlent aux widgets que par les rôles de `tests/contract.py`.** Ce fichier est le
  manifeste `rôle -> nom d'objet` de toute l'interface. Un widget renommé se corrige là et nulle part
  ailleurs. Écrire `banner.cmb_versions` dans un test est une régression.
- **Aucune valeur de version recopiée dans un test.** Le numéro affiché vient de `app/about.py`. Un test
  qui connaît le numéro oblige à modifier les tests à chaque publication.
- **Une chaîne visible passe par `t("...")` avec un littéral.** `t(f"...")` est une régression. La table
  anglaise (`app/translations/en.py`) doit être complète : un test échoue à la première clé manquante,
  un autre échoue si un texte visible est écrit en toutes lettres dans `app/widgets/`.

## Réseau : les règles qui ne bougent pas

Tout l'accès réseau est dans `app/github.py`, et il n'est appelé que par `app/jobs.py` — jamais depuis
un slot d'interface, jamais depuis un thread qui touche un widget.

- `allow_redirects=False` sur chaque appel. Les redirections sont suivies à la main, chaque saut est
  re-validé (HTTPS + liste blanche de serveurs) et borné à 3 sauts.
- **Ne jamais remettre `allow_redirects=True`**, et ne jamais écrire `session.max_redirects = 0` non
  plus : `requests` résout le premier saut en interne dans les deux cas, et dans le second il lève
  `TooManyRedirects` dès le premier `302` — ce qui faisait échouer chaque téléchargement d'asset.
- `session.trust_env = False`, `verify = True` en dur : ni proxy implicite, ni `~/.netrc`.
- Un nom d'asset vient du réseau : il passe obligatoirement par `safe_asset_name()`.

`tools/audit_net.py` vérifie ces propriétés (63 contrôles) et échoue si une tentative de connexion est
enregistrée là où elle est interdite. C'est un outil de vérification pour qui modifie le dépôt, pas un
outil destiné à l'utilisateur final ; il est publié quand même, pour que la vérification soit
reproductible ailleurs.

## Licences : ce qui est refusé

Le projet dépend de **`pyside6-essentials`**, pas du métapaquet `pyside6`. La raison est mesurée sur les
paquets installés (fichiers `RECORD` des `.dist-info`) : `pyside6-addons`, `pyside6-pdf` et
`pyside6-webengine` apportent `Qt6Multimedia.dll`, `Qt6Pdf.dll`, `Qt6WebEngineCore.dll` et les
bibliothèques ffmpeg (`avcodec-*.dll`, `avformat-*.dll`, `avutil-*.dll`). QtWebEngine et QtPdf sont des
modules Qt **sous GPL**, pas LGPL. Le programme n'importe que `QtCore`, `QtGui`, `QtWidgets` — le support
SVG des drapeaux de langue est bien dans Essentials.

- Ne pas ajouter `PySide6-Addons`, `PySide6-Pdf` ou `PySide6-WebEngine` sans relire
  `THIRD-PARTY-NOTICES.md` et le contrôle de DLL de la ligne de publication.
- La construction reste en **`--onedir`** : les DLL Qt doivent rester des fichiers séparés et
  remplaçables par le destinataire, ce que demande la section 6 de la LGPL.
- Une seule exception de licence est suivie : la **LGPL-3.0**. Les exceptions publiées par la Qt Company
  ne lèvent des obligations que lorsque la bibliothèque n'est pas remplaçable (lien statique, exécutable
  d'un seul morceau), ce qui n'est pas le cas ici.
- `tools/export_licenses.py` assemble `licenses/` depuis les paquets installés et **sort en code 1** s'il
  manque un texte : il n'invente jamais un texte. Le seul texte qu'aucun paquet ne fournit — le texte
  intégral LGPL-3.0 — est suivi à la main dans `legal/` (voir `legal/README.md`).
- La ligne de publication refuse un livrable qui contiendrait une DLL GPL, et un livrable auquel
  manquerait le texte de licence.

## Piège connu après un changement de dépendance PySide6

Les paquets PySide6 écrivent tous dans le même dossier `PySide6/`, et leurs listes de fichiers se
recouvrent partiellement. Passer du métapaquet à `pyside6-essentials` a fait désinstaller les paquets en
trop, qui ont effacé au passage `PySide6/__init__.py` : l'import échoue alors avec
`ImportError: DLL load failed while importing QtCore`. Le fichier manquant est revendiqué par le paquet
restant (ligne `PySide6/__init__.py` de son `RECORD`). Réparation : `uv sync --reinstall`, qui redépose
tous les fichiers des paquets conservés. Vérification : `python -c "import PySide6; print(PySide6.__file__)"`
doit afficher un chemin se terminant par `__init__.py`, et non `None`.

## Publier une version

1. Le numéro vit à **deux endroits** : `app/about.py` (`APP_VERSION`, affiché dans le titre de la fenêtre)
   et `pyproject.toml` (`[project] version`). Les modifier tous les deux. Le test
   `tests/test_structure.py::test_la_version_affichee_est_celle_du_projet` échoue si l'un des deux est
   oublié : c'est le seul garde-fou, et il ne contient aucun numéro.
2. `requirements-build.txt` doit porter un numéro précis : `pyinstaller==<version>`. Pour le lire :
    ```bash
    uv run --python 3.13 --with pyinstaller --no-project python -c "import PyInstaller.__main__ as p; print(p.__version__)"
    ```
    Tant que le fichier porte une valeur non numérique, la publication s'arrête sur ce point au lieu de
    construire avec un outil pris au hasard.
3. `legal/lgpl-3.0.txt` doit exister (voir `legal/README.md`), sinon `tools/export_licenses.py` bloque la
   publication.
4. Commit, puis tag annoté **`vX.Y.Z`** où `X.Y.Z` est exactement le numéro de `pyproject.toml`. Le tag
   déclenche `.github/workflows/release.yml` : elle relance les contrôles, construit l'exécutable,
   vérifie ce qu'il embarque réellement (DLL interdites, texte de licence présent, numéro du tag égal au
   numéro du projet), le **démarre vraiment** en mode hors écran (`--smoke-test`, qui rend un code de
   sortie non nul si la fenêtre ne s'est pas construite), fabrique les deux archives source et ouvre une
   publication **en brouillon**. La décision finale de publier reste manuelle.
5. Deux points d'honnêteté sur le livrable : les archives source sont fabriquées avec `git archive` sur
   le commit étiqueté — un fichier non commité n'y figure pas — et l'exécutable **n'est pas signé**, donc
   Windows affiche un avertissement SmartScreen au premier lancement.
