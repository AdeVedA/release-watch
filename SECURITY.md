# Signaler une faille

## Comment signaler

Le canal est le **signalement de vulnérabilité privé** de GitHub (onglet *Security* → *Report a
vulnerability*). Ne pas ouvrir une issue publique pour un problème de sécurité : le dépôt est public,
et l'application tourne sur des postes qui la mettent à jour.

Réponse visée : un accusé de lecture sous une semaine. Pas de programme de récompense.

## Ce que le code tient déjà, et comment le vérifier

Le modèle de menace est simple : l'application lit l'API publique de GitHub, télécharge des fichiers
dont le nom vient du réseau, et lance des scripts que l'utilisateur a lui-même désignés.

| Surface | Ce qui est fait | Où le vérifier |
| ------- | --------------- | -------------- |
| Serveurs contactés | HTTPS uniquement ; hôtes limités à `github.com` / `githubusercontent.com` et à une liste d'hôtes exacts | `app/github.py` (`require_https`, `host_allowed`) |
| Redirections | `allow_redirects=False` partout ; sauts suivis à la main, re-validés un par un, bornés à 3 | `app/github.py` (`next_hop`, `MAX_HOPS`) |
| Proxy et credentials ambiants | `session.trust_env = False` : ni proxy système, ni `~/.netrc` ; `verify = True` en dur | `app/github.py` |
| Noms de fichiers venant du réseau | assainis : traversée de dossier, noms réservés Windows, caractères dangereux, longueur | `safe_asset_name()` |
| Écriture d'un téléchargement | `.part` puis renommage ; une erreur laisse un `.part`, jamais un fichier à moitié écrit | `download_asset()` |
| Liens cliquables des notes | `https://` seulement, filtrés deux fois ; `http://`, `file://` et autres sont tracés comme refusés | `app/widgets/notes_dock.py`, `MainWindow._open_url` |
| Scripts utilisateur | jamais `shell=True` ; la commande est construite en liste ; les métacaractères de coquille dans un chemin sont refusés sur les deux systèmes ; environnement de l'appli retiré de l'enfant | `app/scripts.py` |
| Ouverture d'un dossier local | `QDesktopServices.openUrl(QUrl.fromLocalFile(...))` sur un chemin qui existe, jamais un `subprocess` | `MainWindow._open_folder` |

`tools/audit_net.py` (63 contrôles, hors écran, sans jamais ouvrir de socket) et
`tests/test_github.py` (faux adaptateur, aucune vraie connexion) existent pour que ces affirmations
se vérifient au lieu de se croire.

## Ce qui n'est pas couvert

À lire avant de signaler quelque chose comme un bug :

- **Les scripts désignés par l'utilisateur.** L'application refuse une commande passée par un shell et
  les chemins contenant des métacaractères, mais un script légitime fait ce qu'il fait : le contenu d'un
  `.bat` ou d'un `.sh` choisi par l'utilisateur ne peut pas constituer une faille de l'application.
- **Un asset téléchargé.** L'application ne l'exécute jamais. L'exécuter relève du choix de
  l'utilisateur : la liste des versions vient de GitHub, pas d'un contrôle d'intégrité. Il n'y a ni
  signature, ni empreinte, ni vérification de ce que publient les dépôts surveillés.
- **Le service GitHub lui-même**, ses quotas (60 requêtes anonymes par heure et par adresse IP), et ce
  que GitHub voit de la machine qui l'utilise : l'application ne peut pas être anonyme côté GitHub,
  chaque requête est identifiée par l'adresse IP du poste.
- **Le dépôt de l'état.** `data/state.json` est en clair à côté de l'application, par choix assumé. Il
  ne contient ni jeton, ni mot de passe — l'application ne gère aucun jeton.
- **L'exécutable publié n'est pas signé.** SmartScreen affichera un avertissement au premier
  lancement. Ce n'est pas une faille, c'est l'absence d'un certificat payant.
- Les issues qui demandent de gérer des **dépôts privés** : sans jeton, ce n'est pas le modèle du
  projet.

## Périmètre

La **dernière version publiée** est la seule maintenue. Indiquer le numéro affiché dans le titre de la
fenêtre (`ReleaseWatch 0.1.0 — …`) : c'est le seul numéro qui corresponde au code exécuté.
