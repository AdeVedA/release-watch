# Avis de licences des composants tiers

ReleaseWatch est distribué sous **licence MIT** (voir `LICENSE`). Ce fichier dit ce que le
programme **embarque** et ce qu'il **écarte**, parce que ces deux points se discutent au moment de
distribuer un exécutable.

Les textes intégraux sont posés à côté du livrable, dans `licenses/` (généré par
`tools/export_licenses.py` depuis les paquets installés : jamais une copie faite à la main).

## 1. Ce que le programme utilise à l'exécution

| Composant | Licence déclarée par le paquet | Ce que nous en faisons |
| --- | --- | --- |
| PySide6-Essentials 6.12 | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | nous choisissons **LGPL-3.0-only** |
| shiboken6 6.12 | idem | idem |
| Qt 6 (les `Qt6*.dll` chargées par PySide6) | LGPL-3.0, avec l'exception « LGPLv3 » de la Qt Company | lien **dynamique**, DLL séparées et remplaçables |
| requests 2.34 | Apache-2.0 (avec son `NOTICE`) | texte et `NOTICE` embarqués |
| urllib3 2.8 | MIT | texte embarqué |
| charset-normalizer 3.5 | MIT | texte embarqué |
| idna 3.20 | BSD-3-Clause | texte embarqué |
| certifi 2026 | MPL-2.0 | texte embarqué |
| Python 3.13 | PSF-2.0 (le runtime est embarqué par PyInstaller) | texte à embarquer avec le livrable |
| Microsoft Visual C++ runtime (`vcruntime140.dll`, `msvcp140*.dll`, `vccorlib140.dll`, `concrt140.dll`, `vcomp140.dll`) | redistribuable selon les conditions Microsoft | redistributeur autorisé, sans modification |

## 2. Comment l'obligation LGPL est satisfaite

Le choix de construction n'est pas esthétique, il tient l'obligation légale :

- **`--onedir`, jamais `--onefile`.** Les bibliothèques Qt restent des fichiers `Qt6*.dll` distincts
  à côté de l'exécutable : elles restent **remplaçables** par le destinataire, ce qui est le cœur de
  la section 6 de la LGPL.
- **Le texte de la licence est livré** : `licenses/legal/lgpl-3.0.txt` (voir `legal/README.md`), plus
  `licenses/INDEX.md`, qui liste paquet par paquet ce qui est embarqué.
- **Aucune exception Qt n'est nécessaire.** Les exceptions publiées par la Qt Company ne lèvent des
  obligations que là où la bibliothèque n'est **pas** remplaçable (lien statique, exécutable d'un seul
  morceau). Ce n'est pas le cas de ce livrable : la section 6 de la LGPL-3.0 est tenue par le
  `--onedir` lui-même, donc aucune exception n'est demandée ni invoquée.
- **Aucune source du projet n'est sous GPL** : le projet est MIT, et lier Qt en dynamique sous LGPL
  n'importe pas d'obligation GPL dans notre code.

## 3. Ce qui est volontairement écarté (le point important)

Le métapaquet `pyside6` installe `pyside6-addons`, `pyside6-pdf` et `pyside6-webengine`. Vérifié
localement sur les paquets installés (fichiers `RECORD` des `.dist-info`) :

- `Qt6Multimedia.dll`, `Qt6WebEngineCore.dll` et les DLL **ffmpeg** (`avcodec-63.dll`,
  `avformat-63.dll`, `avutil-61.dll`) sont installés par ces paquets (wheels) supplémentaires ;
- QtWebEngine et QtPdf sont des modules Qt **sous GPL** (et non LGPL) dans la distribution Qt, et
  ffmpeg est lui-même sous licences multiples ;
- l'application n'importe **que** `QtCore`, `QtGui` et `QtWidgets` ; tout ce dont elle a besoin —
  `Svg`, `DBus`, `Concurrent`, `Network`, `Xml`, `PrintSupport` — est dans `pyside6-essentials`.

Le projet dépend donc de **`pyside6-essentials`**, pas de `pyside6`. Ce qui n'est pas lié n'est pas
embarqué : la chaîne GPL et ffmpeg disparaissent du `.exe` comme du virtualenv. La vérification est
automatisée par la CI de publication (voir `CONTRIBUTING.md`).

## 4. Outils de construction (non embarqués)

`uv`, `ruff`, `ty`, `pytest` (et ses dépendances : iniconfig, packaging, pluggy, pygments, colorama)
et `PyInstaller` servent à construire et vérifier le programme. Ils ne sont pas liés au programme et
ne sont pas distribués avec lui ; leur licence ne s'applique pas au code de ReleaseWatch. Deux
précisions pour celui qui refait le build :

- le générateur d'exécutable est sous GPL avec une exception qui couvre le binaire produit — c'est
  précisément la raison pour laquelle le build est reproductible et publié avec le projet (voir
  `.github/workflows/`) ;
- `PySide6-Addons`, `PySide6-Pdf` et `PySide6-WebEngine` ne sont pas installés par ce projet. Qui les
  ajoute doit relire la partie GPL correspondante avant de redistribuer.

## 5. Ce que ce fichier n'est pas

Un avis juridique. Pour rediffuser l'application modifiée ou l'exécutable ailleurs, relire la section
 de la LGPL : les textes sont dans `licenses/legal/`.
