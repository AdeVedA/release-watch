# Textes de licence suivis à la main

Ce dossier contient les textes qu'**aucun paquet Python ne fournit**, mais qu'un livrable doit
porter. `tools/export_licenses.py` recopie **tout** ce dossier (sauf ce mode d'emploi) dans
`licenses/legal/` et **sort en code 1** si un texte obligatoire manque : une CI ne peut donc pas
publier un exécutable sous-licencié. Le dossier part aussi tel quel dans l'exécutable
(`--add-data "legal;legal"`).

| Fichier | Pourquoi il est ici | Où le récupérer |
| --- | --- | --- |
| `lgpl-3.0.txt` | PySide6 et shiboken6 déclarent `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`, mais leur paquet ne livre qu'un renvoi vers la licence commerciale Qt : le texte LGPL intégral n'est fourni par personne. | https://www.gnu.org/licenses/lgpl-3.0.txt |

Récupération une seule fois, puis versionnement ici (ce dossier n'est pas filtré par `.gitignore`) :

```bash
curl -fsSL -o legal/lgpl-3.0.txt https://www.gnu.org/licenses/lgpl-3.0.txt
```

Vérifier ensuite que le fichier porte bien le titre de la licence et qu'il n'est pas vide :

```bat
findstr /n "LESSER" legal\lgpl-3.0.txt
```

## Pourquoi il n'y a pas d'« exception Qt » ici

La Qt Company publie des exceptions à ses licences. Celles qui concernent la LGPL ne lèvent des
obligations que dans un seul cas : quand la bibliothèque **ne peut pas être remplacée** par le
destinataire (bibliothèque collée dans l'exécutable, lien statique, `--onefile`). Le livrable est
construit en `--onedir` : les `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll` et `Qt6Svg.dll` restent
des fichiers distincts, écrasables. L'obligation de la section 6 de la LGPL-3.0 est ainsi tenue sans
aucune exception, et son texte n'est demandé par personne.

Aucun autre texte n'est nécessaire : le livrable ne s'appuie sur aucune exception, ni attachée à la
LGPL ni attachée à la GPL. Les exceptions publiées par la Qt Company concernent des situations qui
ne sont pas les nôtres (bibliothèque non remplaçable, sortie des outils Qt, greffons).

Ces textes ne sont pas relus ni modifiés : ce sont des copies intégrales, conservées telles
qu'éditées par leurs auteurs.
