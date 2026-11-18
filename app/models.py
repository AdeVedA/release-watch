"""Modèles de données persistés et calcul de l'état affiché dans un bandeau.

La désérialisation est explicite champ par champ : un `state.json` édité à la
main peut contenir n'importe quoi, chaque valeur est donc forcée vers le type
attendu avec une valeur de secours, sans jamais lever d'exception sur un champ
parasite.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from app.filters import filter_names, keep
from app.i18n import DEFAULT_LANGUAGE, Language, normalize_language, t

MAX_RELEASES: Final[int] = 25
MAX_VERSIONS_CHOICES: tuple[int, ...] = (5, 10, 15, 20, 25)
MAX_REJECTED_VERSIONS_CHOICES: tuple[int, ...] = (5, 10, 15, 20, 25)
DEFAULT_MAX_VERSIONS: Final[int] = 5
DEFAULT_MAX_REJECTED_VERSIONS: Final[int] = 25
MAX_OTHER_TAGS: Final[int] = MAX_RELEASES
TAG_PATTERN_EXAMPLE: Final[str] = "v0.2.*"
DEFAULT_NOTES_FONT_SIZE: Final[int] = 13
DEFAULT_WINDOW_WIDTH: Final[int] = 1180
DEFAULT_WINDOW_HEIGHT: Final[int] = 780
DEFAULT_NOTES_DOCK_WIDTH: Final[int] = 420
MIN_WINDOW_WIDTH: Final[int] = 480
MIN_WINDOW_HEIGHT: Final[int] = 420
MIN_NOTES_DOCK_WIDTH: Final[int] = 320
MAX_NOTES_DOCK_WIDTH: Final[int] = 800

# Source des versions affichees. Les tags sont le defaut : une release publiee peut etre
# plus vieille que le tag le plus recent, et un repo peut taguer sans publier de release.
VERSIONS_SOURCE_TAGS: Final[str] = "tags"
VERSIONS_SOURCE_RELEASES: Final[str] = "releases"
VERSIONS_SOURCES: tuple[str, ...] = (VERSIONS_SOURCE_TAGS, VERSIONS_SOURCE_RELEASES)
DEFAULT_VERSIONS_SOURCE: Final[str] = VERSIONS_SOURCE_TAGS

# Les tags ne portent ni date ni message dans `/tags`, et `/tags` n'est PAS rendu par date :
# l'ordre suit les refs du depot (environ le nom decroissant), ce qui place les tags recents
# tres loin dans la pagination sur un gros depot. Ces valeurs encadrent ce qui est paye en
# requetes : plafond global d'une passe, part de listing par bandeau, taille de la fenetre
# de datation.
MAX_REQUESTS_PER_PASS: Final[int] = 50
LISTING_REQUESTS_PER_REPO: Final[int] = 2
MAX_MATCHING_PREFIXES_PER_PASS: Final[int] = 4
# Le plan de datation est calcule AVANT le fetch, sur les caches locaux : un bandeau fraichement
# peuple n'a encore aucun `tag_index` et recoit donc une part de datation nulle. Les tags decouverts
# pendant la passe restent sans date. D'ou la manche de rattrapage : elle relance une passe sur les
# seuls bandeaux qui ont encore des tags en attente, avec une reserve neuve.
# Un `304` consomme 1 sur le quota anonyme (mesure : `304 quota=1`), donc chaque manche de relance
# paie aussi deux requetes conditionnelles par bandeau : le nombre de manches est borne.
DATING_CATCHUP_MAX_ROUNDS: Final[int] = 2
# En dessous de ce quota restant, on ne relance rien : mieux vaut laisser le quota se retablir que
# de risquer un 403 en plein rattrapage, ce qui perdrait les dates deja obtenues.
DATING_CATCHUP_MIN_QUOTA: Final[int] = 10
# Le tag situated juste sous la derniere ligne affichee entre quand meme dans la file : sans
# cette marge, remonter d'une version dans la colonne ferait payer une passe de plus.
DATING_WINDOW_MARGIN: Final[int] = 10
MAX_VISIBLE_VERSIONS: Final[int] = 2 * MAX_RELEASES
# Cache des tags recenses et des dates deja payees. Il survit au cap des 25 lignes affichees :
# sans lui, une date payee serait re-payee a chaque passe.
MAX_TAG_INDEX: Final[int] = 1500
MAX_TAG_DATES: Final[int] = 1500
MAX_TAG_PREFIXES: Final[int] = 40
# Memoire des fichiers deja ecrits par « Enregistrer sous », par bandeau : elle ne sert qu'a
# rappeler le bouton 📂 d'une ligne. Au-dela du cap, les plus anciens tombent, ce qui n'est pas
# une erreur : le fichier reste sur le disque, seul le raccourci disparait.
MAX_DOWNLOADS: Final[int] = 100
# `git/matching-refs/tags/{prefix}` renvoie au plus 1000 refs. Si un prefixe revient plein,
# il n'est pas memorise comme « fait » : il sera resserre a la passe suivante.
MATCHING_REFS_PAGE: Final[int] = 1000

# Reponse de repli pour une ligne dont la date n'est pas encore connue : elle herite de la
# date de l'element date le plus proche au-dessus d'elle dans l'ordre naturel de sa famille.
UNDATED_BOUND: Final[str] = "9999-12-31T23:59:59Z"
# Famille sans aucune ancre datee (les `master-…` de `llama.cpp`, par exemple) : aucune
# comparaison n'est possible, donc ses lignes non datees tombent en bas plutot que de pretender
# etre plus recentes que tout le depot.
UNDATED_UNANCHORED: Final[str] = "0000-01-01T00:00:00Z"
FAMILY_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<prefix>[^0-9]*)(?P<number>\d+)")
DIGITS_SPLIT: Final[re.Pattern[str]] = re.compile(r"(\d+)")


def tag_family(tag: str) -> tuple[str, int | None]:
    """(lettres jusqu'au premier nombre, premier nombre) : `b12167` -> ("b", 12167).

    La famille est la seule cle qui rende deux noms comparables chronologiquement. Un tag comme
    `master-fff0e0e` tombe dans la famille `master-fff`, ou aucune ancre datee n'existe : ses
    milliers de refs ne coutent donc aucune requete de datation.
    """
    match = FAMILY_RE.match(tag)
    if match is None:
        return tag, None
    return match.group("prefix"), int(match.group("number"))


def natural_key(value: str) -> tuple[tuple[int, int, str], ...]:
    """Cle de tri « version naturelle » : `b12167` > `b12166`, `v7.4-rc1` > `v7.3-rc7`."""
    key: list[tuple[int, int, str]] = []
    for part in DIGITS_SPLIT.split(value):
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part.casefold()))
    return tuple(key)


def tag_search_prefixes(
    family: str, number: int, floor: int | None = None, limit: int = MAX_MATCHING_PREFIXES_PER_PASS
) -> list[str]:
    """Prefixes de noms a demander a `matching-refs`, autour de la fenetre de versions.

    Derives du numero de l'ancre datee la plus recente, avec la borne basse de la fenetre quand
    elle est connue. Pour `b12167`, la fenetre qui descend jusqu'a `b12034` produit `b1216`
    (b12160..b12169), `b121` (b12100..b12199), `b120` (b12000..b12099) et `b122` (le prochain
    millier de builds). Les prefixes trop larges (`b12`) ne servent a rien : GitHub renvoie les
    refs par ordre lexical, donc les plus vieux en premier, et tronque a 1000 refs.
    """
    digits = str(number)
    out: list[str] = []

    def add(stem: str) -> None:
        if not stem:
            return
        prefix = f"{family}{stem}"
        if prefix not in out:
            out.append(prefix)

    if not digits:
        return out

    tens = digits[:-1]
    base = digits[:-2] if len(digits) > 2 else tens
    add(tens)
    add(base)

    if base:
        base_num = int(base)
        unit = 100 if len(digits) > 2 else 10
        start = base_num * unit
        if (floor is None or floor < start) and base_num > 0:
            add(f"{base_num - 1:0{len(base)}d}")
        add(f"{base_num + 1:0{len(base)}d}")

    return out[: max(1, limit)]


@dataclass(slots=True)
class DatingPlan:
    """Ce qu'il reste a payer en requetes de datation pour un bandeau, dans l'ordre de priorite.

    - `above` : numeros superieurs a l'ancre datee la plus recente (sur llama.cpp, les builds
      posterieurs a la derniere release, qui n'ont souvent pas de release du tout) ;
    - `inside` : orphelins compris entre la frontiere basse de la fenetre visible et cette ancre ;
    - `prefixes` : prefixes `matching-refs` a interroger pour trouver les noms encore inconnus.
    """

    above: list[str] = field(default_factory=list)
    inside: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    known: int = 0
    dated: int = 0
    queued: int = 0
    outside: int = 0

    @property
    def queue(self) -> Iterator[str]:
        yield from self.above
        yield from self.inside


def versions_source_of(raw: Mapping[str, object], key: str = "versions_source") -> str:
    """Source de versions lue dans un JSON edite a la main : inconnu vaut defaut."""
    value = _as_str(raw, key, DEFAULT_VERSIONS_SOURCE)
    return value if value in VERSIONS_SOURCES else DEFAULT_VERSIONS_SOURCE


class Status(StrEnum):
    UP_TO_DATE = "up_to_date"
    NEW_VERSION = "new_version"
    AHEAD = "ahead"
    UNKNOWN = "unknown"
    ERROR = "error"


def status_label(status: Status) -> str:
    """Libellé d'état, lisible seulement dans l'infobulle du point coloré.

    Fonction et non dictionnaire de module : une constante évaluée à l'import
    resterait figée dans la langue du démarrage après un changement de langue.
    """
    if status == Status.UP_TO_DATE:
        return t("À JOUR")
    if status == Status.NEW_VERSION:
        return t("NOUVELLE VERSION")
    if status == Status.AHEAD:
        return t("HORS RELEASE")
    if status == Status.ERROR:
        return t("ERREUR FETCH")
    return t("VERSION LOCALE À DÉFINIR")


STATUS_TOKEN: dict[Status, str] = {
    Status.UP_TO_DATE: "ok",
    Status.NEW_VERSION: "new",
    Status.AHEAD: "ahead",
    Status.UNKNOWN: "unknown",
    Status.ERROR: "err",
}

# Catégories de lignes de versions : la couleur porte le rôle, plus de badge texte.
KIND_LATEST_LOCAL: Final[str] = "latest_local"
KIND_LATEST: Final[str] = "latest"
KIND_LOCAL: Final[str] = "local"
KIND_STALE: Final[str] = "stale"
KIND_OTHER: Final[str] = "other"
KIND_PLAIN: Final[str] = "plain"


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _as_str(raw: Mapping[str, object], key: str, default: str = "") -> str:
    value = raw.get(key, default)
    return value if isinstance(value, str) else default


def _as_int(raw: Mapping[str, object], key: str, default: int = 0) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_opt_int(raw: Mapping[str, object], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_bool(raw: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = raw.get(key, default)
    return value if isinstance(value, bool) else default


def _as_entries(raw: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _as_str_map(raw: Mapping[str, object], key: str, cap: int) -> dict[str, str]:
    """Dictionnaire de chaines lu defensivement dans un `state.json` edite a la main."""
    value = raw.get(key)
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name, item in value.items():
        if isinstance(name, str) and isinstance(item, str) and name and item:
            out[name] = item
            if len(out) >= cap:
                break
    return out


def _as_str_list(raw: Mapping[str, object], key: str, cap: int) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item][:cap]


def _nearest_choice(value: int, choices: Sequence[int]) -> int:
    """Ramène la valeur au cran affiché par les combos ; à égalité, le cran le plus bas."""
    return min(choices, key=lambda choice: (abs(choice - value), choice))


def snap_versions_choice(value: int) -> int:
    """Valeur de réglage ramenée aux crans communs (5, 10, 15, 20, 25)."""
    return _nearest_choice(max(1, value), MAX_VERSIONS_CHOICES)


def _clamp_versions(value: int) -> int:
    return _nearest_choice(value, MAX_VERSIONS_CHOICES)


def _clamp_rejected_versions(value: int) -> int:
    return _nearest_choice(value, MAX_REJECTED_VERSIONS_CHOICES)


@dataclass(slots=True)
class Asset:
    name: str
    url: str
    size: int = 0

    @staticmethod
    def from_dict(raw: Mapping[str, object]) -> Asset:
        return Asset(
            name=_as_str(raw, "name"),
            url=_as_str(raw, "url"),
            size=_as_int(raw, "size"),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ReleaseInfo:
    tag: str
    name: str = ""
    url: str = ""
    published_at: str = ""
    notes_md: str = ""
    source: str = "releases"
    prerelease: bool = False
    assets: list[Asset] = field(default_factory=list)

    @staticmethod
    def from_dict(raw: Mapping[str, object]) -> ReleaseInfo:
        return ReleaseInfo(
            tag=_as_str(raw, "tag"),
            name=_as_str(raw, "name"),
            url=_as_str(raw, "url"),
            published_at=_as_str(raw, "published_at"),
            notes_md=_as_str(raw, "notes_md"),
            source=_as_str(raw, "source", "releases"),
            prerelease=_as_bool(raw, "prerelease"),
            assets=[Asset.from_dict(entry) for entry in _as_entries(raw, "assets")],
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.tag or self.name or t("(sans nom)")

    @property
    def asset_names(self) -> list[str]:
        return [asset.name for asset in self.assets]


@dataclass(slots=True)
class ScriptSpec:
    path: str
    cwd: str = ""
    label: str = ""

    @staticmethod
    def from_dict(raw: Mapping[str, object]) -> ScriptSpec:
        return ScriptSpec(
            path=_as_str(raw, "path"),
            cwd=_as_str(raw, "cwd"),
            label=_as_str(raw, "label"),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def display(self) -> str:
        return self.label or self.path.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass(slots=True)
class Repo:
    id: str
    owner: str
    name: str
    url: str
    title: str
    max_versions: int = DEFAULT_MAX_VERSIONS
    max_rejected_versions: int = DEFAULT_MAX_REJECTED_VERSIONS
    tag_pattern: str = ""
    tag_exclude: str = ""
    collapsed: bool = False
    excluded_check_all: bool = False
    local_version: str = ""
    local_version_source: str = ""
    assets_enabled: bool = True
    asset_include: str = ""
    asset_exclude: str = ""
    default_asset_name: str = ""
    download_dir: str = ""
    # Fichiers deja ecrits : "{tag}|{nom de l'asset}" -> chemin complet. Porte par le bandeau et non
    # par l'asset, parce qu'un fetch recree les assets depuis GitHub et effacerait la trace.
    downloads: dict[str, str] = field(default_factory=dict)
    column_left_collapsed: bool = False
    column_right_collapsed: bool = False
    versions_source: str = DEFAULT_VERSIONS_SOURCE
    etag_tags: str = ""
    etag_releases: str = ""
    # Cache des tags recenses : nom -> sha du commit, nom -> date ISO deja payee, prefixes
    # `matching-refs` deja interroges. Il survit au cap des 25 lignes affichees : sans lui, une
    # date obtenue serait re-obtenue a chaque passe.
    tag_index: dict[str, str] = field(default_factory=dict)
    tag_dates: dict[str, str] = field(default_factory=dict)
    tags_prefixes: list[str] = field(default_factory=list)
    scripts: list[ScriptSpec] = field(default_factory=list)
    releases: list[ReleaseInfo] = field(default_factory=list)
    last_fetch_at: str = ""
    last_fetch_ok: bool = False
    last_fetch_error: str = ""

    @staticmethod
    def make_id(owner: str, name: str) -> str:
        return f"{owner}/{name}".lower()

    @staticmethod
    def from_dict(raw: Mapping[str, object]) -> Repo:
        owner = _as_str(raw, "owner")
        name = _as_str(raw, "name")
        return Repo(
            id=_as_str(raw, "id") or Repo.make_id(owner, name),
            owner=owner,
            name=name,
            url=_as_str(raw, "url"),
            title=_as_str(raw, "title") or name,
            max_versions=_clamp_versions(_as_int(raw, "max_versions", DEFAULT_MAX_VERSIONS)),
            max_rejected_versions=_clamp_rejected_versions(
                _as_int(raw, "max_rejected_versions", DEFAULT_MAX_REJECTED_VERSIONS)
            ),
            tag_pattern=_as_str(raw, "tag_pattern"),
            tag_exclude=_as_str(raw, "tag_exclude"),
            collapsed=_as_bool(raw, "collapsed"),
            excluded_check_all=_as_bool(raw, "excluded_check_all"),
            local_version=_as_str(raw, "local_version"),
            local_version_source=_as_str(raw, "local_version_source"),
            assets_enabled=_as_bool(raw, "assets_enabled", True),
            asset_include=_as_str(raw, "asset_include"),
            asset_exclude=_as_str(raw, "asset_exclude"),
            default_asset_name=_as_str(raw, "default_asset_name"),
            download_dir=_as_str(raw, "download_dir"),
            downloads=_as_str_map(raw, "downloads", MAX_DOWNLOADS),
            column_left_collapsed=_as_bool(raw, "column_left_collapsed"),
            column_right_collapsed=_as_bool(raw, "column_right_collapsed"),
            versions_source=versions_source_of(raw),
            etag_tags=_as_str(raw, "etag_tags"),
            etag_releases=_as_str(raw, "etag_releases"),
            tag_index=_as_str_map(raw, "tag_index", MAX_TAG_INDEX),
            tag_dates=_as_str_map(raw, "tag_dates", MAX_TAG_DATES),
            tags_prefixes=_as_str_list(raw, "tags_prefixes", MAX_TAG_PREFIXES),
            scripts=[ScriptSpec.from_dict(entry) for entry in _as_entries(raw, "scripts")],
            releases=[ReleaseInfo.from_dict(entry) for entry in _as_entries(raw, "releases")],
            last_fetch_at=_as_str(raw, "last_fetch_at"),
            last_fetch_ok=_as_bool(raw, "last_fetch_ok"),
            last_fetch_error=_as_str(raw, "last_fetch_error"),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def github_url(self) -> str:
        return self.url or f"https://github.com/{self.owner}/{self.name}"

    @property
    def releases_url(self) -> str:
        return f"{self.github_url}/releases"

    @property
    def tags_url(self) -> str:
        return f"{self.github_url}/tags"

    @property
    def versions_url(self) -> str:
        """La page GitHub qui correspond à la source choisie : c'est elle qu'ouvre le bandeau."""
        return self.releases_url if self.versions_source == VERSIONS_SOURCE_RELEASES else self.tags_url

    def uses_tags(self) -> bool:
        return self.versions_source == VERSIONS_SOURCE_TAGS

    def tag_is_allowed(self, tag: str) -> bool:
        """Un tag est autorisé s'il suit le motif saisi et n'est pas exclu."""
        return keep(tag, self.tag_pattern, self.tag_exclude)

    def asset_is_allowed(self, name: str) -> bool:
        if not self.assets_enabled:
            return False
        return keep(name, self.asset_include, self.asset_exclude)

    @staticmethod
    def _by_date(items: Sequence[ReleaseInfo]) -> list[ReleaseInfo]:
        """Ordre d'affichage : famille la plus récente d'abord, puis ordre naturel de version.

        A l'interieur d'une famille de versions (`b…`, `v…`), le numero est plus fiable que la
        date renvoyee par l'API : les tags `b…` peuvent avoir ete crees dans un ordre qui ne suit
        pas la date de publication de la release correspondante. On obtient donc l'ordre attendu
        `b12170 > b12169 > b12167`, sans que la colonne gauche se retrouvent avec `b12167` devant
        `b12170` a cause d'une date de release posterieure.

        La date ne sert plus qu'a placer les familles entre elles, et a pousser en bas les familles
        sans aucune date connue (`master-…`).
        """
        families: dict[str, list[ReleaseInfo]] = {}
        for item in items:
            families.setdefault(tag_family(item.tag)[0], []).append(item)
        latest: dict[str, str] = {}
        for family, members in families.items():
            members.sort(key=lambda item: natural_key(item.tag), reverse=True)
            dated = [member.published_at for member in members if member.published_at]
            latest[family] = max(dated) if dated else UNDATED_UNANCHORED
        return sorted(
            items,
            key=lambda item: (latest[tag_family(item.tag)[0]], natural_key(item.tag)),
            reverse=True,
        )

    def archive_url(self, tag: str) -> str:
        return f"{self.github_url}/archive/refs/tags/{tag}"

    def cached_release(self, tag: str) -> ReleaseInfo:
        """Ligne reconstruite depuis le cache : le tag est connu, sa date l'est peut-être déjà."""
        archive = self.archive_url(tag)
        return ReleaseInfo(
            tag=tag,
            name=tag,
            url=self.tags_url,
            published_at=self.tag_dates.get(tag, ""),
            notes_md="",
            source=VERSIONS_SOURCE_TAGS,
            prerelease=False,
            assets=[
                Asset(name=f"{tag}.zip", url=f"{archive}.zip", size=0),
                Asset(name=f"{tag}.tar.gz", url=f"{archive}.tar.gz", size=0),
            ],
        )

    @staticmethod
    def download_key(tag: str, asset_name: str) -> str:
        """Cle d'un fichier ecrit : le tag ne suffit pas, deux versions portent le meme asset."""
        return f"{tag}|{asset_name}"

    def remember_download(self, tag: str, asset_name: str, path: str) -> None:
        """Memorise le fichier écrit pour ce couple version + asset. Le plus récent gagne.

        Le cap tombe sur les plus anciens (`dict` garde l'ordre d'insertion) : un chemin oublié
        n'est pas perdu, seul le raccourci 📂 de la ligne disparaît.
        """
        self.downloads[self.download_key(tag, asset_name)] = path
        while len(self.downloads) > MAX_DOWNLOADS:
            self.downloads.pop(next(iter(self.downloads)))

    def downloads_for(self, tag: str) -> dict[str, str]:
        """Les fichiers déjà écrits pour cette version : nom d'asset -> chemin complet."""
        prefix = f"{tag}|"
        return {key[len(prefix) :]: value for key, value in self.downloads.items() if key.startswith(prefix)}

    def remember_tags(self, entries: Mapping[str, str]) -> int:
        """Mémorise `nom -> sha` des tags recensés. Rend le nombre de noms nouveaux."""
        added = 0
        for tag, sha in entries.items():
            if not tag or not sha:
                continue
            if tag not in self.tag_index:
                added += 1
            self.tag_index[tag] = sha
        while len(self.tag_index) > MAX_TAG_INDEX:
            self.tag_index.pop(next(iter(self.tag_index)))
        return added

    def remember_dates(self, dates: Mapping[str, str]) -> int:
        """Mémorise `nom -> date ISO`. Ce qui est payé ici n'est plus jamais redemandé."""
        added = 0
        for tag, date in dates.items():
            if not tag or not date:
                continue
            if tag not in self.tag_dates:
                added += 1
            self.tag_dates[tag] = date
        while len(self.tag_dates) > MAX_TAG_DATES:
            self.tag_dates.pop(next(iter(self.tag_dates)))
        return added

    def remember_prefixes(self, prefixes: Sequence[str]) -> None:
        """Préfixes `matching-refs` déjà interrogés : ils ne seront pas repayés."""
        for prefix in prefixes:
            if prefix and prefix not in self.tags_prefixes:
                self.tags_prefixes.append(prefix)
        if len(self.tags_prefixes) > MAX_TAG_PREFIXES:
            self.tags_prefixes = self.tags_prefixes[-MAX_TAG_PREFIXES:]

    def dating_plan(self) -> DatingPlan:
        """Ce qui doit être daté en priorité, et ce qui ne le sera jamais.

        La fenêtre est bornée par les ancres datées de chaque famille : sur `llama.cpp`, les
        releases datent déjà `b12167` … `b11988`, donc seuls les orphelins numériquement au-dessus
        de `b12167` (les builds postérieurs à la dernière release, souvent dépourvus de release)
        et ceux coincés entre les ancres jusqu'à `b11988 - marge` sont des candidats. Les familles
        sans aucune ancre (`master-…`) ne reçoivent aucune requête dès qu'il existe une ancre
        ailleurs : elles ne peuvent pas être replacées chronologiquement par leur seul nom.
        """
        names = set(self.tag_index) | set(self.tag_dates) | {item.tag for item in self.releases if item.tag}
        dated: dict[str, str] = {tag: date for tag, date in self.tag_dates.items() if date}
        dated.update({item.tag: item.published_at for item in self.releases if item.tag and item.published_at})
        plan = DatingPlan(known=len(names), dated=len(dated))
        families: dict[str, list[str]] = {}
        for name in names:
            families.setdefault(tag_family(name)[0], []).append(name)
        window = max(1, self.max_versions + self.max_rejected_versions)
        prefix_groups: list[tuple[str, list[str]]] = []

        def rank(names: list[str]) -> list[str]:
            return sorted(names, key=lambda name: (self.tag_is_allowed(name), natural_key(name)), reverse=True)

        for family, members in families.items():
            members.sort(key=natural_key, reverse=True)
            numbered = [(member, tag_family(member)[1]) for member in members]
            anchors = [number for member, number in numbered if number is not None and dated.get(member)]
            if not anchors:
                if dated:
                    plan.outside += sum(1 for member, _ in numbered if not dated.get(member))
                    continue
                continue
            newest = max(anchors)
            ranked = sorted(anchors, reverse=True)
            floor = ranked[min(len(ranked) - 1, window - 1)] - DATING_WINDOW_MARGIN
            above: list[str] = []
            inside: list[str] = []
            allowed_anchors = [
                (member, number)
                for member, number in numbered
                if number is not None and dated.get(member) and self.tag_is_allowed(member)
            ]
            for member, number in numbered:
                if number is None or dated.get(member):
                    continue
                if number > newest:
                    above.append(member)
                elif number >= floor:
                    inside.append(member)
                else:
                    plan.outside += 1
            plan.above.extend(rank(above))
            plan.inside.extend(rank(inside))
            cap_dates = max(MAX_VISIBLE_VERSIONS, window + DATING_WINDOW_MARGIN)
            plan.above = plan.above[:cap_dates]
            plan.inside = plan.inside[:cap_dates]
            if allowed_anchors:
                # Les prefixes ne sont jamais consideres comme « deja faits » : une ref peut
                # apparaitre sous un prefixe precedemment vide. Le budget de la passe borne le
                # nombre reellement interroge.
                newest_date = max((dated[member] for member, _ in allowed_anchors), default="")
                group = tag_search_prefixes(family, newest, floor)
                if group:
                    prefix_groups.append((newest_date, group))

        for _, group in sorted(prefix_groups, key=lambda entry: entry[0], reverse=True):
            plan.prefixes.extend(prefix for prefix in group if prefix not in plan.prefixes)

        if not dated:
            # Repo sans release ni date memorisee (torvalds/linux) : aucune ancre ne permet de
            # comparer, donc on paie d'abord la tete naturelle des noms connus.
            head = window + DATING_WINDOW_MARGIN
            ordered = sorted(names, key=natural_key, reverse=True)
            plan.inside = rank(list(ordered[:head]))
            plan.outside = max(0, len(names) - head)

        cap_dates = max(MAX_VISIBLE_VERSIONS, window + DATING_WINDOW_MARGIN)
        plan.above = plan.above[:cap_dates]
        plan.inside = plan.inside[:cap_dates]
        plan.queued = len(plan.above) + len(plan.inside)
        return plan

    def storage_cap(self) -> int:
        """Lignes gardées en base : de quoi remplir les deux colonnes, plafonné à `MAX_VISIBLE_VERSIONS`.

        Les colonnes sont bornées chacune par son propre réglage (`max_versions` à gauche,
        `max_rejected_versions` à droite) : un cap de stockage plus bas tronque silencieusement
        la colonne rejetée, réglage affiché à l'écran non respecté.
        """
        kept = snap_versions_choice(self.max_versions)
        rejected = snap_versions_choice(self.max_rejected_versions)
        return min(MAX_VISIBLE_VERSIONS, kept + rejected)

    def pick_candidates(self, candidates: Sequence[ReleaseInfo], cap: int = MAX_RELEASES) -> list[ReleaseInfo]:
        """Les lignes gardées en base, chronologiques, en incluant les tags déjà recensés.

        Le cap est une limite de stockage, pas un filtre : la priorité reste donnée à ce qui passe
        le motif « à garder ». Les noms connus du cache mais absents de la réponse réseau entrent
        aussi comme candidats, avec leur date déjà payée : c'est ce qui fait remonter un tag sans
        release dans la colonne, et c'est ce qui le fera dater à la passe suivante, puisqu'il entre
        alors dans la fenêtre de datation.
        """
        seen = {item.tag for item in candidates}
        merged = list(candidates)
        merged.extend(self.cached_release(tag) for tag in self.tag_index if tag not in seen)
        allowed = [item for item in merged if self.tag_is_allowed(item.tag)]
        refused = [item for item in merged if not self.tag_is_allowed(item.tag)]
        return (self._by_date(allowed) + self._by_date(refused))[: max(1, cap)]

    @property
    def allowed_releases(self) -> list[ReleaseInfo]:
        """Tous les tags autorisés, dans l'ordre de version reconstruit par `_by_date`.

        Le stockage peut garder un ordre intermédiaire (fetch, `state.json` plus ancien), mais les
        colonnes doivent être coupées APRÈS le tri : sans cela, un dépôt dont la liste en base est
        ascendante afficherait les versions les plus vieilles à gauche et les plus récentes à
        droite. A l'interieur d'une famille, c'est le numero de version qui commande ; la date ne
        sert qu'a classer les familles entre elles.
        """
        return self._by_date([release for release in self.releases if self.tag_is_allowed(release.tag)])

    @property
    def matching_releases(self) -> list[ReleaseInfo]:
        """Seules ces versions-là sont comparées à la version locale : elles suivent le motif."""
        return self.allowed_releases[: self.max_versions]

    @property
    def stale_releases(self) -> list[ReleaseInfo]:
        """Tags autorisés mais au-delà du cap affiché : trop anciens, colonne de droite."""
        return self.allowed_releases[self.max_versions : MAX_OTHER_TAGS]

    @property
    def other_releases(self) -> list[ReleaseInfo]:
        """Tags refusés par le motif ou l'exclusion : affichés à droite, jamais comparés."""
        refused = [release for release in self.releases if not self.tag_is_allowed(release.tag)]
        return self._by_date(refused)[:MAX_OTHER_TAGS]

    @property
    def rejected_candidates(self) -> list[ReleaseInfo]:
        """Tous les tags candidats à la colonne de droite, avant le cap affiché."""
        return [*self.stale_releases, *self.other_releases]

    @property
    def rejected_releases(self) -> list[ReleaseInfo]:
        """Colonne de droite, bornée par le choix « rejetées »."""
        return self.rejected_candidates[: self.max_rejected_versions]

    @property
    def latest(self) -> ReleaseInfo | None:
        matching = self.matching_releases
        return matching[0] if matching else None

    @property
    def known_tags(self) -> list[str]:
        return [release.tag for release in self.releases]

    @property
    def status(self) -> Status:
        return compute_status(self)

    @property
    def has_scripts(self) -> bool:
        return bool(self.scripts)

    def release_kind(self, release: ReleaseInfo, side: str) -> str:
        """Catégorie de la ligne : c'est elle qui porte la couleur, plus aucun badge texte."""
        is_local = bool(self.local_version) and release.tag == self.local_version
        latest = self.latest
        is_latest = side == "left" and latest is not None and latest.tag == release.tag
        if is_local:
            return KIND_LATEST_LOCAL if is_latest else KIND_LOCAL
        if side == "right":
            return KIND_STALE if self.tag_is_allowed(release.tag) else KIND_OTHER
        return KIND_LATEST if is_latest else KIND_PLAIN

    def apply_asset_filters(self) -> tuple[int, int]:
        """Ne laisse en base que les assets autorisés. Retourne (gardés, ignorés)."""
        kept_total = 0
        dropped_total = 0
        for release in self.releases:
            names = [asset.name for asset in release.assets]
            if self.assets_enabled:
                kept = set(filter_names(names, self.asset_include, self.asset_exclude))
            else:
                kept = set()
            release.assets = [asset for asset in release.assets if asset.name in kept]
            kept_total += len(release.assets)
            dropped_total += len(names) - len(release.assets)
        return kept_total, dropped_total

    def prune_asset_choice(self) -> bool:
        """L'asset par défaut pointe-t-il encore un asset conservé ?"""
        if not self.default_asset_name:
            return False
        return any(asset.name == self.default_asset_name for release in self.releases for asset in release.assets)


@dataclass(slots=True)
class Settings:
    max_versions: int = DEFAULT_MAX_VERSIONS
    download_dir: str = ""
    notes_font_size: int = DEFAULT_NOTES_FONT_SIZE
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    window_x: int | None = None
    window_y: int | None = None
    notes_dock_width: int = DEFAULT_NOTES_DOCK_WIDTH
    language: Language = DEFAULT_LANGUAGE

    @staticmethod
    def from_dict(raw: Mapping[str, object]) -> Settings:
        width = _as_int(raw, "window_width", DEFAULT_WINDOW_WIDTH)
        height = _as_int(raw, "window_height", DEFAULT_WINDOW_HEIGHT)
        dock_width = _as_int(raw, "notes_dock_width", DEFAULT_NOTES_DOCK_WIDTH)
        return Settings(
            max_versions=_clamp_versions(_as_int(raw, "max_versions", DEFAULT_MAX_VERSIONS)),
            download_dir=_as_str(raw, "download_dir"),
            notes_font_size=_as_int(raw, "notes_font_size", DEFAULT_NOTES_FONT_SIZE),
            window_width=width if width >= MIN_WINDOW_WIDTH else DEFAULT_WINDOW_WIDTH,
            window_height=height if height >= MIN_WINDOW_HEIGHT else DEFAULT_WINDOW_HEIGHT,
            window_x=_as_opt_int(raw, "window_x"),
            window_y=_as_opt_int(raw, "window_y"),
            notes_dock_width=max(MIN_NOTES_DOCK_WIDTH, min(MAX_NOTES_DOCK_WIDTH, dock_width)),
            language=normalize_language(raw.get("language", DEFAULT_LANGUAGE)),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class AppState:
    settings: Settings = field(default_factory=Settings)
    repos: list[Repo] = field(default_factory=list)

    def repo_by_id(self, repo_id: str) -> Repo | None:
        for repo in self.repos:
            if repo.id == repo_id:
                return repo
        return None

    def index_of(self, repo_id: str) -> int:
        for position, repo in enumerate(self.repos):
            if repo.id == repo_id:
                return position
        return -1


def tag_matches(pattern: str, tag: str) -> bool:
    """Motif glob simple (`v0.2.*`, `v0.*`, `release-??`) : motif vide = tous les tags."""
    return keep(tag, pattern, "")


def allowed_names(names: Sequence[str], include: str, exclude: str) -> list[str]:
    """Passerelle lisible pour les contrôles : mêmes règles que le bandeau."""
    return filter_names(names, include, exclude)


def compute_status(repo: Repo) -> Status:
    """Seuls les tags autorisés par le bandeau décident de l'état affiché."""
    if repo.last_fetch_at and not repo.last_fetch_ok:
        return Status.ERROR
    if not repo.local_version:
        return Status.UNKNOWN
    matching = repo.matching_releases
    if not matching:
        return Status.UNKNOWN
    if repo.local_version == matching[0].tag:
        return Status.UP_TO_DATE
    if repo.local_version in {release.tag for release in matching}:
        return Status.NEW_VERSION
    return Status.AHEAD
