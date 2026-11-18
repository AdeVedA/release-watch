"""Travail hors du thread GUI : appels GitHub et telechargements.

Chaque job est un QRunnable qui ne touche AUCUN widget : il rend la main par des
signaux, connectes depuis le thread GUI. Un client HTTP est cree par job, car
requests.Session n'est pas sur pour un usage simultane entre threads.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.github import GitHubClient, GitHubError
from app.models import (
    DATING_CATCHUP_MAX_ROUNDS,
    DATING_CATCHUP_MIN_QUOTA,
    LISTING_REQUESTS_PER_REPO,
    MAX_MATCHING_PREFIXES_PER_PASS,
    MAX_RELEASES,
    MAX_REQUESTS_PER_PASS,
    VERSIONS_SOURCE_TAGS,
    Asset,
    DatingPlan,
    ReleaseInfo,
)

NO_RATE = -1


def catchup_plan(needs: Sequence[tuple[str, int]], round_index: int, remaining: int) -> tuple[bool, list[str]]:
    """Manche de rattrapage des dates : quels bandeaux relancer, et faut-il le faire.

    Le plan de datation est calcule avant le fetch, sur les caches locaux : un bandeau fraichement
    peuple recoit une part de datation nulle et ses tags decouverts pendant la passe restent sans
    date. Cette fonction decide de la manche corrective sur les seuls compteurs rendus par les
    modeles, sans reseau : (relancer, identifiants des bandeaux qui ont encore des tags en attente).

    Le rattrapage s'arrete de lui-meme des qu'une manche ne date rien (`queued` partout a zero) ou
    que le plafond de manches est atteint. Un quota deja bas arret tout : perdre un 403 en plein
    rattrapage couterait plus de dates qu'il n'en rapporte.
    """
    if round_index >= DATING_CATCHUP_MAX_ROUNDS:
        return False, []
    if remaining != NO_RATE and remaining < DATING_CATCHUP_MIN_QUOTA:
        return False, []
    targets = [repo_id for repo_id, queued in needs if queued > 0]
    if not targets:
        return False, []
    return True, targets


class DatingBudget:
    """Réserve de requêtes GitHub d'une passe « Vérifier les repos », partagée entre les bandeaux.

    Une passe consomme trois kinds de requêtes : listing (`/tags`, `/releases`), découverte
    (`git/matching-refs`), datation (`/commits/{tag}`). Le total est plafonné, pas seulement la
    datation : sans ce plafond, un dépôt orphelin très profond pouvait vider le quota anonyme avant
    que les autres bandeaux aient seulement listé leurs versions. Les parts sont pré-allouées par
    la fenêtre principale ; le budget reste thread-safe et une part accordée n'est jamais rendue.
    """

    def __init__(self, total: int) -> None:
        self._lock = Lock()
        self._left = max(0, total)

    def take(self, want: int) -> int:
        with self._lock:
            granted = min(self._left, max(0, want))
            self._left -= granted
            return granted

    @property
    def left(self) -> int:
        with self._lock:
            return self._left


class FetchSignals(QObject):
    finished = Signal(str, object, int)
    failed = Signal(str, str)


class FetchJob(QRunnable):
    def __init__(
        self,
        client_factory: Callable[[], GitHubClient],
        repo_id: str,
        owner: str,
        name: str,
        limit: int,
        source: str = VERSIONS_SOURCE_TAGS,
        etags: Mapping[str, str] | None = None,
        previous: Sequence[ReleaseInfo] | None = None,
        budget: DatingBudget | None = None,
        listing_share: int = LISTING_REQUESTS_PER_REPO,
        match_share: int = MAX_MATCHING_PREFIXES_PER_PASS,
        dating_share: int = MAX_REQUESTS_PER_PASS,
        tag_pattern: str = "",
        tag_exclude: str = "",
        plan: DatingPlan | None = None,
        tag_index: Mapping[str, str] | None = None,
        tag_dates: Mapping[str, str] | None = None,
        tag_prefixes: Sequence[str] | None = None,
        dating_window: int = MAX_RELEASES,
    ) -> None:
        super().__init__()
        self.signals = FetchSignals()
        self.repo_id = repo_id
        self._client_factory = client_factory
        self._owner = owner
        self._name = name
        self._limit = limit
        self._source = source
        self._etags = dict(etags or {})
        # `previous` et les caches sont seulement lus depuis le thread du job : le thread GUI ne
        # les modifie qu'apres la fin du job, et le client ne recoit que des copies.
        self._previous = list(previous or [])
        self._budget = budget
        self._listing_share = max(0, listing_share)
        self._match_share = max(0, match_share)
        self._dating_share = max(0, dating_share)
        # Le motif ne filtre pas la recuperation : il designe seulement les tags auxquels
        # les requetes de listing, de decouverte et de datation sont accordees en priorite.
        self._tag_pattern = tag_pattern
        self._tag_exclude = tag_exclude
        self._plan = plan
        self._known_shas = dict(tag_index or {})
        self._known_dates = dict(tag_dates or {})
        self._known_prefixes = list(tag_prefixes or [])
        self._dating_window = max(1, dating_window)

    def run(self) -> None:
        client = self._client_factory()
        if self._budget is None:
            listing = self._listing_share
            matching = self._match_share
            dating = self._dating_share
        else:
            listing = self._budget.take(self._listing_share)
            matching = self._budget.take(self._match_share)
            dating = self._budget.take(self._dating_share)
        try:
            result = client.fetch_versions(
                self._owner,
                self._name,
                self._limit,
                source=self._source,
                etags=self._etags,
                previous=self._previous,
                listing_budget=listing,
                match_budget=matching,
                dating_budget=dating,
                tag_pattern=self._tag_pattern,
                tag_exclude=self._tag_exclude,
                plan=self._plan,
                known_dates=self._known_dates,
                done_prefixes=self._known_prefixes,
                dating_window=self._dating_window,
            )
        except GitHubError as exc:
            self.signals.failed.emit(self.repo_id, str(exc))
        else:
            remaining = client.rate.remaining if client.rate is not None else NO_RATE
            self.signals.finished.emit(self.repo_id, result, remaining)
        finally:
            client.close()


class ValidateSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ValidateJob(QRunnable):
    def __init__(self, client_factory: Callable[[], GitHubClient], owner: str, name: str) -> None:
        super().__init__()
        self.signals = ValidateSignals()
        self._client_factory = client_factory
        self._owner = owner
        self._name = name

    def run(self) -> None:
        client = self._client_factory()
        try:
            meta = client.validate(self._owner, self._name)
        except GitHubError as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(meta)
        client.close()


class DownloadSignals(QObject):
    finished = Signal(str, str)
    failed = Signal(str, str)
    progress = Signal(str, int, int)


class DownloadJob(QRunnable):
    def __init__(
        self,
        client_factory: Callable[[], GitHubClient],
        key: str,
        asset: Asset,
        dest_dir: Path,
        filename: str = "",
    ) -> None:
        super().__init__()
        self.signals = DownloadSignals()
        self.key = key
        self._client_factory = client_factory
        self._asset = asset
        self._dest_dir = dest_dir
        # Nom choisi dans le dialogue « Enregistrer sous » : vide = nom de l'asset, sans ecrasement.
        self._filename = filename

    def run(self) -> None:
        client = self._client_factory()

        def report(done: int, total: int) -> None:
            self.signals.progress.emit(self.key, done, total)

        try:
            target = client.download_asset(self._asset, self._dest_dir, self._filename, progress=report)
        except GitHubError as exc:
            self.signals.failed.emit(self.key, str(exc))
        else:
            self.signals.finished.emit(self.key, str(target))
        finally:
            client.close()


class JobPool:
    def __init__(self, max_threads: int = 2) -> None:
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max(1, max_threads))

    def start(self, job: QRunnable) -> None:
        self._pool.start(job)

    @property
    def active(self) -> int:
        return self._pool.activeThreadCount()

    def wait_for_done(self, timeout_ms: int = 4000) -> bool:
        return self._pool.waitForDone(timeout_ms)
