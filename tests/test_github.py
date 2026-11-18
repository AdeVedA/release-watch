"""Telechargement d'assets et suivi manuel des redirections, sans aucun paquet sur le reseau.

Non-regression : `session.max_redirects = 0` faisait echouer CHAQUE telechargement. Avec
`allow_redirects=False`, requests appelle quand meme `resolve_redirects` (pour calculer
`Response.next()`), et cette methode leve `TooManyRedirects("Exceeded 0 redirects.")` des le
premier 302 quand la valeur est 0. Un asset GitHub repond pourtant toujours par un 302.

Les requetes sont servies par un faux adaptateur monte sur la session : rien ne sort de la
machine, et la liste blanche d'hotes ainsi que `next_hop()` restent dans le chemin testé.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter

from app.github import MAX_HOPS, Asset, GitHubClient, RedirectRefusedError

SOURCE_URL = "https://github.com/acme/tool/releases/download/v1.0.0/tool.zip"
CIBLE_URL = "https://objects.githubusercontent.com/tool-v1.0.0.zip"
CONTENU = b"archive factice de test"


class ServeurFactice(HTTPAdapter):
    """Renvoie un 302 vers `destination` tant que l'URL demandee n'est pas cette destination.

    Les reponses sont construites avec `_content` deja lu : iter_content() debite ces octets
    sans jamais toucher une socket, et `Response.close()` devient une operation vide.
    """

    def __init__(self, destination: str) -> None:
        super().__init__()
        self._destination = destination
        self.visited: list[str] = []

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: dict[str, str] | None = None,
    ) -> Response:
        url = request.url or ""
        self.visited.append(url)
        response = Response()
        response.url = url
        response.request = request
        response._content = CONTENU if url == self._destination else b""
        response._content_consumed = True
        if url == self._destination:
            response.status_code = 200
            response.headers["Content-Length"] = str(len(CONTENU))
        else:
            response.status_code = 302
            response.headers["Location"] = self._destination
        return response


def client_factice(destination: str) -> tuple[GitHubClient, ServeurFactice]:
    client = GitHubClient()
    serveur = ServeurFactice(destination)
    client._session.mount("https://", serveur)
    return client, serveur


class BoucleSansFin(HTTPAdapter):
    """302 eternel vers une URL autorisee differente a chaque passage : la boucle ne finit pas.

    C'est la forme reelle du piege : seule la boucle manuelle `MAX_HOPS` de `download_asset`
    arrete le cycle, jamais requests (le suivi automatique est desactive).
    """

    def __init__(self) -> None:
        super().__init__()
        self.visited: list[str] = []

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: dict[str, str] | None = None,
    ) -> Response:
        url = request.url or ""
        self.visited.append(url)
        response = Response()
        response.url = url
        response.request = request
        response._content = b""
        response._content_consumed = True
        response.status_code = 302
        response.headers["Location"] = f"{CIBLE_URL}/etape-{len(self.visited)}"
        return response


def asset_factice() -> Asset:
    return Asset(name="tool.zip", url=SOURCE_URL, size=len(CONTENU))


def test_session_ne_leve_plus_sur_le_premier_302() -> None:
    """Regression directe du reglage `max_redirects = 0` : la valeur doit rester positive."""
    client = GitHubClient()
    try:
        assert client._session.max_redirects > 0
    finally:
        client.close()


def test_download_asset_suit_la_redirection_validee(tmp_path: Path) -> None:
    client, serveur = client_factice(CIBLE_URL)
    try:
        chemin = client.download_asset(asset_factice(), tmp_path)
    finally:
        client.close()
    assert serveur.visited == [SOURCE_URL, CIBLE_URL], "le saut github.com -> objet doit etre suivi"
    assert chemin.name == "tool.zip"
    assert chemin.read_bytes() == CONTENU
    assert not (tmp_path / "tool.zip.part").exists(), "le .part ne doit pas trainer"


def test_download_asset_refuse_une_boucle_de_redirections(tmp_path: Path) -> None:
    client = GitHubClient()
    serveur = BoucleSansFin()
    client._session.mount("https://", serveur)
    try:
        with pytest.raises(RedirectRefusedError):
            client.download_asset(asset_factice(), tmp_path)
    finally:
        client.close()
    assert len(serveur.visited) == MAX_HOPS + 1, "la boucle manuelle doit rester bornée à MAX_HOPS"
    assert list(tmp_path.iterdir()) == [], "aucune trace du telechargement avorte"


def test_download_asset_ecrit_sous_le_nom_choisi(tmp_path: Path) -> None:
    """« Enregistrer sous » impose son nom : ni « tool (1) » invente, ni nom de l'asset plaque.

    L'explorateur a deja demande la confirmation d'ecrasement : ecrire par-dessus le fichier
    present est ici le comportement voulu, pas une perte de donnee.
    """
    (tmp_path / "ma-version.zip").write_bytes(b"ancien fichier")
    client, _serveur = client_factice(CIBLE_URL)
    try:
        chemin = client.download_asset(asset_factice(), tmp_path, "ma-version.zip")
    finally:
        client.close()
    assert chemin.name == "ma-version.zip"
    assert chemin.read_bytes() == CONTENU
    assert sorted(f.name for f in tmp_path.iterdir()) == ["ma-version.zip"], "aucun suffixe invente"


def test_download_asset_sanitize_le_nom_choisi(tmp_path: Path) -> None:
    """Le nom vient d'une saisie libre : traverssee de dossier et caracteres dangereux tombent."""
    client, _serveur = client_factice(CIBLE_URL)
    try:
        chemin = client.download_asset(asset_factice(), tmp_path, "../../mauvais|nom.zip")
    finally:
        client.close()
    assert chemin.parent == tmp_path
    assert "|" not in chemin.name and ".." not in chemin.name
    assert chemin.read_bytes() == CONTENU
