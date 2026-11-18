"""Client API GitHub (public, anonyme) et téléchargement d'assets.

Zéro trust réseau :
- aucune requête n'est émise à l'init : seul un appel explicite (fetch, vérifier,
  télécharger) déclenche du trafic ;
- `trust_env` désactivée : ni proxy implicite, ni `~/.netrc`, ni variables d'environnement
  ne peuvent dévier une requête ou ajouter un jeton ;
- HTTPS obligatoire, hôtes autorisés en liste blanche, redirections JAMAIS suivies
  automatiquement : chaque saut est re-validé (hôte + schéma) et borné à `MAX_HOPS` ;
- le nom d'asset vient du réseau : il est assaini avant toute écriture disque ;
- `requests` n'est importé qu'à la première requête : 107 ms d'import ne sont plus payés
  à chaque lancement, alors qu'aucun appel réseau n'a lieu au démarrage.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from types import ModuleType
from typing import IO, TYPE_CHECKING
from urllib.parse import quote, urljoin, urlparse

if TYPE_CHECKING:
    # Annotation seule : `requests` n'est pas importe a l'execution (voir `_requests()`).
    import requests

from app.filters import keep
from app.i18n import t
from app.models import (
    DATING_WINDOW_MARGIN,
    LISTING_REQUESTS_PER_REPO,
    MATCHING_REFS_PAGE,
    MAX_MATCHING_PREFIXES_PER_PASS,
    MAX_RELEASES,
    MAX_REQUESTS_PER_PASS,
    MAX_VISIBLE_VERSIONS,
    VERSIONS_SOURCE_RELEASES,
    VERSIONS_SOURCE_TAGS,
    Asset,
    DatingPlan,
    ReleaseInfo,
    natural_key,
    tag_family,
    tag_search_prefixes,
)

API_ROOT: str = "https://api.github.com"
API_HOST: str = "api.github.com"
API_VERSION: str = "2022-11-28"
DOWNLOAD_CHUNK: int = 256 * 1024
TIMEOUT: tuple[float, float] = (6.0, 25.0)
MAX_HOPS: int = 3
REDIRECT_CODES: frozenset[int] = frozenset({301, 302, 303, 307, 308})
# Reponse conditionnelle (`If-None-Match`) : rien n'a change, le contenu en base reste bon.
NOT_MODIFIED: int = 304
# Le motif « a garder » est applique apres telechargement : si on ne demandait que les 25
# tags les plus recents, un repo dont les tags recents ne correspondent pas au motif
# perdrait la release qui l'interesse avant meme le filtre. 100 est le maximum accepte
# par GitHub, et cela ne coute toujours qu'une seule requete.
TAGS_PAGE_SIZE: int = 100

HOST_SUFFIX_ALLOWLIST: tuple[str, ...] = ("github.com", "githubusercontent.com")
HOST_EXACT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "github.com",
        "api.github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "media.githubusercontent.com",
    }
)
MAX_NAME_LENGTH: int = 180
WINDOWS_RESERVED: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)

_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)", re.I),
    re.compile(r"^(?:git@|ssh://git@)github\.com[:/](?P<owner>[\w.-]+)/(?P<name>[\w.-]+)", re.I),
    re.compile(r"^(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)$"),
)


_REQUESTS: ModuleType | None = None


def _requests() -> ModuleType:
    """Charge `requests` a la premiere requete, jamais a l'import du module.

    L'import de requests (urllib3, charset_normalizer, email, ...) coute 107 ms sur les
    251 ms d'import de l'application, alors qu'aucun appel reseau n'est emis au
    demarrage : il etait donc paye pour rien a chaque lancement.
    """
    global _REQUESTS
    if _REQUESTS is None:
        import requests

        _REQUESTS = requests
    return _REQUESTS


class GitHubError(RuntimeError):
    """Erreur d'accès à GitHub, affichable telle quelle à l'utilisateur."""


class BadRepoUrlError(GitHubError):
    """L'adresse saisie n'est pas un repo GitHub exploitable."""


class RepoNotFoundError(GitHubError):
    """404 : GitHub ne distingue pas repo inexistant et repo privé en anonyme."""


class NetworkError(GitHubError):
    """Timeout, DNS, TLS : la requête n'est pas arrivée jusqu'à GitHub."""


class RateLimitedError(GitHubError):
    def __init__(self, message: str, retry_after_minutes: int) -> None:
        super().__init__(message)
        self.retry_after_minutes = retry_after_minutes


class RedirectRefusedError(GitHubError):
    """La redirection sortirait de la liste blanche d'hôtes ou du HTTPS."""


class InsecureURLError(GitHubError):
    """URL en clair (non HTTPS) refusée."""


@dataclass(slots=True)
class RepoMeta:
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    description: str
    stars: int


@dataclass(slots=True)
class RateInfo:
    limit: int
    remaining: int
    reset_at: datetime

    @property
    def minutes_to_reset(self) -> int:
        delta = self.reset_at - datetime.now(tz=UTC)
        return max(0, int(delta.total_seconds() // 60))


@dataclass(slots=True)
class FetchResult:
    """Résultat d'une passe de récupération des versions.

    `etags` est rendu tel quel pour être mémorisé sur le repo : un `304` évite le transfert et
    la reconstruction, pas la requête (mesuré : un `304` consomme 1 sur le quota anonyme).
    `tag_index` recense les noms de tags déjà vus (`nom -> sha`), `dates` les dates déjà payées
    dans cette passe, et `prefixes_done` les préfixes `matching-refs` qui ont rendu une liste
    complète. Ces trois caches sont fusionnés dans le `Repo` par la fenêtre principale.
    """

    releases: list[ReleaseInfo]
    etags: dict[str, str] = field(default_factory=dict)
    tag_index: dict[str, str] = field(default_factory=dict)
    dates: dict[str, str] = field(default_factory=dict)
    prefixes_done: list[str] = field(default_factory=list)
    dated: int = 0
    listing_used: int = 0
    match_used: int = 0
    not_modified: bool = False


def parse_repo_url(raw: str) -> tuple[str, str]:
    text = raw.strip().rstrip("/")
    for pattern in _URL_PATTERNS:
        match = pattern.match(text)
        if match:
            owner = match.group("owner").removesuffix(".git")
            name = match.group("name").removesuffix(".git")
            if owner in {".", ".."} or name in {".", ".."}:
                raise BadRepoUrlError(t("Nom de repo invalide."))
            if len(owner) > 100 or len(name) > 100:
                raise BadRepoUrlError(t("Nom de repo trop long."))
            if owner and name:
                return owner, name
    raise BadRepoUrlError(
        t(
            "Adresse invalide. Formes acceptées : https://github.com/owner/repo, "
            "git@github.com:owner/repo.git, ou owner/repo."
        )
    )


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host in HOST_EXACT_ALLOWLIST:
        return True
    return any(host.endswith(f".{suffix}") for suffix in HOST_SUFFIX_ALLOWLIST)


def require_https(url: str) -> str:
    if urlparse(url).scheme.lower() != "https":
        raise InsecureURLError(t("URL non HTTPS refusée : {url}").format(url=url))
    return url


def next_hop(headers: Mapping[str, str], current: str) -> str:
    location = headers.get("Location") or headers.get("location") or ""
    if not location:
        raise RedirectRefusedError(t("Redirection sans destination depuis : {url}").format(url=current))
    target = urljoin(current, location)
    require_https(target)
    if not host_allowed(target):
        raise RedirectRefusedError(t("Redirection vers un hôte hors liste blanche refusée : {url}").format(url=target))
    return target


def safe_asset_name(raw: str, fallback: str) -> str:
    """Le nom d'asset vient du réseau : ni traversée de dossier ni nom réservé."""
    candidate = PureWindowsPath(raw.replace("/", "\\")).name.strip()
    candidate = "".join(char for char in candidate if char not in '<>:"|?*' and ord(char) >= 32)
    candidate = candidate.strip(" .")
    if not candidate or candidate in {".", ".."}:
        candidate = fallback
    if candidate.split(".", 1)[0].lower() in WINDOWS_RESERVED:
        candidate = f"_{candidate}"
    return candidate[:MAX_NAME_LENGTH] or fallback


def _api_str(data: Mapping[str, object], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value if isinstance(value, str) else default


def _api_int(data: Mapping[str, object], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _api_bool(data: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _api_mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _api_entries(data: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _as_list(response: requests.Response) -> list[Mapping[str, object]]:
    payload = response.json()
    if not isinstance(payload, list):
        raise GitHubError(t("Réponse GitHub inattendue : une liste était attendue."))
    return [entry for entry in payload if isinstance(entry, dict)]


def _as_dict(response: requests.Response) -> Mapping[str, object]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise GitHubError(t("Réponse GitHub inattendue : un objet était attendu."))
    return payload


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: tuple[float, float] = TIMEOUT) -> None:
        self._session = _requests().Session()
        self._session.trust_env = False
        self._session.verify = True
        # `max_redirects` laissé à son défaut : avec `allow_redirects=False`, requests appelle
        # quand même `resolve_redirects` pour calculer `Response.next()`, et cette méthode lève
        # `TooManyRedirects("Exceeded 0 redirects.")` dès le premier 302 si la valeur est 0 —
        # tout téléchargement d'asset échouait. Le suivi automatique reste impossible :
        # `allow_redirects=False` partout, chaque saut est re-validé par `next_hop` et borné
        # par `MAX_HOPS`.
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "script-launcher",
            }
        )
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout
        self.rate: RateInfo | None = None

    def close(self) -> None:
        self._session.close()

    def _header_int(self, response: requests.Response, name: str) -> int:
        raw = response.headers.get(name, "")
        try:
            return int(raw)
        except ValueError:
            return 0

    def _remember_rate(self, response: requests.Response) -> None:
        if "X-RateLimit-Remaining" not in response.headers:
            return
        self.rate = RateInfo(
            limit=self._header_int(response, "X-RateLimit-Limit"),
            remaining=self._header_int(response, "X-RateLimit-Remaining"),
            reset_at=datetime.fromtimestamp(self._header_int(response, "X-RateLimit-Reset"), tz=UTC),
        )

    def _raise_for_status(self, response: requests.Response, url: str) -> None:
        if response.status_code == 404:
            raise RepoNotFoundError(t("Repo introuvable, orthographe à vérifier, ou repo privé."))
        if response.status_code in (403, 429):
            remaining = self._header_int(response, "X-RateLimit-Remaining")
            wait = self.rate.minutes_to_reset if self.rate is not None else 0
            if remaining == 0 or response.status_code == 429:
                raise RateLimitedError(
                    t("Quota anonyme GitHub atteint (60 requêtes/heure). Attendre environ {wait} min.").format(
                        wait=wait
                    ),
                    wait,
                )
            raise GitHubError(t("Accès refusé par GitHub (403) : {detail}").format(detail=response.text[:180]))
        if response.status_code >= 400:
            raise GitHubError(t("GitHub a répondu {code} pour {url}").format(code=response.status_code, url=url))

    def _get_no_redirect(self, url: str, params: dict[str, str] | None, etag: str | None = None) -> requests.Response:
        headers = {"If-None-Match": etag} if etag else None
        try:
            return self._session.get(url, params=params, timeout=self._timeout, allow_redirects=False, headers=headers)
        except _requests().RequestException as exc:
            raise NetworkError(t("Requête impossible vers {url} : {exc}").format(url=url, exc=exc)) from exc

    def _request(self, url: str, params: dict[str, str] | None = None, etag: str | None = None) -> requests.Response:
        require_https(url)
        if urlparse(url).netloc != API_HOST:
            raise RedirectRefusedError(
                t("Seul {host} est interrogé par l'application : {url}").format(host=API_HOST, url=url)
            )
        current = url
        hops = 0
        while True:
            response = self._get_no_redirect(current, params, etag)
            self._remember_rate(response)
            if response.status_code not in REDIRECT_CODES:
                self._raise_for_status(response, current)
                return response
            hops += 1
            if hops > MAX_HOPS:
                response.close()
                raise RedirectRefusedError(t("Trop de redirections consécutives pour {url}").format(url=url))
            target = next_hop(response.headers, current)
            response.close()
            if urlparse(target).netloc != API_HOST:
                raise RedirectRefusedError(
                    t("Redirection hors {host} refusée : {url}").format(host=API_HOST, url=target)
                )
            current = target

    def validate(self, owner: str, name: str) -> RepoMeta:
        data = _as_dict(self._request(f"{API_ROOT}/repos/{owner}/{name}"))
        owner_data = _api_mapping(data, "owner")
        return RepoMeta(
            owner=_api_str(owner_data, "login", owner),
            name=_api_str(data, "name", name),
            full_name=_api_str(data, "full_name", f"{owner}/{name}"),
            html_url=_api_str(data, "html_url", f"https://github.com/{owner}/{name}"),
            default_branch=_api_str(data, "default_branch"),
            description=_api_str(data, "description"),
            stars=_api_int(data, "stargazers_count"),
        )

    def fetch_versions(
        self,
        owner: str,
        name: str,
        limit: int,
        source: str = VERSIONS_SOURCE_TAGS,
        etags: Mapping[str, str] | None = None,
        previous: Sequence[ReleaseInfo] | None = None,
        listing_budget: int = LISTING_REQUESTS_PER_REPO,
        match_budget: int = MAX_MATCHING_PREFIXES_PER_PASS,
        dating_budget: int = MAX_REQUESTS_PER_PASS,
        tag_pattern: str = "",
        tag_exclude: str = "",
        plan: DatingPlan | None = None,
        known_dates: Mapping[str, str] | None = None,
        done_prefixes: Sequence[str] = (),
        dating_window: int = MAX_RELEASES,
    ) -> FetchResult:
        """Versions du repo, avec le maximum d'informations localement disponibles.

        Source `tags` (defaut) : `/tags` ne renvoie NI date NI message, seulement le nom du tag
        et le sha du commit qu'il designe. Chaque tag est donc enrichi par la release du meme nom
        (date, notes, assets, pre-release), et les tags restants sont dates a la source (voir
        `_date_missing_tags`). L'ordre rendu par GitHub n'est PAS chronologique : il suit les refs
        du depot, a peu pres par nom decroissant. Sur `llama.cpp`, `/tags` page 1 commence par
        `v0.9.0` puis `master-…` ; les tags `b…` recents sont des pages plus bas. L'ordre rendu
        n'est donc pas utilisable : les colonnes sont reconstruites cote modele par famille et par
        numero de version.

        `plan` vient de `Repo.dating_plan()` : il donne la file de tags deja connus a dater et les
        prefixes `matching-refs` a interroger. Si le plan est vide au premier fetch, les prefixes
        sont derives des releases fraichement recues (`_anchor_prefixes`) : sans cela, un depot
        comme `llama.cpp` resterait bloque sur les seules releases recues et ne verrait jamais les
        tags orphelins entre deux releases ou apres la derniere.
        """
        # Plafond d'une passe : de quoi remplir les deux colonnes (`storage_cap` côté modèle),
        # jamais le quota : une page `/tags` ou `/releases` en 100 entre dans une seule requête.
        capped = max(1, min(limit, MAX_VISIBLE_VERSIONS))
        known = dict(etags or {})
        remembered = list(previous or [])
        dates_cache = dict(known_dates or {})
        if source == VERSIONS_SOURCE_RELEASES:
            return self._fetch_releases_only(owner, name, capped, known, remembered, dates_cache, listing_budget)
        return self._fetch_tags_enriched(
            owner,
            name,
            capped,
            known,
            remembered,
            dates_cache,
            listing_budget,
            match_budget,
            dating_budget,
            tag_pattern,
            tag_exclude,
            plan,
            done_prefixes,
            dating_window,
        )

    def _conditional(
        self, url: str, params: dict[str, str], etag: str
    ) -> tuple[list[Mapping[str, object]] | None, str]:
        """`GET` conditionnel : (liste, ou `None` si GitHub a repondu 304, ETag courant).

        Le `304` ne sauve pas le quota (mesure : `304 quota=1`) : il sauve le transfert et la
        reconstruction locale. Les caches `tag_index` / `tag_dates` restent donc indispensables.
        """
        response = self._request(url, params=params, etag=etag or None)
        fresh = response.headers.get("etag", "")
        if response.status_code == NOT_MODIFIED:
            response.close()
            return None, etag
        return _as_list(response), fresh

    def _conditional_if_left(
        self, url: str, params: dict[str, str], etag: str, left: int
    ) -> tuple[list[Mapping[str, object]] | None, str, int]:
        if left <= 0:
            return None, etag, 0
        payload, fresh = self._conditional(url, params=params, etag=etag)
        return payload, fresh, 1

    def _fetch_releases_only(
        self,
        owner: str,
        name: str,
        capped: int,
        known: Mapping[str, str],
        remembered: Sequence[ReleaseInfo],
        dates_cache: Mapping[str, str],
        listing_budget: int,
    ) -> FetchResult:
        payload, etag, used = self._conditional_if_left(
            f"{API_ROOT}/repos/{owner}/{name}/releases",
            params={"per_page": str(TAGS_PAGE_SIZE)},
            etag=known.get("releases", ""),
            left=listing_budget,
        )
        result = FetchResult(releases=[], etags={"releases": etag}, listing_used=used)
        if payload is None:
            result.not_modified = True
            # Un 304 vaut pour `/releases` seulement : on ne rend que ce que cette source contient.
            result.releases = [item for item in remembered if item.source == VERSIONS_SOURCE_RELEASES]
            result.dates = {item.tag: item.published_at for item in result.releases if item.tag and item.published_at}
            return result
        parsed = [self._release_from_api(item) for item in payload]
        self._reuse_dates(parsed, remembered, dates_cache)
        result.releases = [item for item in parsed if item.tag][:capped]
        result.dates = {item.tag: item.published_at for item in result.releases if item.tag and item.published_at}
        return result

    def _fetch_tags_enriched(
        self,
        owner: str,
        name: str,
        capped: int,
        known: Mapping[str, str],
        remembered: Sequence[ReleaseInfo],
        dates_cache: Mapping[str, str],
        listing_budget: int,
        match_budget: int,
        dating_budget: int,
        tag_pattern: str = "",
        tag_exclude: str = "",
        plan: DatingPlan | None = None,
        done_prefixes: Sequence[str] = (),
        dating_window: int = MAX_RELEASES,
    ) -> FetchResult:
        left = max(0, listing_budget)
        tags, tags_etag, tags_used = self._conditional_if_left(
            f"{API_ROOT}/repos/{owner}/{name}/tags",
            params={"per_page": str(TAGS_PAGE_SIZE)},
            etag=known.get("tags", ""),
            left=left,
        )
        left -= tags_used
        releases, releases_etag, releases_used = self._conditional_if_left(
            f"{API_ROOT}/repos/{owner}/{name}/releases",
            params={"per_page": str(TAGS_PAGE_SIZE)},
            etag=known.get("releases", ""),
            left=left,
        )
        left -= releases_used
        result = FetchResult(
            releases=[],
            etags={"tags": tags_etag, "releases": releases_etag},
            listing_used=tags_used + releases_used,
        )
        if tags is None and releases is None and not (plan and plan.prefixes) and not remembered:
            result.not_modified = True
            return result
        # Un 304 ne concerne que la moitie qui l'a renvoye : l'autre liste, fraiche, doit
        # quand meme etre fusionnee avec ce que la partie 304 avait deja fourni. Sans ce
        # repli, `/releases` en 304 faisait perdre toutes les releases du bandeau : la liste
        # restait non vide mais plus aucune n'y passait le motif, d'ou « aucun tag ne passe
        # le filtre » au deuxieme « Verifier les repos ».
        enriched: dict[str, ReleaseInfo] = {}
        if releases is not None:
            for item in releases:
                release = self._release_from_api(item)
                if release.tag:
                    enriched[release.tag] = release
        else:
            enriched = {item.tag: item for item in remembered if item.source == VERSIONS_SOURCE_RELEASES}
        tag_names: list[str] = []
        if tags is not None:
            for item in tags:
                tag = _api_str(item, "name")
                sha = _api_str(_api_mapping(item, "commit"), "sha")
                if tag:
                    tag_names.append(tag)
                    if sha:
                        result.tag_index[tag] = sha
        else:
            # `/tags` en 304 : les noms memorises servent de repli, l'ordre definitif etant
            # de toute facon pose par le tri par date cote modele.
            tag_names = [item.tag for item in remembered if item.source == VERSIONS_SOURCE_TAGS]
        prefixes = self._prefix_requests(
            plan.prefixes if plan else [], enriched, tag_pattern, tag_exclude, done_prefixes, dating_window
        )
        listed, match_used, prefixes_done = self._fetch_matching_refs(owner, name, prefixes, max(0, match_budget))
        result.match_used = match_used
        result.prefixes_done = prefixes_done
        result.tag_index.update(listed)
        tag_names = list(dict.fromkeys(tag_names + list(listed)))
        merged: list[ReleaseInfo] = []
        for tag in tag_names:
            if not tag:
                continue
            merged.append(enriched.pop(tag, None) or self._tag_as_release(owner, name, tag))
        # Une release dont le tag n'est pas dans `/tags` doit rester visible : tag deplace,
        # ou repo dont la liste de tags est plus courte que celle des releases.
        merged.extend(enriched.values())
        if not merged:
            # Rien d'exploitable cote reseau : on garde ce qui est en base plutot que de
            # vider le bandeau, ce qui produirait un « aucune version recuperée » trompeur.
            result.not_modified = True
            result.releases = list(remembered)
            return result
        # Aucune troncature ici : la selection des lignes stockees est faite cote modele, ou le
        # motif « a garder » est connu (voir `Repo.pick_candidates`). Les noms supplementaires
        # coutent de la memoire, pas du quota ; le quota n'est engage que par matching-refs/dates.
        self._reuse_dates(merged, remembered, dates_cache)
        result.dated = self._date_missing_tags(
            owner,
            name,
            merged,
            dating_budget,
            tag_pattern,
            tag_exclude,
            plan,
            list(listed),
            dating_window,
        )
        result.releases = merged
        result.dates = {item.tag: item.published_at for item in merged if item.tag and item.published_at}
        return result

    def _fetch_matching_refs(
        self, owner: str, name: str, prefixes: Sequence[str], budget: int
    ) -> tuple[dict[str, str], int, list[str]]:
        """Liste des tags par prefixe, sans payer de datation. Utile quand `/tags` est noye.

        `matching-refs` ne renvoie ni date ni message : il ne sert qu'a retrouver des noms caches
        trop bas dans la pagination. Un prefixe qui revient a 1000 refs est laisse ouvert : il sera
        resserre a la passe suivante.
        """
        found: dict[str, str] = {}
        done: list[str] = []
        used = 0
        left = max(0, budget)
        for prefix in prefixes:
            if left <= 0:
                break
            try:
                entries = _as_list(
                    self._request(
                        f"{API_ROOT}/repos/{owner}/{name}/git/matching-refs/tags/{quote(prefix, safe='/')}",
                        params={"per_page": str(MATCHING_REFS_PAGE)},
                    )
                )
            except RateLimitedError:
                raise
            except GitHubError:
                continue
            used += 1
            left -= 1
            for entry in entries:
                ref = _api_str(entry, "ref")
                if not ref.startswith("refs/tags/"):
                    continue
                tag = ref[len("refs/tags/") :]
                sha = _api_str(_api_mapping(entry, "object"), "sha")
                if tag:
                    found[tag] = sha
            if len(entries) < MATCHING_REFS_PAGE:
                done.append(prefix)
        return found, used, done

    @staticmethod
    def _release_from_api(item: Mapping[str, object]) -> ReleaseInfo:
        assets: list[Asset] = []
        for entry in _api_entries(item, "assets"):
            assets.append(
                Asset(
                    name=_api_str(entry, "name"),
                    url=_api_str(entry, "browser_download_url") or _api_str(entry, "url"),
                    size=_api_int(entry, "size"),
                )
            )
        tag = _api_str(item, "tag_name")
        return ReleaseInfo(
            tag=tag,
            name=_api_str(item, "name") or tag,
            url=_api_str(item, "html_url"),
            published_at=_api_str(item, "published_at") or _api_str(item, "created_at"),
            notes_md=_api_str(item, "body"),
            source="releases",
            prerelease=_api_bool(item, "prerelease"),
            assets=assets,
        )

    @staticmethod
    def _tag_as_release(owner: str, name: str, tag: str) -> ReleaseInfo:
        """Un tag sans release : pas de date ni de notes dans `/tags`, seulement les archives."""
        base = f"https://github.com/{owner}/{name}"
        archive = f"{base}/archive/refs/tags/{tag}"
        return ReleaseInfo(
            tag=tag,
            name=tag,
            url=f"{base}/tags",
            published_at="",
            notes_md="",
            source=VERSIONS_SOURCE_TAGS,
            prerelease=False,
            assets=[
                Asset(name=f"{tag}.zip", url=f"{archive}.zip", size=0),
                Asset(name=f"{tag}.tar.gz", url=f"{archive}.tar.gz", size=0),
            ],
        )

    @staticmethod
    def _reuse_dates(
        target: list[ReleaseInfo],
        previous: Sequence[ReleaseInfo],
        dates_cache: Mapping[str, str] | None = None,
    ) -> int:
        """Reprend la date et le message deja obtenus pour un tag deja croise.

        Dater un tag coute une a deux requetes : la valeur est memorisee dans
        `data/state.json`, donc un tag deja date ne sera plus jamais re-date.
        """
        remembered = {item.tag: item for item in previous if item.published_at}
        remembered_dates = dict(dates_cache or {})
        reused = 0
        for release in target:
            if release.published_at:
                continue
            old = remembered.get(release.tag)
            if old is not None:
                release.published_at = old.published_at
                if not release.notes_md:
                    release.notes_md = old.notes_md
                reused += 1
                continue
            date = remembered_dates.get(release.tag)
            if date:
                release.published_at = date
                reused += 1
        return reused

    @staticmethod
    def _dating_targets(
        target: Sequence[ReleaseInfo],
        tag_pattern: str,
        tag_exclude: str,
        cap: int = MAX_RELEASES,
    ) -> list[ReleaseInfo]:
        """Cibles de repli quand aucun plan de fenetre n'a ete fourni par le modele."""
        allowed = [item for item in target if keep(item.tag, tag_pattern, tag_exclude)]
        refused = [item for item in target if not keep(item.tag, tag_pattern, tag_exclude)]
        stored = (allowed + refused)[: max(1, cap)]
        return [item for item in stored if not item.published_at]

    def _prefix_requests(
        self,
        planned: Sequence[str],
        anchors: Mapping[str, ReleaseInfo],
        tag_pattern: str,
        tag_exclude: str,
        done_prefixes: Sequence[str],
        dating_window: int,
    ) -> list[str]:
        """Prefixes `matching-refs` de la passe : d'abord ceux du plan, puis ceux des ancres vues.

        Un prefixe precedemment interroge n'est jamais exclusif : une ref peut apparaitre plus tard
        sous un prefixe qui etait vide ou incomplet. Ils passent seulement en dernier, derriere les
        prefixes nouveaux, pour que le budget serve d'abord a decouvrir ce qui a bouge.
        """
        out: list[str] = []
        pending = [prefix for prefix in planned if prefix and prefix not in done_prefixes]
        reused = [prefix for prefix in planned if prefix and prefix in done_prefixes]
        fallback = self._anchor_prefixes(anchors, tag_pattern, tag_exclude, dating_window)
        for prefix in [*pending, *fallback, *reused]:
            if prefix not in out:
                out.append(prefix)
            if len(out) >= MAX_MATCHING_PREFIXES_PER_PASS:
                break
        return out[:MAX_MATCHING_PREFIXES_PER_PASS]

    @staticmethod
    def _anchor_prefixes(
        anchors: Mapping[str, ReleaseInfo], tag_pattern: str, tag_exclude: str, dating_window: int
    ) -> list[str]:
        """Prefixes deduits des releases fraiches quand aucun plan n'etait encore disponible."""
        families: dict[str, list[int]] = {}
        dates: dict[str, str] = {}
        for release in anchors.values():
            if not release.tag or not release.published_at:
                continue
            if not keep(release.tag, tag_pattern, tag_exclude):
                continue
            family, number = tag_family(release.tag)
            if number is None:
                continue
            families.setdefault(family, []).append(number)
            dates[family] = max(dates.get(family, ""), release.published_at)
        groups: list[tuple[str, list[str]]] = []
        window = max(1, dating_window)
        for family, numbers in families.items():
            newest = max(numbers)
            ranked = sorted(numbers, reverse=True)
            floor = ranked[min(len(ranked) - 1, window - 1)] - DATING_WINDOW_MARGIN
            groups.append((dates.get(family, ""), tag_search_prefixes(family, newest, floor)))
        out: list[str] = []
        for _, prefixes in sorted(groups, key=lambda entry: entry[0], reverse=True):
            for prefix in prefixes:
                if prefix and prefix not in out:
                    out.append(prefix)
                if len(out) >= MAX_MATCHING_PREFIXES_PER_PASS:
                    return out
        return out

        return out

    def _date_queue(
        self,
        target: Sequence[ReleaseInfo],
        undated: Mapping[str, ReleaseInfo],
        plan: DatingPlan | None,
        extra: Sequence[str],
        tag_pattern: str,
        tag_exclude: str,
        window: int,
    ) -> list[str]:
        """File des tags sans date : les plus recents d'abord, plans connus et decouvertes melanges.

        Le repli local (`_dating_targets`) ne s'applique que si aucun plan exploitable n'a ete fourni :
        `plan.known == 0` signifie que le plan a ete calcule sur un etat local vide, donc qu'il ne
        contenait AUCUNE file. C'est le cas du premier controle global d'un bandeau fraichement ajoute :
        le budget de datation etait pourtant alloue, et sans ce repli il etait laisse intact pendant que
        les tags recement listes restaient sans date. Un plan construit sur un cache peuple reste lui
        seul maitre : ses exclusions (`master-…` sans ancre) doivent etre respectees, sinon la datation
        repartirait payer des familles entieres hors fenetre.
        """
        anchors: dict[str, list[int]] = {}
        for item in target:
            if not item.tag or not item.published_at:
                continue
            family, number = tag_family(item.tag)
            if number is not None and keep(item.tag, tag_pattern, tag_exclude):
                anchors.setdefault(family, []).append(number)

        size = max(1, window)
        above: list[str] = list(plan.above) if plan is not None else []
        inside: list[str] = list(plan.inside) if plan is not None else []

        for tag in extra:
            if tag not in undated or not keep(tag, tag_pattern, tag_exclude):
                continue
            family, number = tag_family(tag)
            numbers = anchors.get(family, [])
            if number is None or not numbers:
                continue
            newest = max(numbers)
            ranked = sorted(numbers, reverse=True)
            floor = ranked[min(len(ranked) - 1, size - 1)] - DATING_WINDOW_MARGIN
            if number > newest:
                above.append(tag)
            elif number >= floor:
                inside.append(tag)

        above.sort(key=natural_key, reverse=True)
        inside.sort(key=natural_key, reverse=True)
        cap_dates = max(MAX_VISIBLE_VERSIONS, size + DATING_WINDOW_MARGIN)
        queued = [*above, *inside]
        if plan is None or plan.known == 0:
            queued.extend(item.tag for item in self._dating_targets(target, tag_pattern, tag_exclude))
        return list(dict.fromkeys(tag for tag in queued if tag in undated))[:cap_dates]

    def _date_one_tag(self, owner: str, name: str, release: ReleaseInfo) -> tuple[bool, int]:
        """Date un tag et lui donne un message. Rend (date obtenue, requêtes payées).

        `GET /commits/{nom}` accepte un nom de tag et désannote les tags annotés : une seule
        requête suffit, et la date obtenue est celle du commit désigné, même référentiel que
        `published_at` des releases. Le chemin en deux requêtes ne sert plus que de repli : il
        donne la date de création du tag annoté quand l'appel direct n'a rien donné.
        """
        ref = quote(release.tag, safe="")
        data: Mapping[str, object] = {}
        try:
            data = _as_dict(self._request(f"{API_ROOT}/repos/{owner}/{name}/commits/{ref}"))
        except RateLimitedError:
            raise
        except GitHubError:
            pass
        commit = _api_mapping(data, "commit")
        release.published_at = _api_str(_api_mapping(commit, "committer"), "date")
        if not release.published_at:
            release.published_at = _api_str(_api_mapping(commit, "author"), "date")
        if not release.notes_md:
            release.notes_md = _api_str(commit, "message")
        if release.published_at:
            return True, 1
        try:
            ref_data = _as_dict(self._request(f"{API_ROOT}/repos/{owner}/{name}/git/ref/tags/{ref}"))
        except RateLimitedError:
            raise
        except GitHubError:
            return False, 2
        object_data = _api_mapping(ref_data, "object")
        sha = _api_str(object_data, "sha")
        if not sha or _api_str(object_data, "type") != "tag":
            return False, 2
        try:
            tag_data = _as_dict(self._request(f"{API_ROOT}/repos/{owner}/{name}/git/tags/{sha}"))
        except RateLimitedError:
            raise
        except GitHubError:
            return False, 3
        release.published_at = _api_str(_api_mapping(tag_data, "tagger"), "date")
        if not release.notes_md:
            release.notes_md = _api_str(tag_data, "message")
        return bool(release.published_at), 3

    def _date_missing_tags(
        self,
        owner: str,
        name: str,
        target: list[ReleaseInfo],
        budget: int,
        tag_pattern: str = "",
        tag_exclude: str = "",
        plan: DatingPlan | None = None,
        extra: Sequence[str] = (),
        window: int = MAX_RELEASES,
    ) -> int:
        """Donne une date et un message aux tags qui n'en ont pas, sans dépasser le budget.

        La file combine le plan calcule avant le fetch et les noms trouves pendant le fetch par
        `matching-refs`. Sans ce second apport, un tag comme `b12168`, qui n'existait pas dans
        l'etat local au demarrage de la passe, serait listé mais jamais date.

        Une réponse inattendue laisse la ligne sans date : ce n'est pas une erreur de fetch, la
        version reste affichée, et sa date sera payée à une passe suivante — elle est ensuite
        mémorisée dans `data/state.json` et n'est plus jamais redemandée.
        """
        rows = {item.tag: item for item in target if item.tag and not item.published_at}
        queued = self._date_queue(target, rows, plan, extra, tag_pattern, tag_exclude, window)
        dated = 0
        left = max(0, budget)
        for tag in queued:
            if left <= 0:
                break
            release = rows[tag]
            try:
                obtained, paid = self._date_one_tag(owner, name, release)
            except RateLimitedError:
                break
            left -= max(1, paid)
            if obtained:
                dated += 1
        return dated

    def download_asset(
        self,
        asset: Asset,
        dest_dir: Path,
        filename: str = "",
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        url = require_https(asset.url)
        if not host_allowed(url):
            raise RedirectRefusedError(t("Hôte de téléchargement hors liste blanche : {url}").format(url=url))
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GitHubError(
                t("Dossier de téléchargement inaccessible {folder} : {exc}").format(folder=dest_dir, exc=exc)
            ) from exc
        chosen = safe_asset_name(filename, fallback="") if filename else ""
        safe_name = chosen or safe_asset_name(asset.name, fallback="asset")
        # Un nom choisi dans « Enregistrer sous » est un choix assume : l'explorateur a deja demande
        # confirmation d'ecrasement, `unique_path()` inventerait un « asset (1) » que personne n'a
        # demande. Sans nom choisi, le nom vient du reseau et ne doit ecraser aucun fichier.
        target = dest_dir / chosen if chosen else unique_path(dest_dir, safe_name)
        temp = target.with_name(target.name + ".part")
        hops = 0
        try:
            while True:
                response = self._session.get(url, stream=True, timeout=self._timeout, allow_redirects=False)
                try:
                    if response.status_code in REDIRECT_CODES:
                        hops += 1
                        if hops > MAX_HOPS:
                            raise RedirectRefusedError(
                                t("Trop de redirections pour télécharger {name}").format(name=safe_name)
                            )
                        url = next_hop(response.headers, url)
                        if not host_allowed(url):
                            raise RedirectRefusedError(
                                t("Redirection de téléchargement refusée vers {url}").format(url=url)
                            )
                        continue
                    if response.status_code >= 400:
                        raise GitHubError(
                            t("Téléchargement refusé ({code}) : {url}").format(code=response.status_code, url=url)
                        )
                    return self._stream_to(response, temp, target, progress)
                finally:
                    response.close()
        except _requests().RequestException as exc:
            temp.unlink(missing_ok=True)
            raise NetworkError(t("Téléchargement interrompu : {exc}").format(exc=exc)) from exc
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise GitHubError(t("Échec d'écriture de {file} : {exc}").format(file=target, exc=exc)) from exc
        except GitHubError:
            temp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _stream_to(
        response: requests.Response,
        temp: Path,
        target: Path,
        progress: Callable[[int, int], None] | None,
    ) -> Path:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        handle: IO[bytes] = temp.open("wb")
        try:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK):
                if not chunk:
                    continue
                handle.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        finally:
            handle.close()
        temp.replace(target)
        return target


def unique_path(folder: Path, name: str) -> Path:
    candidate = folder / name
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        trial = folder / f"{name} ({index})"
        if not trial.exists():
            return trial
    raise GitHubError(t("Nom de fichier indisponible après 999 essais : {name}").format(name=name))
